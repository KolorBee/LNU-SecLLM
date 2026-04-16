package app

import (
	"time"

	"cyberstrike-ai/internal/database"
	"cyberstrike-ai/internal/skills"
)

// skillStatsDBAdapter 将database.DB适配为skills.SkillStatsStorage接口
type skillStatsDBAdapter struct {
	db *database.DB
}

// UpdateSkillStats 更新Skills统计信息
func (a *skillStatsDBAdapter) UpdateSkillStats(skillName string, totalCalls, successCalls, failedCalls int, lastCallTime *time.Time) error {
	return a.db.UpdateSkillStats(skillName, totalCalls, successCalls, failedCalls, lastCallTime)
}

// LoadSkillStats 加载所有Skills统计信息
func (a *skillStatsDBAdapter) LoadSkillStats() (map[string]*skills.SkillStats, error) {
	dbStats, err := a.db.LoadSkillStats()
	if err != nil {
		return nil, err
	}

	// 转换为skills.SkillStats格式
	result := make(map[string]*skills.SkillStats)
	for name, stat := range dbStats {
		result[name] = &skills.SkillStats{
			SkillName:    stat.SkillName,
			TotalCalls:   stat.TotalCalls,
			SuccessCalls: stat.SuccessCalls,
			FailedCalls:  stat.FailedCalls,
			LastCallTime: stat.LastCallTime,
		}
	}

	return result, nil
}
