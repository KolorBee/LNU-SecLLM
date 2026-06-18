POOL_FILE = "/app/user_pools_local/10000001/20260607_142559/stock_pool.txt"

STRATEGY_CONFIG = {
    "class": "RedisWeightStrategy",
    "module_path": "backend.services.engine.qlib_app.utils.recording_strategy",
    "kwargs": {
        "signal": "<PRED>",
        "topk": 10,
        "rebalance_days": 5,
        "pool_file": POOL_FILE,
    },
}
