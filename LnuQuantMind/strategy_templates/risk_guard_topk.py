"""
大盘风控 Top-K 选股策略 (Risk Guard Top-K)
[Native] 核心逻辑：
1. 先做基本面/交易风险硬过滤；
2. 再结合大盘状态自动降仓；
3. 维持 Top-K-Dropout 的低换手优势。
"""

STRATEGY_CONFIG = {
    "class": "RedisRiskGuardTopkStrategy",
    "module_path": "backend.services.engine.qlib_app.utils.extended_strategies",
    "kwargs": {
        "signal": "<PRED>",
        "topk": 50,
        "n_drop": 10,
        "rebalance_days": 3,
        "max_industry_count": 0,
        "industry_cap_ratio": 0.30,
        "market_state_window": 20,
        "exclude_st": True,
        "f_is_st_not": 1,
        "f_listed_days_min": 120,
        "f_limit_up_today_not": 1,
        "f_limit_down_today_not": 1,
        "f_consecutive_limit_up_days_max": 0,
        "f_turnover_rate_min": 0.5,
        "f_turnover_rate_max": 15.0,
        "f_beta_20_max": 1.8,
        "f_float_mv_min": 500000000.0,
        "f_micro_jump_flag_not": 1,
        "market_state_symbol": "SH000300",
    }
}
