package skills

import (
	"context"
	"fmt"
	"strings"
	"time"

	"cyberstrike-ai/internal/mcp"
	"cyberstrike-ai/internal/mcp/builtin"

	"go.uber.org/zap"
)

// RegisterSkillsTool 注册Skills工具到MCP服务器
func RegisterSkillsTool(
	mcpServer *mcp.Server,
	manager *Manager,
	logger *zap.Logger,
) {
	RegisterSkillsToolWithStorage(mcpServer, manager, nil, logger)
}

// RegisterSkillsToolWithStorage 注册Skills工具到MCP服务器（带存储支持）
func RegisterSkillsToolWithStorage(
	mcpServer *mcp.Server,
	manager *Manager,
	storage SkillStatsStorage,
	logger *zap.Logger,
) {
	// 注册第一个工具：获取所有可用的skills列表
	listSkillsTool := mcp.Tool{
		Name:             builtin.ToolListSkills,
		Description:      "获取所有可用的skills列表。Skills是专业知识文档，可以在执行任务前阅读以获取相关专业知识。使用此工具可以查看系统中所有可用的skills，然后使用read_skill工具读取特定skill的内容。",
		ShortDescription: "获取所有可用的skills列表",
		InputSchema: map[string]interface{}{
			"type":       "object",
			"properties": map[string]interface{}{},
			"required":   []string{},
		},
	}

	listSkillsHandler := func(ctx context.Context, args map[string]interface{}) (*mcp.ToolResult, error) {
		skills, err := manager.ListSkills()
		if err != nil {
			logger.Error("获取skills列表失败", zap.Error(err))
			return &mcp.ToolResult{
				Content: []mcp.Content{
					{
						Type: "text",
						Text: fmt.Sprintf("获取skills列表失败: %v", err),
					},
				},
				IsError: true,
			}, nil
		}

		if len(skills) == 0 {
			return &mcp.ToolResult{
				Content: []mcp.Content{
					{
						Type: "text",
						Text: "当前没有可用的skills。\n\nSkills是专业知识文档，可以在执行任务前阅读以获取相关专业知识。你可以在skills目录下创建新的skill。",
					},
				},
				IsError: false,
			}, nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("共有 %d 个可用的skills：\n\n", len(skills)))
		for i, skill := range skills {
			result.WriteString(fmt.Sprintf("%d. %s\n", i+1, skill))
		}
		result.WriteString("\n使用 read_skill 工具可以读取特定skill的详细内容。\n")
		result.WriteString("例如：read_skill(skill_name=\"sql-injection-testing\")")

		return &mcp.ToolResult{
			Content: []mcp.Content{
				{
					Type: "text",
					Text: result.String(),
				},
			},
			IsError: false,
		}, nil
	}

	mcpServer.RegisterTool(listSkillsTool, listSkillsHandler)
	logger.Info("注册skills列表工具成功")

	// 注册第二个工具：读取特定skill的内容
	readSkillTool := mcp.Tool{
		Name:             builtin.ToolReadSkill,
		Description:      "读取指定skill的详细内容。Skills是专业知识文档，包含测试方法、工具使用、最佳实践等。在执行相关任务前，可以调用此工具读取相关skill的内容，以获取专业知识和指导。",
		ShortDescription: "读取指定skill的详细内容",
		InputSchema: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"skill_name": map[string]interface{}{
					"type":        "string",
					"description": "要读取的skill名称（必需）。可以使用list_skills工具获取所有可用的skill名称。",
				},
			},
			"required": []string{"skill_name"},
		},
	}

	readSkillHandler := func(ctx context.Context, args map[string]interface{}) (*mcp.ToolResult, error) {
		skillName, ok := args["skill_name"].(string)
		if !ok || skillName == "" {
			return &mcp.ToolResult{
				Content: []mcp.Content{
					{
						Type: "text",
						Text: "错误: skill_name 参数必需且不能为空。请使用list_skills工具获取所有可用的skill名称。",
					},
				},
				IsError: true,
			}, nil
		}

		skill, err := manager.LoadSkill(skillName)
		failed := err != nil
		now := time.Now()

		// 记录调用统计
		if storage != nil {
			totalCalls := 1
			successCalls := 0
			failedCalls := 0
			if failed {
				failedCalls = 1
			} else {
				successCalls = 1
			}
			if err := storage.UpdateSkillStats(skillName, totalCalls, successCalls, failedCalls, &now); err != nil {
				logger.Warn("保存Skills统计信息失败", zap.String("skill", skillName), zap.Error(err))
			} else {
				logger.Info("Skills统计信息已更新",
					zap.String("skill", skillName),
					zap.Int("totalCalls", totalCalls),
					zap.Int("successCalls", successCalls),
					zap.Int("failedCalls", failedCalls))
			}
		} else {
			logger.Warn("Skills统计存储未配置，无法记录调用统计", zap.String("skill", skillName))
		}

		if err != nil {
			logger.Warn("读取skill失败", zap.String("skill", skillName), zap.Error(err))
			return &mcp.ToolResult{
				Content: []mcp.Content{
					{
						Type: "text",
						Text: fmt.Sprintf("读取skill失败: %v\n\n请使用list_skills工具确认skill名称是否正确。", err),
					},
				},
				IsError: true,
			}, nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("## Skill: %s\n\n", skill.Name))
		if skill.Description != "" {
			result.WriteString(fmt.Sprintf("**描述**: %s\n\n", skill.Description))
		}
		result.WriteString("---\n\n")
		result.WriteString(skill.Content)
		result.WriteString("\n\n---\n\n")
		result.WriteString(fmt.Sprintf("*Skill路径: %s*", skill.Path))

		return &mcp.ToolResult{
			Content: []mcp.Content{
				{
					Type: "text",
					Text: result.String(),
				},
			},
			IsError: false,
		}, nil
	}

	mcpServer.RegisterTool(readSkillTool, readSkillHandler)
	logger.Info("注册skill读取工具成功")
}

// SkillStatsStorage Skills统计存储接口
type SkillStatsStorage interface {
	UpdateSkillStats(skillName string, totalCalls, successCalls, failedCalls int, lastCallTime *time.Time) error
	LoadSkillStats() (map[string]*SkillStats, error)
}

// SkillStats Skills统计信息
type SkillStats struct {
	SkillName    string
	TotalCalls   int
	SuccessCalls int
	FailedCalls  int
	LastCallTime *time.Time
}
