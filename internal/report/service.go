package report

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"cyberstrike-ai/internal/database"
)

type Service struct {
	db *database.DB
}

type GenerateRequest struct {
	Title          string `json:"title"`
	ConversationID string `json:"conversation_id"`
}

type Summary struct {
	Scope              string         `json:"scope"`
	ConversationTitle  string         `json:"conversation_title,omitempty"`
	Severity           map[string]int `json:"severity"`
	Status             map[string]int `json:"status"`
	AttackChainNodes   int            `json:"attack_chain_nodes"`
	AttackChainEdges   int            `json:"attack_chain_edges"`
	ToolExecutionCount int            `json:"tool_execution_count"`
	GeneratedAt        time.Time      `json:"generated_at"`
}

func NewService(db *database.DB) *Service {
	return &Service{db: db}
}

func (s *Service) Generate(req GenerateRequest) (*database.Report, error) {
	vulnerabilities, err := s.db.ListVulnerabilities(10000, 0, "", req.ConversationID, "", "")
	if err != nil {
		return nil, err
	}

	nodes, edges, toolCount, conversationTitle, err := s.collectContext(req.ConversationID)
	if err != nil {
		return nil, err
	}

	severity := map[string]int{"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
	status := map[string]int{}
	for _, vuln := range vulnerabilities {
		key := strings.ToLower(vuln.Severity)
		if _, ok := severity[key]; !ok {
			key = "info"
		}
		severity[key]++
		status[vuln.Status]++
	}

	title := strings.TrimSpace(req.Title)
	if title == "" {
		if conversationTitle != "" {
			title = conversationTitle + " - 安全测试报告"
		} else {
			title = "LNU-SecLM 安全测试报告"
		}
	}

	summary := Summary{
		Scope:              "全部数据",
		ConversationTitle:  conversationTitle,
		Severity:           severity,
		Status:             status,
		AttackChainNodes:   len(nodes),
		AttackChainEdges:   len(edges),
		ToolExecutionCount: toolCount,
		GeneratedAt:        time.Now(),
	}
	if req.ConversationID != "" {
		summary.Scope = "会话 " + req.ConversationID
	}
	summaryJSON, _ := json.Marshal(summary)

	report := &database.Report{
		Title:              title,
		ConversationID:     req.ConversationID,
		Status:             "completed",
		RiskLevel:          highestRisk(severity),
		VulnerabilityCount: len(vulnerabilities),
		CriticalCount:      severity["critical"],
		HighCount:          severity["high"],
		MediumCount:        severity["medium"],
		LowCount:           severity["low"],
		InfoCount:          severity["info"],
		AttackChainNodes:   len(nodes),
		ToolExecutionCount: toolCount,
		SummaryJSON:        string(summaryJSON),
	}
	report.ContentMarkdown = buildMarkdown(report, summary, vulnerabilities, nodes, edges)
	return s.db.CreateReport(report)
}

func (s *Service) collectContext(conversationID string) ([]database.AttackChainNode, []database.AttackChainEdge, int, string, error) {
	if conversationID != "" {
		nodes, err := s.db.LoadAttackChainNodes(conversationID)
		if err != nil {
			return nil, nil, 0, "", err
		}
		edges, err := s.db.LoadAttackChainEdges(conversationID)
		if err != nil {
			return nil, nil, 0, "", err
		}
		var title string
		if err := s.db.QueryRow("SELECT title FROM conversations WHERE id = ?", conversationID).Scan(&title); err != nil {
			return nil, nil, 0, "", fmt.Errorf("指定的会话不存在: %w", err)
		}
		var toolCount int
		err = s.db.QueryRow(`
			SELECT COUNT(DISTINCT tool_execution_id)
			FROM attack_chain_nodes
			WHERE conversation_id = ? AND tool_execution_id IS NOT NULL
		`, conversationID).Scan(&toolCount)
		return nodes, edges, toolCount, title, err
	}

	nodes := make([]database.AttackChainNode, 0)
	rows, err := s.db.Query(`
		SELECT id, node_type, node_name, COALESCE(tool_execution_id, ''), COALESCE(metadata, '{}'), risk_score
		FROM attack_chain_nodes ORDER BY created_at ASC
	`)
	if err != nil {
		return nil, nil, 0, "", err
	}
	for rows.Next() {
		var node database.AttackChainNode
		var metadata string
		if err := rows.Scan(&node.ID, &node.Type, &node.Label, &node.ToolExecutionID, &metadata, &node.RiskScore); err != nil {
			rows.Close()
			return nil, nil, 0, "", err
		}
		_ = json.Unmarshal([]byte(metadata), &node.Metadata)
		nodes = append(nodes, node)
	}
	if err := rows.Close(); err != nil {
		return nil, nil, 0, "", err
	}

	edges := make([]database.AttackChainEdge, 0)
	edgeRows, err := s.db.Query(`
		SELECT id, source_node_id, target_node_id, edge_type, weight
		FROM attack_chain_edges ORDER BY created_at ASC
	`)
	if err != nil {
		return nil, nil, 0, "", err
	}
	for edgeRows.Next() {
		var edge database.AttackChainEdge
		if err := edgeRows.Scan(&edge.ID, &edge.Source, &edge.Target, &edge.Type, &edge.Weight); err != nil {
			edgeRows.Close()
			return nil, nil, 0, "", err
		}
		edges = append(edges, edge)
	}
	if err := edgeRows.Close(); err != nil {
		return nil, nil, 0, "", err
	}

	var toolCount int
	if err := s.db.QueryRow("SELECT COUNT(*) FROM tool_executions").Scan(&toolCount); err != nil {
		return nil, nil, 0, "", err
	}
	return nodes, edges, toolCount, "", nil
}

func highestRisk(severity map[string]int) string {
	for _, level := range []string{"critical", "high", "medium", "low", "info"} {
		if severity[level] > 0 {
			return level
		}
	}
	return "info"
}

func buildMarkdown(report *database.Report, summary Summary, vulnerabilities []*database.Vulnerability, nodes []database.AttackChainNode, edges []database.AttackChainEdge) string {
	var b strings.Builder
	fmt.Fprintf(&b, "# %s\n\n", report.Title)
	fmt.Fprintf(&b, "> 由 LNU-SecLM 安全报告模块自动生成  \n")
	fmt.Fprintf(&b, "> 生成时间：%s\n\n", summary.GeneratedAt.Format("2006-01-02 15:04:05"))

	b.WriteString("## 1. 执行摘要\n\n")
	fmt.Fprintf(&b, "- **报告范围**：%s\n", summary.Scope)
	if summary.ConversationTitle != "" {
		fmt.Fprintf(&b, "- **会话名称**：%s\n", summary.ConversationTitle)
	}
	fmt.Fprintf(&b, "- **总体风险等级**：%s\n", severityName(report.RiskLevel))
	fmt.Fprintf(&b, "- **漏洞总数**：%d\n", report.VulnerabilityCount)
	fmt.Fprintf(&b, "- **攻击链节点/关系**：%d / %d\n", summary.AttackChainNodes, summary.AttackChainEdges)
	fmt.Fprintf(&b, "- **关联工具执行数**：%d\n\n", summary.ToolExecutionCount)

	b.WriteString("## 2. 风险统计\n\n")
	b.WriteString("| 严重程度 | 数量 |\n| --- | ---: |\n")
	for _, level := range []string{"critical", "high", "medium", "low", "info"} {
		fmt.Fprintf(&b, "| %s | %d |\n", severityName(level), summary.Severity[level])
	}
	b.WriteString("\n")

	b.WriteString("## 3. 漏洞明细\n\n")
	if len(vulnerabilities) == 0 {
		b.WriteString("本次范围内未记录漏洞。\n\n")
	} else {
		sort.SliceStable(vulnerabilities, func(i, j int) bool {
			return riskOrder(vulnerabilities[i].Severity) < riskOrder(vulnerabilities[j].Severity)
		})
		for i, vuln := range vulnerabilities {
			fmt.Fprintf(&b, "### 3.%d %s\n\n", i+1, vuln.Title)
			fmt.Fprintf(&b, "- **风险等级**：%s\n", severityName(vuln.Severity))
			fmt.Fprintf(&b, "- **状态**：%s\n", statusName(vuln.Status))
			if vuln.Type != "" {
				fmt.Fprintf(&b, "- **漏洞类型**：%s\n", vuln.Type)
			}
			if vuln.Target != "" {
				fmt.Fprintf(&b, "- **目标**：%s\n", vuln.Target)
			}
			if vuln.Description != "" {
				fmt.Fprintf(&b, "\n**漏洞描述**\n\n%s\n", vuln.Description)
			}
			if vuln.Proof != "" {
				fmt.Fprintf(&b, "\n**验证证据**\n\n```\n%s\n```\n", vuln.Proof)
			}
			if vuln.Impact != "" {
				fmt.Fprintf(&b, "\n**影响分析**\n\n%s\n", vuln.Impact)
			}
			recommendation := vuln.Recommendation
			if recommendation == "" {
				recommendation = defaultRecommendation(vuln.Type)
			}
			fmt.Fprintf(&b, "\n**修复建议**\n\n%s\n\n", recommendation)
		}
	}

	b.WriteString("## 4. 攻击链概览\n\n")
	if len(nodes) == 0 {
		b.WriteString("本次范围内暂无攻击链数据。\n\n")
	} else {
		b.WriteString("| 节点 | 类型 | 风险分 |\n| --- | --- | ---: |\n")
		limit := len(nodes)
		if limit > 30 {
			limit = 30
		}
		for _, node := range nodes[:limit] {
			fmt.Fprintf(&b, "| %s | %s | %d |\n", escapeTable(node.Label), node.Type, node.RiskScore)
		}
		if len(nodes) > limit {
			fmt.Fprintf(&b, "\n其余 %d 个节点已省略。\n", len(nodes)-limit)
		}
		b.WriteString("\n")
	}

	b.WriteString("## 5. 修复优先级\n\n")
	b.WriteString("1. 优先处理严重和高危漏洞，并在修复后立即复测。\n")
	b.WriteString("2. 对可形成攻击链的漏洞进行组合验证，避免仅修复单点问题。\n")
	b.WriteString("3. 对中低危问题制定整改计划，并持续跟踪漏洞状态。\n")
	b.WriteString("4. 保留修复证据和复测记录，形成可审计的闭环。\n\n")

	b.WriteString("## 6. 免责声明\n\n")
	b.WriteString("本报告基于平台内已记录的数据自动生成，结论应由具备资质的安全人员复核。所有测试活动必须在明确授权范围内进行。\n")
	return b.String()
}

func riskOrder(level string) int {
	order := map[string]int{"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
	if value, ok := order[strings.ToLower(level)]; ok {
		return value
	}
	return 5
}

func severityName(level string) string {
	names := map[string]string{"critical": "严重", "high": "高危", "medium": "中危", "low": "低危", "info": "信息"}
	if name, ok := names[strings.ToLower(level)]; ok {
		return name
	}
	return level
}

func statusName(status string) string {
	names := map[string]string{"open": "待处理", "confirmed": "已确认", "fixed": "已修复", "false_positive": "误报"}
	if name, ok := names[status]; ok {
		return name
	}
	return status
}

func defaultRecommendation(vulnerabilityType string) string {
	value := strings.ToLower(vulnerabilityType)
	switch {
	case strings.Contains(value, "sql"):
		return "使用参数化查询或预编译语句，禁止拼接用户输入，并限制数据库账户权限。"
	case strings.Contains(value, "xss"):
		return "对输出内容进行上下文编码，启用内容安全策略，并对富文本使用可靠的白名单清洗。"
	case strings.Contains(value, "命令"), strings.Contains(value, "rce"):
		return "避免将外部输入传入系统命令；使用参数白名单，并以最低权限运行相关服务。"
	case strings.Contains(value, "越权"), strings.Contains(value, "权限"):
		return "在服务端实施统一鉴权和资源级权限校验，不依赖前端传入的身份或权限信息。"
	default:
		return "根据漏洞成因实施输入校验、权限控制和安全配置加固，修复后执行针对性复测。"
	}
}

func escapeTable(value string) string {
	return strings.ReplaceAll(strings.ReplaceAll(value, "|", "\\|"), "\n", " ")
}
