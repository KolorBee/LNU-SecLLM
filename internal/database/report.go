package database

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Report stores an immutable security report snapshot.
type Report struct {
	ID                 string    `json:"id"`
	Title              string    `json:"title"`
	ConversationID     string    `json:"conversation_id,omitempty"`
	Status             string    `json:"status"`
	RiskLevel          string    `json:"risk_level"`
	VulnerabilityCount int       `json:"vulnerability_count"`
	CriticalCount      int       `json:"critical_count"`
	HighCount          int       `json:"high_count"`
	MediumCount        int       `json:"medium_count"`
	LowCount           int       `json:"low_count"`
	InfoCount          int       `json:"info_count"`
	AttackChainNodes   int       `json:"attack_chain_nodes"`
	ToolExecutionCount int       `json:"tool_execution_count"`
	SummaryJSON        string    `json:"summary_json"`
	ContentMarkdown    string    `json:"content_markdown,omitempty"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
}

func (db *DB) CreateReport(report *Report) (*Report, error) {
	if report.ID == "" {
		report.ID = uuid.New().String()
	}
	if report.Status == "" {
		report.Status = "completed"
	}
	now := time.Now()
	report.CreatedAt = now
	report.UpdatedAt = now

	_, err := db.Exec(`
		INSERT INTO reports (
			id, title, conversation_id, status, risk_level,
			vulnerability_count, critical_count, high_count, medium_count, low_count, info_count,
			attack_chain_nodes, tool_execution_count, summary_json, content_markdown,
			created_at, updated_at
		) VALUES (?, ?, NULLIF(?, ''), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, report.ID, report.Title, report.ConversationID, report.Status, report.RiskLevel,
		report.VulnerabilityCount, report.CriticalCount, report.HighCount, report.MediumCount,
		report.LowCount, report.InfoCount, report.AttackChainNodes, report.ToolExecutionCount,
		report.SummaryJSON, report.ContentMarkdown, report.CreatedAt, report.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("创建报告失败: %w", err)
	}
	return report, nil
}

func (db *DB) GetReport(id string) (*Report, error) {
	var report Report
	var conversationID sql.NullString
	err := db.QueryRow(`
		SELECT id, title, conversation_id, status, risk_level,
		       vulnerability_count, critical_count, high_count, medium_count, low_count, info_count,
		       attack_chain_nodes, tool_execution_count, summary_json, content_markdown,
		       created_at, updated_at
		FROM reports WHERE id = ?
	`, id).Scan(
		&report.ID, &report.Title, &conversationID, &report.Status, &report.RiskLevel,
		&report.VulnerabilityCount, &report.CriticalCount, &report.HighCount,
		&report.MediumCount, &report.LowCount, &report.InfoCount,
		&report.AttackChainNodes, &report.ToolExecutionCount, &report.SummaryJSON,
		&report.ContentMarkdown, &report.CreatedAt, &report.UpdatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("报告不存在")
		}
		return nil, fmt.Errorf("获取报告失败: %w", err)
	}
	if conversationID.Valid {
		report.ConversationID = conversationID.String
	}
	return &report, nil
}

func (db *DB) ListReports(limit, offset int) ([]*Report, int, error) {
	var total int
	if err := db.QueryRow("SELECT COUNT(*) FROM reports").Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("统计报告失败: %w", err)
	}
	rows, err := db.Query(`
		SELECT id, title, conversation_id, status, risk_level,
		       vulnerability_count, critical_count, high_count, medium_count, low_count, info_count,
		       attack_chain_nodes, tool_execution_count, summary_json, created_at, updated_at
		FROM reports ORDER BY created_at DESC LIMIT ? OFFSET ?
	`, limit, offset)
	if err != nil {
		return nil, 0, fmt.Errorf("查询报告列表失败: %w", err)
	}
	defer rows.Close()

	reports := make([]*Report, 0)
	for rows.Next() {
		var report Report
		var conversationID sql.NullString
		if err := rows.Scan(
			&report.ID, &report.Title, &conversationID, &report.Status, &report.RiskLevel,
			&report.VulnerabilityCount, &report.CriticalCount, &report.HighCount,
			&report.MediumCount, &report.LowCount, &report.InfoCount,
			&report.AttackChainNodes, &report.ToolExecutionCount, &report.SummaryJSON,
			&report.CreatedAt, &report.UpdatedAt,
		); err != nil {
			return nil, 0, fmt.Errorf("读取报告列表失败: %w", err)
		}
		if conversationID.Valid {
			report.ConversationID = conversationID.String
		}
		reports = append(reports, &report)
	}
	return reports, total, rows.Err()
}

func (db *DB) DeleteReport(id string) error {
	result, err := db.Exec("DELETE FROM reports WHERE id = ?", id)
	if err != nil {
		return fmt.Errorf("删除报告失败: %w", err)
	}
	affected, err := result.RowsAffected()
	if err == nil && affected == 0 {
		return fmt.Errorf("报告不存在")
	}
	return nil
}
