"""股票搜索接口（数据库快照版）

目标：
1. 避免前端直连第三方行情服务产生 CORS 问题。
2. 直接从 `stock_daily_latest` 最新交易日读取全市场股票索引，杜绝硬编码和本地 JSON 依赖。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from backend.shared.database_manager_v2 import get_session
from backend.shared.logging_config import get_logger
from backend.shared.stock_utils import StockCodeUtil

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/stocks", tags=["Stocks"])

_INDEX_CACHE_TTL_SECONDS = int(os.getenv("STOCK_INDEX_CACHE_TTL_SECONDS", "300"))
_INDEX_CACHE_MAX_ENTRIES = int(os.getenv("STOCK_INDEX_CACHE_MAX_ENTRIES", "4"))
_INDEX_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_INDEX_LOCK = asyncio.Lock()
_MONEY_UNIT_TO_YI = 1.0 / 100000000.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class StockIndexItem:
    symbol: str
    code: str
    exchange: str
    name: str
    market_cap: float = 0.0
    pe: float = 0.0
    price: float = 0.0

    def searchable_text(self) -> str:
        return " ".join([self.symbol.lower(), self.code.lower(), self.name.lower()]).strip()

    def to_result(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "code": self.code,
            "name": self.name,
            "market": self.exchange,
            "marketCap": self.market_cap,
            "market_cap": self.market_cap,
            "pe": self.pe,
            "price": self.price,
            "closePrice": self.price,
        }


def _normalize_symbol(symbol: str) -> str:
    return StockCodeUtil.to_prefix(symbol)


def _symbol_to_exchange(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    return normalized[:2] if len(normalized) >= 8 else ""


def _symbol_to_code(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    suffix = StockCodeUtil.to_suffix(normalized)
    return suffix.split(".", 1)[0] if "." in suffix else normalized


def _cache_get(key: str) -> dict[str, Any] | None:
    now = asyncio.get_event_loop().time()
    cached = _INDEX_CACHE.get(key)
    if not cached:
        return None
    if (now - cached[0]) > _INDEX_CACHE_TTL_SECONDS:
        _INDEX_CACHE.pop(key, None)
        return None
    return cached[1]


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _INDEX_CACHE[key] = (asyncio.get_event_loop().time(), payload)
    if len(_INDEX_CACHE) > _INDEX_CACHE_MAX_ENTRIES:
        oldest_key = min(_INDEX_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _INDEX_CACHE.pop(oldest_key, None)


async def _load_stock_index_payload() -> dict[str, Any]:
    async with get_session(read_only=True) as session:
        latest_trade_date = await session.scalar(text("SELECT MAX(trade_date) FROM stock_daily_latest"))
        if latest_trade_date is None:
            raise FileNotFoundError("stock_daily_latest")

        cache_key = str(latest_trade_date)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        columns_res = await session.execute(text("SELECT * FROM stock_daily_latest LIMIT 0"))
        columns = {str(name).lower() for name in columns_res.keys()}
        name_col = "stock_name" if "stock_name" in columns else ("name" if "name" in columns else None)
        market_cap_col = "total_mv" if "total_mv" in columns else ("market_cap" if "market_cap" in columns else None)
        pe_col = "pe_ttm" if "pe_ttm" in columns else ("pe" if "pe" in columns else None)
        close_col = "close" if "close" in columns else None
        adj_factor_col = "adj_factor" if "adj_factor" in columns else None

        select_fields = [
            "symbol",
            f"COALESCE({name_col}, '') AS stock_name" if name_col else "'' AS stock_name",
            f"COALESCE({market_cap_col}, 0) AS market_cap_raw" if market_cap_col else "0 AS market_cap_raw",
            f"COALESCE({pe_col}, 0) AS pe" if pe_col else "0 AS pe",
            f"COALESCE({close_col}, 0) AS close_price" if close_col else "0 AS close_price",
            f"COALESCE({adj_factor_col}, 1) AS adj_factor" if adj_factor_col else "1 AS adj_factor",
        ]

        result = await session.execute(
            text(
                f"""
                SELECT
                    {", ".join(select_fields)}
                FROM stock_daily_latest
                WHERE trade_date = :trade_date
                  AND COALESCE(symbol, '') <> ''
                ORDER BY symbol
                """
            ),
            {"trade_date": latest_trade_date},
        )
        rows = result.mappings().all()

    items_map: dict[str, StockIndexItem] = {}
    for row in rows:
        symbol = _normalize_symbol(str(row.get("symbol") or ""))
        if not symbol:
            continue
        name = str(row.get("stock_name") or "").strip() or symbol
        market_cap_raw = float(row.get("market_cap_raw") or 0)
        pe = float(row.get("pe") or 0)
        close_price_raw = float(row.get("close_price") or 0)
        adj_factor = float(row.get("adj_factor") or 1) or 1
        exchange = _symbol_to_exchange(symbol)
        code = _symbol_to_code(symbol)
        items_map.setdefault(
            symbol,
            StockIndexItem(
                symbol=symbol,
                code=code,
                exchange=exchange,
                name=name,
                market_cap=round(market_cap_raw * _MONEY_UNIT_TO_YI, 2) if market_cap_raw else 0.0,
                pe=round(pe, 2) if pe else 0.0,
                price=round(close_price_raw / adj_factor, 2) if close_price_raw else 0.0,
            ),
        )

    items = [items_map[key] for key in sorted(items_map.keys())]
    payload = {
        "trade_date": latest_trade_date.isoformat() if hasattr(latest_trade_date, "isoformat") else str(latest_trade_date),
        "items": [item.to_result() for item in items],
        "loaded_count": len(items),
    }
    _cache_set(cache_key, payload)
    logger.info("已从 stock_daily_latest 加载股票索引: trade_date=%s count=%s", payload["trade_date"], len(items))
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
        logger.error("股票快照表不可用: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="股票索引未就绪，请先确保 stock_daily_latest 已完成同步。",
        ) from exc
    except Exception as exc:
        logger.error("股票索引搜索失败: %s", exc, exc_info=True)
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
    """返回完整股票索引，供前端独立打包后统一读取。"""
    try:
        payload = await _load_stock_index_payload()
    except FileNotFoundError as exc:
        logger.error("stock_daily_latest 不可用: %s", exc)
        raise HTTPException(status_code=503, detail="股票索引未就绪，请先完成 stock_daily_latest 同步。") from exc
    except Exception as exc:
        logger.error("获取股票索引失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取股票索引失败: {exc}") from exc

    return {
        "items": payload.get("items", []),
        "total": int(payload.get("loaded_count") or len(payload.get("items") or [])),
        "trade_date": payload.get("trade_date"),
        "timestamp": _now_iso(),
        "source": "stock_daily_latest",
    }
