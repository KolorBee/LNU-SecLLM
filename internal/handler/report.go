package handler

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"cyberstrike-ai/internal/database"
	reportservice "cyberstrike-ai/internal/report"
	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

type ReportHandler struct {
	db      *database.DB
	service *reportservice.Service
	logger  *zap.Logger
}

func NewReportHandler(db *database.DB, logger *zap.Logger) *ReportHandler {
	return &ReportHandler{db: db, service: reportservice.NewService(db), logger: logger}
}

func (h *ReportHandler) Create(c *gin.Context) {
	var req reportservice.GenerateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	report, err := h.service.Generate(req)
	if err != nil {
		h.logger.Error("生成安全报告失败", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, report)
}

func (h *ReportHandler) List(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	if offset < 0 {
		offset = 0
	}
	reports, total, err := h.db.ListReports(limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"reports": reports, "total": total})
}

func (h *ReportHandler) Get(c *gin.Context) {
	report, err := h.db.GetReport(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, report)
}

func (h *ReportHandler) DownloadMarkdown(c *gin.Context) {
	report, err := h.db.GetReport(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	filename := sanitizeFilename(report.Title) + ".md"
	c.Header("Content-Type", "text/markdown; charset=utf-8")
	c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, filename))
	c.String(http.StatusOK, report.ContentMarkdown)
}

func (h *ReportHandler) Delete(c *gin.Context) {
	if err := h.db.DeleteReport(c.Param("id")); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "删除成功"})
}

func sanitizeFilename(value string) string {
	replacer := strings.NewReplacer("/", "-", "\\", "-", ":", "-", "*", "-", "?", "-", `"`, "-", "<", "-", ">", "-", "|", "-")
	value = strings.TrimSpace(replacer.Replace(value))
	if value == "" {
		return "security-report"
	}
	return value
}
