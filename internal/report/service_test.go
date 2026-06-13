package report

import (
	"path/filepath"
	"strings"
	"testing"
	"time"

	"cyberstrike-ai/internal/database"
	"go.uber.org/zap"
)

func TestGenerateReportSnapshot(t *testing.T) {
	db, err := database.NewDB(filepath.Join(t.TempDir(), "report-test.db"), zap.NewNop())
	if err != nil {
		t.Fatalf("NewDB() error = %v", err)
	}
	defer db.Close()

	now := time.Now()
	if _, err := db.Exec(
		"INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
		"conversation-1", "测试会话", now, now,
	); err != nil {
		t.Fatalf("insert conversation: %v", err)
	}
	if _, err := db.CreateVulnerability(&database.Vulnerability{
		ConversationID: "conversation-1",
		Title:          "SQL 注入",
		Description:    "登录接口存在注入风险",
		Severity:       "high",
		Status:         "confirmed",
		Type:           "SQL Injection",
		Target:         "https://example.test/login",
	}); err != nil {
		t.Fatalf("CreateVulnerability() error = %v", err)
	}
	if _, err := db.Exec(`
		INSERT INTO tool_executions (id, tool_name, arguments, status, start_time)
		VALUES (?, ?, ?, ?, ?)
	`, "tool-1", "sqlmap", "{}", "success", now); err != nil {
		t.Fatalf("insert tool execution: %v", err)
	}
	if err := db.SaveAttackChainNode("conversation-1", "node-1", "vulnerability", "SQL 注入", "tool-1", "{}", 8); err != nil {
		t.Fatalf("SaveAttackChainNode() error = %v", err)
	}

	generated, err := NewService(db).Generate(GenerateRequest{ConversationID: "conversation-1"})
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if generated.VulnerabilityCount != 1 || generated.HighCount != 1 {
		t.Fatalf("unexpected vulnerability counts: %+v", generated)
	}
	if generated.AttackChainNodes != 1 || generated.ToolExecutionCount != 1 {
		t.Fatalf("unexpected context counts: %+v", generated)
	}
	if generated.RiskLevel != "high" {
		t.Fatalf("RiskLevel = %q, want high", generated.RiskLevel)
	}
	if !strings.Contains(generated.ContentMarkdown, "SQL 注入") ||
		!strings.Contains(generated.ContentMarkdown, "参数化查询") {
		t.Fatalf("generated markdown missing vulnerability details or recommendation:\n%s", generated.ContentMarkdown)
	}

	stored, err := db.GetReport(generated.ID)
	if err != nil {
		t.Fatalf("GetReport() error = %v", err)
	}
	if stored.ContentMarkdown != generated.ContentMarkdown {
		t.Fatal("stored report snapshot differs from generated markdown")
	}
}
