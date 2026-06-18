"""
价值成长策略 (Value Growth)
[Native] 核心逻辑：在 TopK 选股基础上叠加基本面过滤（剔除 ST + 市值区间 + 估值 + 盈利能力）。
"""
STRATEGY_CONFIG = {
    "class": "RedisRecordingStrategy",
    "kwargs": {
        "signal": "<PRED>",
        "topk": 30,
        "n_drop": 5,
        "f_is_st_not": 1,
        "f_total_mv_min": 1e9,
        "f_total_mv_max": 5e10,
        "f_pe_ttm_max": 25,
        "f_roe_min": 0.12,
        "f_listed_days_min": 365,
    },
}
