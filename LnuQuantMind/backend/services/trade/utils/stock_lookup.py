import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Redis Hash Key for stock names
STOCK_NAME_CACHE_KEY = "quantmind:stock_names"

_STOCK_SYMBOL_NAME_MAP = None

def _load_from_file() -> dict:
    """Load symbol names from local JSON file"""
    possible_paths = [
        "data/stocks/stocks_index.json",
        "/app/data/stocks/stocks_index.json",
        "../data/stocks/stocks_index.json",
        "/data/stocks/stocks_index.json",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        item["symbol"]: item["name"]
                        for item in data.get("items", [])
                        if "symbol" in item and "name" in item
                    }
            except Exception as e:
                logger.warning(f"Failed to load stock index from {path}: {e}")
    return {}

def warmup_stock_cache():
    """Warmup Redis cache with all stock names from file"""
    try:
        from backend.services.trade.redis_client import get_redis
        redis = get_redis()
        if not redis.client:
            logger.warning("Redis client not connected, skipping warmup")
            return

        # Check if already warmed up (optional: overwrite if stale)
        # For simplicity, we always warmup on startup to ensure consistency
        mapping = _load_from_file()
        if mapping:
            # Use HMSET (or hset in newer redis-py) to load all at once
            redis.client.hset(STOCK_NAME_CACHE_KEY, mapping=mapping)
            logger.info(f"Successfully warmed up {len(mapping)} stocks in Redis")
        else:
            logger.warning("No stocks found to warmup in index file")
    except Exception as e:
        logger.error(f"Failed to warmup stock cache: {e}")

def lookup_symbol_name(symbol: str) -> str | None:
    """Lookup symbol name from memory, then Redis, then file"""
    global _STOCK_SYMBOL_NAME_MAP

    # 1. Local Memory Cache (Fastest)
    if _STOCK_SYMBOL_NAME_MAP is not None:
        name = _STOCK_SYMBOL_NAME_MAP.get(symbol)
        if name:
            return name

    # 2. Redis Cache (Fast)
    try:
        from backend.services.trade.redis_client import get_redis
        redis = get_redis()
        if redis.client:
            name = redis.client.hget(STOCK_NAME_CACHE_KEY, symbol)
            if name:
                # Update local cache if not set
                if _STOCK_SYMBOL_NAME_MAP is None:
                    _STOCK_SYMBOL_NAME_MAP = {}
                _STOCK_SYMBOL_NAME_MAP[symbol] = name
                return name
    except Exception as e:
        logger.warning(f"Redis lookup failed for {symbol}: {e}")

    # 3. Fallback to File (Slow)
    if _STOCK_SYMBOL_NAME_MAP is None:
        mapping = _load_from_file()
        _STOCK_SYMBOL_NAME_MAP = mapping

        # Try to update Redis while we're at it if we found the mapping
        if mapping:
            try:
                from backend.services.trade.redis_client import get_redis
                redis = get_redis()
                if redis.client:
                    redis.client.hset(STOCK_NAME_CACHE_KEY, mapping=mapping)
            except Exception:
                pass

    return _STOCK_SYMBOL_NAME_MAP.get(symbol)
