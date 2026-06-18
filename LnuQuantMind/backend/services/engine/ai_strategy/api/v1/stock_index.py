"""策略向导专用股票索引服务。

该服务只读取容器内数据库中的 `stock_daily_latest` 最新交易日快照，
避免策略平台复用研究/实时行情那条外部行情链路。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from backend.shared.database_manager_v2 import get_session
from backend.shared.logging_config import get_logger
from backend.shared.stock_utils import StockCodeUtil

logger = get_logger(__name__)

router = APIRouter(prefix="/stocks", tags=["strategy-stock-index"])

_INDEX_CACHE_TTL_SECONDS = 300
_INDEX_CACHE_MAX_ENTRIES = 4
_INDEX_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_INDEX_LOCK = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_symbol(symbol: str) -> str:
    return StockCodeUtil.to_prefix(symbol)


def _symbol_to_exchange(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    return normalized[:2] if len(normalized) >= 8 else ""


def _symbol_to_code(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    suffix = StockCodeUtil.to_suffix(normalized)
    if "." in suffix:
        return suffix.split(".", 1)[0]
    return normalized


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    cached = _INDEX_CACHE.get(key)
    if not cached:
        return None
    if (now - cached[0]) > _INDEX_CACHE_TTL_SECONDS:
        _INDEX_CACHE.pop(key, None)
        return None
    return cached[1]


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _INDEX_CACHE[key] = (time.monotonic(), payload)
    if len(_INDEX_CACHE) > _INDEX_CACHE_MAX_ENTRIES:
        oldest_key = min(_INDEX_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _INDEX_CACHE.pop(oldest_key, None)


async def _load_stock_index_payload() -> dict[str, Any]:
    async with _INDEX_LOCK:
        async with get_session(read_only=True) as session:
            latest_trade_date = await session.scalar(text("SELECT MAX(trade_date) FROM stock_daily_latest"))
            if latest_trade_date is None:
                raise FileNotFoundError("stock_daily_latest")

            cache_key = str(latest_trade_date)
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached

            result = await session.execute(
                text(
                    """
                    SELECT
                        symbol,
                        COALESCE(stock_name, name, symbol) AS stock_name
                    FROM stock_daily_latest
                    WHERE trade_date = :trade_date
                      AND COALESCE(symbol, '') <> ''
                    ORDER BY symbol
                    """
                ),
                {"trade_date": latest_trade_date},
            )
            rows = result.mappings().all()

    items_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = _normalize_symbol(str(row.get("symbol") or ""))
        if not symbol:
            continue
        name = str(row.get("stock_name") or "").strip() or symbol
        items_map.setdefault(
            symbol,
            {
                "symbol": symbol,
                "code": _symbol_to_code(symbol),
                "name": name,
                "market": _symbol_to_exchange(symbol),
            },
        )

    items = [items_map[key] for key in sorted(items_map.keys())]
    payload = {
        "trade_date": latest_trade_date.isoformat() if hasattr(latest_trade_date, "isoformat") else str(latest_trade_date),
        "items": items,
        "loaded_count": len(items),
    }
    _cache_set(cache_key, payload)
    logger.info("已从 stock_daily_latest 加载策略股票索引: trade_date=%s count=%s", payload["trade_date"], len(items))
    return payload


async def _search_stock_index(keyword: str, limit: int) -> list[dict[str, Any]]:
    payload = await _load_stock_index_payload()
    items = payload.get("items") if isinstance(payload, dict) else []
    if not keyword.strip():
        return []

    k = keyword.strip().lower()
    starts: list[dict[str, Any]] = []
    contains: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            [
                str(item.get("symbol") or "").lower(),
                str(item.get("code") or "").lower(),
                str(item.get("name") or "").lower(),
            ]
        ).strip()
        symbol = str(item.get("symbol") or "").lower()
        code = str(item.get("code") or "").lower()
        if text.startswith(k) or symbol.startswith(k) or code.startswith(k):
            starts.append(item)
        elif k in text:
            contains.append(item)
        if len(starts) >= limit:
            break
    return (starts + contains)[:limit]


@router.get("/search")
async def search_stocks(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(20, ge=1, le=200, description="最大返回数量"),
):
    try:
        results = await _search_stock_index(keyword=q, limit=limit)
    except FileNotFoundError as exc:
        logger.error("策略股票快照表不可用: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="股票索引未就绪，请先确保 stock_daily_latest 已完成同步。",
        ) from exc
    except Exception as exc:
        logger.error("策略股票索引搜索失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"股票搜索失败: {exc}") from exc

    return {
        "query": q,
        "results": results,
        "total": len(results),
        "timestamp": _now_iso(),
        "source": "stock_daily_latest",
    }


@router.get("/search/status")
async def search_status():
    try:
        payload = await _load_stock_index_payload()
    except FileNotFoundError:
        payload = {"trade_date": None, "loaded_count": 0}
    return {
        "status": "ok",
        "timestamp": _now_iso(),
        "index": payload,
    }


@router.get("/index")
async def get_stock_index():
    """返回完整股票索引，供策略向导与回测组件统一读取。"""
    try:
        payload = await _load_stock_index_payload()
    except FileNotFoundError as exc:
        logger.error("stock_daily_latest 不可用: %s", exc)
        raise HTTPException(status_code=503, detail="股票索引未就绪，请先完成 stock_daily_latest 同步。") from exc
    except Exception as exc:
        logger.error("获取策略股票索引失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取股票索引失败: {exc}") from exc

    return {
        "items": payload.get("items", []),
        "total": int(payload.get("loaded_count") or len(payload.get("items") or [])),
        "trade_date": payload.get("trade_date"),
        "timestamp": _now_iso(),
        "source": "stock_daily_latest",
    }
