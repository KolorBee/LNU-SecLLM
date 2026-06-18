import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, File, UploadFile
from pydantic import BaseModel

from backend.services.trade.deps import AuthContext, get_auth_context, get_redis
from backend.services.trade.redis_client import RedisClient
from backend.services.trade.simulation.services.fund_snapshot_service import (
    SimulationFundSnapshotService,
)
from backend.services.trade.simulation.models.corporate_action import (
    SimulationCorporateAction,
)
from backend.services.trade.simulation.models.account_daily import (
    SimulationAccountDaily,
)
from backend.services.trade.simulation.models.cash_ledger import (
    SimulationCashLedger,
)
from backend.services.trade.simulation.models.fill import (
    SimulationFill,
)
from backend.services.trade.simulation.models.position_daily import (
    SimulationPositionDaily,
)
from backend.services.trade.simulation.models.position_lot import (
    SimulationPositionLot,
)
from backend.services.trade.simulation.models.rebalance_job import (
    SimulationRebalanceJob,
)
from backend.services.trade.simulation.services.corporate_action_service import (
    SimulationCorporateActionService,
)
from backend.services.trade.simulation.services.projection_service import (
    SimulationProjectionService,
)
from backend.services.trade.simulation.services.migration_service import (
    SimulationMigrationService,
)
from backend.services.trade.simulation.services.seed_service import (
    SimulationSeedService,
)
from backend.services.trade.simulation.services.simulation_manager import (
    SimulationAccountManager,
)
from backend.services.trade.simulation.services.ocr_service import SimulationOCRService
from backend.services.trade.trade_config import settings
from backend.shared.database_manager_v2 import get_db_manager, get_session
from backend.shared.trade_account_cache import write_json_cache, write_trade_account_cache
from backend.shared.trade_redis_keys import normalize_trade_user_id
from backend.shared.stock_utils import StockCodeUtil
import logging
import httpx
from sqlalchemy import select, text
from backend.shared.auth import get_internal_call_secret

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_latest_price(symbol: str) -> float:
    """
    获取股票最新价格逻辑：
    1. 优先尝试行情服务实时数据
    2. 如果失败或数据为0，查询数据库 stock_daily_latest 获取最后一天收盘价
    """
    market_url = settings.MARKET_DATA_SERVICE_URL.rstrip("/")
    price = 0.0
    raw_symbol = str(symbol or "").strip().upper()
    prefix_symbol = raw_symbol
    suffix_symbol = raw_symbol
    if raw_symbol.endswith((".SH", ".SZ", ".BJ")) and len(raw_symbol) > 3:
        prefix_symbol = f"{raw_symbol[-2:]}{raw_symbol[:-3]}"
    elif raw_symbol.startswith(("SH", "SZ", "BJ")) and len(raw_symbol) > 2:
        suffix_symbol = f"{raw_symbol[2:]}.{raw_symbol[:2]}"

    # Level 1: 实时行情
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            headers = {"X-Internal-Call": get_internal_call_secret()}
            for candidate in [raw_symbol, prefix_symbol, suffix_symbol]:
                if not candidate:
                    continue
                resp = await client.get(
                    f"{market_url}/api/v1/quotes/{candidate}", headers=headers
                )
                if resp.status_code != 200:
                    continue
                q_data = resp.json()
                price = float(
                    q_data.get("current_price") or q_data.get("last_price") or 0
                )
                if price > 0:
                    break
    except Exception as e:
        logger.warning(f"Failed to fetch real-time price for {raw_symbol}: {e}")

    # Level 2: 数据库兜底
    if price <= 0:
        try:
            db_manager = get_db_manager()
            # 数据库 stock_daily_latest 使用 Prefix 格式 (SH600191)
            query = text("""
                SELECT close, adj_factor FROM stock_daily_latest
                WHERE symbol = :symbol
                ORDER BY trade_date DESC LIMIT 1
            """)

            async with db_manager.get_master_session() as session:
                result = await session.execute(query, {"symbol": prefix_symbol})
                row = result.fetchone()
                if not row and suffix_symbol != prefix_symbol:
                    result = await session.execute(query, {"symbol": suffix_symbol})
                    row = result.fetchone()
                if row:
                    hfq_close = float(row[0])
                    adj_factor = float(row[1] or 1.0)
                    # 计算名义价格 (除权价)
                    price = hfq_close / adj_factor if adj_factor > 0 else hfq_close
                    logger.info(
                        f"Fallback to DB nominal price for {raw_symbol}: {price} (Hfq: {hfq_close}, Adj: {adj_factor})"
                    )
        except Exception as e:
            logger.error(f"Database fallback failed for {raw_symbol}: {e}")

    return price


async def _resolve_symbol_by_name(name: str) -> Optional[str]:
    """
    通过股票名称反查标准 Prefix 代码
    """
    if not name:
        return None

    try:
        db_manager = get_db_manager()
        # 清理名称中的特殊字符，如 *ST
        clean_name = name.replace("*", "").strip()
        query = text("""
            SELECT symbol FROM stock_daily_latest 
            WHERE stock_name LIKE :name
            ORDER BY trade_date DESC LIMIT 1
        """)

        async with db_manager.get_master_session() as session:
            # 先试完全匹配
            result = await session.execute(query, {"name": f"%{clean_name}%"})
            row = result.fetchone()
            if row:
                return row[0]
    except Exception as e:
        logger.error(f"Failed to resolve symbol for name {name}: {e}")

    return None


async def _build_realtime_positions_from_db(
    *,
    tenant_id: str,
    user_id: int,
    since_at: Optional[datetime] = None,
) -> tuple[dict[str, dict[str, float]], float]:
    """[DEPRECATED] 从 sim_trades 聚合当前持仓，并用最新行情重算持仓市值。支持多空双向。
    此函数仅用于审计兼容（account-audit 的 legacy_trade_aggregate 对照源），
    不应在常规读路径中调用。常规持仓查询请使用 simulation_position_lots 投影。"""
    since_naive = None
    if isinstance(since_at, datetime):
        since_naive = (
            since_at.replace(tzinfo=None)
            if since_at.tzinfo is None
            else since_at.astimezone().replace(tzinfo=None)
        )

    base_filter = "WHERE tenant_id = :tenant_id AND user_id = :user_id"
    extra_filter = ""
    params: dict = {"tenant_id": tenant_id, "user_id": user_id}
    if since_naive is not None:
        extra_filter = " AND executed_at >= :since_at"
        params["since_at"] = since_naive

    # 多头净量：buy_to_open 增仓 / sell_to_close 平仓
    # trade_action 为空时（旧数据）保持原先 buy=+/sell=- 逻辑
    long_sql = f"""
        SELECT symbol,
               SUM(CASE
                       WHEN trade_action IN ('buy_to_open', 'buy') OR (trade_action IS NULL AND side = 'buy')
                           THEN quantity
                       WHEN trade_action IN ('sell_to_close') OR (trade_action IS NULL AND side = 'sell')
                           THEN -quantity
                       ELSE 0
                   END) AS volume
        FROM sim_trades
        {base_filter}{extra_filter}
        GROUP BY symbol
        HAVING SUM(CASE
                       WHEN trade_action IN ('buy_to_open', 'buy') OR (trade_action IS NULL AND side = 'buy')
                           THEN quantity
                       WHEN trade_action IN ('sell_to_close') OR (trade_action IS NULL AND side = 'sell')
                           THEN -quantity
                       ELSE 0
                   END) > 0.000001
        ORDER BY symbol
    """

    # 空头净量：sell_to_open 开空 / buy_to_close 平空
    short_sql = f"""
        SELECT symbol,
               SUM(CASE
                       WHEN trade_action = 'sell_to_open' THEN quantity
                       WHEN trade_action = 'buy_to_close' THEN -quantity
                       ELSE 0
                   END) AS volume
        FROM sim_trades
        {base_filter}{extra_filter}
          AND trade_action IN ('sell_to_open', 'buy_to_close')
        GROUP BY symbol
        HAVING SUM(CASE
                       WHEN trade_action = 'sell_to_open' THEN quantity
                       WHEN trade_action = 'buy_to_close' THEN -quantity
                       ELSE 0
                   END) > 0.000001
        ORDER BY symbol
    """

    async with get_session(read_only=True) as session:
        long_rows = (await session.execute(text(long_sql), params)).mappings().all()
        short_rows = (await session.execute(text(short_sql), params)).mappings().all()

    positions: dict[str, dict[str, float]] = {}
    total_market_value = 0.0

    long_candidates: list[tuple[str, float]] = []
    short_candidates: list[tuple[str, float]] = []
    symbols: set[str] = set()

    for row in long_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        volume = float(row.get("volume") or 0.0)
        if not symbol or volume <= 0:
            continue
        long_candidates.append((symbol, volume))
        symbols.add(symbol)

    for row in short_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        volume = float(row.get("volume") or 0.0)
        if not symbol or volume <= 0:
            continue
        short_candidates.append((symbol, volume))
        symbols.add(symbol)

    price_pairs = await asyncio.gather(
        *[_get_latest_price(sym) for sym in sorted(symbols)],
        return_exceptions=True,
    )
    latest_price_map: dict[str, float] = {}
    for sym, price in zip(sorted(symbols), price_pairs):
        latest_price_map[sym] = float(price) if isinstance(price, (int, float)) else 0.0

    for symbol, volume in long_candidates:
        last_price = float(latest_price_map.get(symbol) or 0.0)
        if last_price <= 0:
            continue
        market_value = round(last_price * volume, 2)
        positions[symbol] = {
            "volume": volume,
            "available_volume": volume,
            "price": round(last_price, 4),
            "last_price": round(last_price, 4),
            "market_value": market_value,
            "side": "long",
        }
        total_market_value += market_value

    for symbol, volume in short_candidates:
        last_price = float(latest_price_map.get(symbol) or 0.0)
        if last_price <= 0:
            continue
        market_value = round(last_price * volume, 2)
        key = f"{symbol}:short"
        positions[key] = {
            "symbol": symbol,
            "volume": volume,
            "available_volume": volume,
            "price": round(last_price, 4),
            "last_price": round(last_price, 4),
            "market_value": market_value,
            "side": "short",
        }
        total_market_value -= market_value

    return positions, round(total_market_value, 2)


async def _build_realtime_positions_from_trade_history(
    *,
    tenant_id: str,
    user_id: str,
    since_at: Optional[datetime] = None,
    allow_legacy_fallback: bool = False,
) -> tuple[dict[str, dict[str, float]], float, str]:
    """优先从 simulation_fills 聚合当前持仓；默认不再隐式回退 legacy sim_trades。"""
    since_naive = None
    if isinstance(since_at, datetime):
        since_naive = (
            since_at.replace(tzinfo=None)
            if since_at.tzinfo is None
            else since_at.astimezone().replace(tzinfo=None)
        )

    async with get_session(read_only=True) as session:
        stmt = select(SimulationFill).where(
            SimulationFill.tenant_id == tenant_id,
            SimulationFill.user_id == str(user_id),
        )
        if since_naive is not None:
            stmt = stmt.where(SimulationFill.executed_at >= since_naive)
        stmt = stmt.order_by(SimulationFill.executed_at.asc(), SimulationFill.id.asc())
        fills = list((await session.execute(stmt)).scalars().all())

    if fills:
        long_positions: dict[str, float] = {}
        short_positions: dict[str, float] = {}
        symbols: set[str] = set()

        for fill in fills:
            symbol = str(fill.symbol or "").strip().upper()
            if not symbol:
                continue
            symbols.add(symbol)
            quantity = float(fill.fill_quantity or 0.0)
            if quantity <= 0:
                continue
            side = str(fill.side or "").strip().lower()
            trade_action = str(fill.trade_action or "").strip().lower()
            position_side = str(fill.position_side or "long").strip().lower()

            if position_side == "short":
                if trade_action == "sell_to_open":
                    short_positions[symbol] = short_positions.get(symbol, 0.0) + quantity
                elif trade_action == "buy_to_close":
                    short_positions[symbol] = max(
                        0.0,
                        short_positions.get(symbol, 0.0) - quantity,
                    )
                continue

            if trade_action in {"buy_to_open", "buy"} or (
                not trade_action and side == "buy"
            ):
                long_positions[symbol] = long_positions.get(symbol, 0.0) + quantity
            elif trade_action in {"sell_to_close"} or (
                not trade_action and side == "sell"
            ):
                long_positions[symbol] = max(
                    0.0,
                    long_positions.get(symbol, 0.0) - quantity,
                )

        price_pairs = await asyncio.gather(
            *[_get_latest_price(sym) for sym in sorted(symbols)],
            return_exceptions=True,
        )
        latest_price_map: dict[str, float] = {}
        for sym, price in zip(sorted(symbols), price_pairs):
            latest_price_map[sym] = float(price) if isinstance(price, (int, float)) else 0.0

        positions: dict[str, dict[str, float]] = {}
        total_market_value = 0.0
        for symbol, volume in sorted(long_positions.items()):
            if volume <= 0:
                continue
            last_price = float(latest_price_map.get(symbol) or 0.0)
            if last_price <= 0:
                continue
            market_value = round(last_price * volume, 2)
            positions[symbol] = {
                "symbol": symbol,
                "volume": round(volume, 6),
                "available_volume": round(volume, 6),
                "price": round(last_price, 4),
                "last_price": round(last_price, 4),
                "market_value": market_value,
                "side": "long",
            }
            total_market_value += market_value

        for symbol, volume in sorted(short_positions.items()):
            if volume <= 0:
                continue
            last_price = float(latest_price_map.get(symbol) or 0.0)
            if last_price <= 0:
                continue
            market_value = round(last_price * volume, 2)
            key = f"{symbol}:short"
            positions[key] = {
                "symbol": symbol,
                "volume": round(volume, 6),
                "available_volume": round(volume, 6),
                "price": round(last_price, 4),
                "last_price": round(last_price, 4),
                "market_value": market_value,
                "side": "short",
            }
            total_market_value -= market_value

        return positions, round(total_market_value, 2), "simulation_fill_aggregate"

    if not allow_legacy_fallback:
        return {}, 0.0, "trade_history_aggregate_empty"

    try:
        legacy_user_id = int(str(user_id))
    except (TypeError, ValueError):
        return {}, 0.0, "trade_history_aggregate_empty"
    legacy_positions, legacy_market_value = await _build_realtime_positions_from_db(
        tenant_id=tenant_id,
        user_id=legacy_user_id,
        since_at=since_at,
    )
    return legacy_positions, legacy_market_value, "legacy_trade_aggregate"


def _compute_market_value_from_positions(
    positions: dict[str, dict[str, float]],
) -> float:
    total_market_value = 0.0
    for pos in positions.values():
        if not isinstance(pos, dict):
            continue
        mv = float(pos.get("market_value") or 0.0)
        side = str(pos.get("side") or "long").strip().lower()
        total_market_value += -mv if side == "short" else mv
    return round(total_market_value, 2)


def _is_cache_payload_structurally_valid(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("positions"), dict):
        return False
    snapshot_at = payload.get("snapshot_at")
    if not isinstance(snapshot_at, str) or not snapshot_at.strip():
        return False
    account_version = payload.get("account_version")
    if not isinstance(account_version, int) or account_version <= 0:
        return False
    required_numeric_keys = (
        "cash",
        "available_cash",
        "frozen_cash",
        "total_asset",
        "liabilities",
        "initial_equity",
    )
    for key in required_numeric_keys:
        value = payload.get(key)
        if not isinstance(value, (int, float)):
            return False
    return True


def _persist_projection_cache(
    *,
    redis: RedisClient,
    manager: SimulationAccountManager,
    tenant_id: str,
    user_id: str,
    payload: dict[str, Any],
) -> None:
    sim_key = manager._get_key(user_id, tenant_id)
    write_json_cache(redis, sim_key, payload)
    write_trade_account_cache(
        redis,
        tenant_id,
        normalize_trade_user_id(user_id) or str(user_id),
        dict(payload),
    )


def _extract_position_signature(
    positions: dict[str, dict[str, float]] | None,
) -> dict[str, dict[str, float | str]]:
    if not isinstance(positions, dict):
        return {}
    signature: dict[str, dict[str, float | str]] = {}
    for key, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        normalized_key = str(key or "").strip().upper()
        if not normalized_key:
            continue
        signature[normalized_key] = {
            "symbol": str(pos.get("symbol") or normalized_key).strip().upper(),
            "side": str(pos.get("side") or "long").strip().lower(),
            "volume": round(float(pos.get("volume") or 0.0), 6),
            "available_volume": round(float(pos.get("available_volume") or 0.0), 6),
                "market_value": round(float(pos.get("market_value") or 0.0), 2),
                "cost_price": round(float(pos.get("cost_price") or 0.0), 4),
                "frozen_volume": round(float(pos.get("frozen_volume") or 0.0), 6),
            }
    return signature


def _build_source_account_summary(
    *,
    source: str,
    account: Any | None,
    positions: dict[str, dict[str, float]] | None,
    market_value_override: float | None = None,
) -> dict[str, Any]:
    account_dict = account if isinstance(account, dict) else {}
    position_signature = _extract_position_signature(positions)
    market_value = (
        float(market_value_override)
        if market_value_override is not None
        else _compute_market_value_from_positions(positions or {})
        if position_signature
        else float(account_dict.get("market_value") or 0.0)
    )
    cash = float(
        (
            account_dict.get("cash")
            if account_dict
            else getattr(account, "cash", 0.0)
        )
        or 0.0
    )
    available_cash = float(
        (
            account_dict.get("available_cash")
            if account_dict
            else getattr(account, "available_cash", 0.0)
        )
        or cash
    )
    initial_equity = float(
        (
            account_dict.get("initial_equity")
            if account_dict
            else getattr(account, "initial_equity", 0.0)
        )
        or 0.0
    )
    total_asset = float(
        (
            account_dict.get("total_asset")
            if account_dict
            else getattr(account, "total_asset", 0.0)
        )
        or round(cash + market_value, 2)
    )
    return {
        "source": source,
        "cash": round(cash, 2),
        "available_cash": round(available_cash, 2),
        "market_value": round(market_value, 2),
        "total_asset": round(total_asset, 2),
        "initial_equity": round(initial_equity, 2),
        "position_count": len(position_signature),
        "positions": position_signature,
    }


def _build_account_reconcile_diff(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    left_positions = left.get("positions") or {}
    right_positions = right.get("positions") or {}
    left_keys = set(left_positions.keys())
    right_keys = set(right_positions.keys())
    shared_keys = sorted(left_keys & right_keys)
    position_quantity_mismatches: list[dict[str, Any]] = []
    for key in shared_keys:
        left_pos = left_positions.get(key) or {}
        right_pos = right_positions.get(key) or {}
        volume_diff = round(
            float(left_pos.get("volume") or 0.0) - float(right_pos.get("volume") or 0.0),
            6,
        )
        available_diff = round(
            float(left_pos.get("available_volume") or 0.0)
            - float(right_pos.get("available_volume") or 0.0),
            6,
        )
        if abs(volume_diff) > 0.000001 or abs(available_diff) > 0.000001:
            position_quantity_mismatches.append(
                {
                    "position_key": key,
                    "volume_diff": volume_diff,
                    "available_volume_diff": available_diff,
                }
            )

    return {
        "left_source": left.get("source"),
        "right_source": right.get("source"),
        "cash_diff": round(float(left.get("cash") or 0.0) - float(right.get("cash") or 0.0), 2),
        "available_cash_diff": round(
            float(left.get("available_cash") or 0.0) - float(right.get("available_cash") or 0.0),
            2,
        ),
        "market_value_diff": round(
            float(left.get("market_value") or 0.0) - float(right.get("market_value") or 0.0),
            2,
        ),
        "total_asset_diff": round(
            float(left.get("total_asset") or 0.0) - float(right.get("total_asset") or 0.0),
            2,
        ),
        "initial_equity_diff": round(
            float(left.get("initial_equity") or 0.0) - float(right.get("initial_equity") or 0.0),
            2,
        ),
        "position_count_diff": int(left.get("position_count") or 0) - int(right.get("position_count") or 0),
        "positions_only_in_left": sorted(left_keys - right_keys),
        "positions_only_in_right": sorted(right_keys - left_keys),
        "position_quantity_mismatches": position_quantity_mismatches,
    }


def _build_account_reconcile_report(
    *,
    tenant_id: str,
    user_id: str,
    redis_account: dict[str, Any] | None,
    projection_account: Any | None,
    projection_positions: dict[str, dict[str, float]],
    trade_history_positions: dict[str, dict[str, float]],
    trade_history_market_value: float,
    trade_history_source: str = "trade_history_aggregate",
    legacy_trade_history_positions: dict[str, dict[str, float]] | None = None,
    legacy_trade_history_market_value: float = 0.0,
    legacy_trade_history_source: str | None = None,
) -> dict[str, Any]:
    redis_summary = _build_source_account_summary(
        source="redis_cache",
        account=redis_account,
        positions=(redis_account or {}).get("positions") if isinstance(redis_account, dict) else {},
    )
    projection_summary = _build_source_account_summary(
        source="ledger_projection",
        account=projection_account,
        positions=projection_positions,
    )
    trade_history_summary = _build_source_account_summary(
        source=trade_history_source,
        account={
            "cash": float((redis_account or {}).get("cash") or 0.0),
            "available_cash": float((redis_account or {}).get("available_cash") or 0.0),
            "initial_equity": float((redis_account or {}).get("initial_equity") or 0.0),
            "total_asset": round(
                float((redis_account or {}).get("cash") or 0.0)
                + float(trade_history_market_value or 0.0),
                2,
            ),
        },
        positions=trade_history_positions,
        market_value_override=trade_history_market_value,
    )
    sources = {
        "redis_cache": redis_summary,
        "ledger_projection": projection_summary,
        "trade_history_aggregate": trade_history_summary,
    }
    diffs = {
        "redis_vs_projection": _build_account_reconcile_diff(redis_summary, projection_summary),
        "redis_vs_trade_history_aggregate": _build_account_reconcile_diff(
            redis_summary,
            trade_history_summary,
        ),
        "projection_vs_trade_history_aggregate": _build_account_reconcile_diff(
            projection_summary,
            trade_history_summary,
        ),
    }

    if legacy_trade_history_source and legacy_trade_history_positions is not None:
        legacy_trade_history_summary = _build_source_account_summary(
            source=legacy_trade_history_source,
            account={
                "cash": float((redis_account or {}).get("cash") or 0.0),
                "available_cash": float((redis_account or {}).get("available_cash") or 0.0),
                "initial_equity": float((redis_account or {}).get("initial_equity") or 0.0),
                "total_asset": round(
                    float((redis_account or {}).get("cash") or 0.0)
                    + float(legacy_trade_history_market_value or 0.0),
                    2,
                ),
            },
            positions=legacy_trade_history_positions,
            market_value_override=legacy_trade_history_market_value,
        )
        sources["legacy_trade_aggregate"] = legacy_trade_history_summary
        diffs["projection_vs_legacy_trade_aggregate"] = _build_account_reconcile_diff(
            projection_summary,
            legacy_trade_history_summary,
        )
        diffs["redis_vs_legacy_trade_aggregate"] = _build_account_reconcile_diff(
            redis_summary,
            legacy_trade_history_summary,
        )

    return {
        "account_id": SimulationProjectionService.build_account_id(tenant_id, user_id),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "sources": sources,
        "diffs": diffs,
    }


def _build_cache_payload_from_daily_rows(
    *,
    account_row: SimulationAccountDaily,
    position_rows: list[SimulationPositionDaily],
) -> dict[str, object]:
    positions: dict[str, dict[str, float]] = {}
    for row in position_rows:
        side = str(row.position_side or "long").strip().lower()
        key = row.symbol if side == "long" else f"{row.symbol}:short"
        positions[key] = {
            "symbol": row.symbol,
            "volume": float(row.quantity or 0.0),
            "available_volume": float(row.available_quantity or row.quantity or 0.0),
            "frozen_volume": float(row.frozen_quantity or 0.0),
            "price": float(row.close_price or 0.0),
            "last_price": float(row.close_price or 0.0),
            "market_value": float(row.market_value or 0.0),
            "cost_price": float(row.cost_price or 0.0),
            "side": side,
        }

    initial_equity = max(
        0.0,
        float(account_row.total_asset or 0.0) - float(account_row.total_pnl or 0.0),
    )
    return {
        "account_version": int(account_row.snapshot_at.timestamp() * 1000),
        "snapshot_at": account_row.snapshot_at.isoformat(),
        "cash": float(account_row.cash or 0.0),
        "available_cash": float(account_row.available_cash or 0.0),
        "frozen_cash": float(account_row.frozen_cash or 0.0),
        "market_value": float(account_row.long_market_value or 0.0)
        - float(account_row.short_market_value or 0.0),
        "short_market_value": float(account_row.short_market_value or 0.0),
        "total_asset": float(account_row.total_asset or 0.0),
        "liabilities": float(account_row.liabilities or 0.0),
        "equity": float(account_row.equity or account_row.total_asset or 0.0),
        "today_pnl": float(account_row.daily_pnl or 0.0),
        "daily_pnl": float(account_row.daily_pnl or 0.0),
        "total_pnl": float(account_row.total_pnl or 0.0),
        "initial_equity": initial_equity,
        "positions": positions,
        "baseline": {
            "initial_equity": initial_equity,
            "day_open_equity": max(
                0.0,
                float(account_row.total_asset or 0.0) - float(account_row.daily_pnl or 0.0),
            ),
            "month_open_equity": initial_equity,
        },
        "replay_source": "simulation_account_daily",
        "replayed_snapshot_date": account_row.snapshot_date.isoformat(),
        "replayed_snapshot_at": account_row.snapshot_at.isoformat(),
    }


def _build_replay_account_payload(
    account_row: SimulationAccountDaily,
) -> "SimulationFundSnapshotResponse":
    total_asset = float(account_row.total_asset or 0.0)
    total_pnl = float(account_row.total_pnl or 0.0)
    daily_pnl = float(account_row.daily_pnl or 0.0)
    initial_capital = max(0.0, total_asset - total_pnl)
    daily_return_pct = (
        (daily_pnl / initial_capital * 100.0) if initial_capital > 0 else 0.0
    )
    total_return_pct = (
        (total_pnl / initial_capital * 100.0) if initial_capital > 0 else 0.0
    )
    return SimulationFundSnapshotResponse(
        snapshot_date=account_row.snapshot_date,
        total_asset=Decimal(str(account_row.total_asset or 0.0)),
        available_balance=Decimal(str(account_row.available_cash or 0.0)),
        frozen_balance=Decimal(str(account_row.frozen_cash or 0.0)),
        market_value=Decimal(
            str((account_row.long_market_value or 0.0) - (account_row.short_market_value or 0.0))
        ),
        initial_capital=Decimal(str(initial_capital)),
        total_pnl=Decimal(str(total_pnl)),
        today_pnl=Decimal(str(daily_pnl)),
        daily_return_pct=round(daily_return_pct, 6),
        daily_return_ratio=round(daily_return_pct / 100.0, 10),
        total_return_pct=round(total_return_pct, 6),
        total_return_ratio=round(total_return_pct / 100.0, 10),
        source="simulation_account_daily",
    )


def _build_replay_positions_payload(
    position_rows: list[SimulationPositionDaily],
) -> list["SimulationPositionDailyResponse"]:
    return [
        SimulationPositionDailyResponse(
            snapshot_date=row.snapshot_date,
            snapshot_at=row.snapshot_at,
            symbol=row.symbol,
            position_side=row.position_side,
            quantity=float(row.quantity or 0.0),
            available_quantity=float(row.available_quantity or 0.0),
            frozen_quantity=float(row.frozen_quantity or 0.0),
            cost_price=float(row.cost_price or 0.0),
            close_price=float(row.close_price or 0.0),
            market_value=float(row.market_value or 0.0),
            unrealized_pnl=float(row.unrealized_pnl or 0.0),
        )
        for row in position_rows
    ]


def _derive_seed_initial_equity_from_positions(
    *,
    cash: float,
    positions: dict[str, dict[str, float]],
) -> float | None:
    """Estimate baseline equity from Redis-seeded holdings when no成交历史 is available.

    仅在纯 Redis 持仓回退场景使用：
    - 多头仓位按 cost_price * volume 估算成本
    - 一旦遇到空头或缺少成本价的仓位，则放弃推断，避免错误覆盖基线
    """
    estimated_equity = float(cash or 0.0)
    has_cost_basis = False

    for pos in positions.values():
        if not isinstance(pos, dict):
            continue
        side = str(pos.get("side") or "long").lower()
        if side == "short":
            return None
        volume = float(pos.get("volume") or 0.0)
        cost_price = float(
            pos.get("cost_price")
            or pos.get("avg_cost")
            or pos.get("avg_price")
            or pos.get("cost")
            or 0.0
        )
        if volume <= 0:
            continue
        if cost_price <= 0:
            return None
        estimated_equity += volume * cost_price
        has_cost_basis = True

    if not has_cost_basis:
        return None
    return round(estimated_equity, 2)


DEFAULT_INITIAL_CASH = 1_000_000.0
SIM_AMOUNT_STEP = 100_000
COOLDOWN_DAYS = 30


class AccountResetRequest(BaseModel):
    initial_cash: float | None = None


class HoldingItem(BaseModel):
    symbol: str
    quantity: float
    name: Optional[str] = None


class SyncHoldingsRequest(BaseModel):
    holdings: List[HoldingItem]
    available_cash: Optional[float] = None


# SimulationSettingsRequest removed as it is deprecated.


class SimulationSettingsResponse(BaseModel):
    initial_cash: float
    last_modified_at: str | None = None
    next_allowed_modified_at: str | None = None
    can_modify: bool
    cooldown_days: int
    amount_step: int


class SimulationFundSnapshotResponse(BaseModel):
    snapshot_date: date
    total_asset: Decimal
    available_balance: Decimal
    frozen_balance: Decimal
    market_value: Decimal
    initial_capital: Decimal
    total_pnl: Decimal
    today_pnl: Decimal
    daily_return_pct: float
    daily_return_ratio: float
    total_return_pct: float
    total_return_ratio: float
    source: str


class SimulationCorporateActionCreateRequest(BaseModel):
    symbol: str
    action_type: str
    ex_date: datetime | None = None
    effective_date: datetime | None = None
    cash_dividend_per_share: float = 0.0
    share_ratio: float = 0.0
    rights_price: float = 0.0
    source: str = "manual"
    note: str | None = None


class SimulationCorporateActionResponse(BaseModel):
    id: int
    symbol: str
    action_type: str
    ex_date: datetime | None = None
    effective_date: datetime | None = None
    cash_dividend_per_share: float = 0.0
    share_ratio: float = 0.0
    rights_price: float = 0.0
    source: str = "manual"
    note: str | None = None
    status: str = "pending"
    applied_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SimulationRebalanceJobResponse(BaseModel):
    job_id: str
    tenant_id: str
    user_id: str
    strategy_id: str
    job_type: str
    schedule_type: str
    planned_run_at: datetime | None = None
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None
    status: str
    attempt_count: int = 0
    last_error: str | None = None
    idempotency_key: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SimulationRebalanceJobCreateRequest(BaseModel):
    strategy_id: str
    schedule_type: str = "manual"
    planned_run_at: datetime | None = None
    window_seconds: int = 300


class SimulationCashLedgerResponse(BaseModel):
    id: int
    account_id: str
    tenant_id: str
    user_id: str
    event_type: str
    ref_type: str
    ref_id: str | None = None
    amount: float
    balance_after: float | None = None
    trade_date: datetime | None = None
    occurred_at: datetime
    currency: str = "CNY"
    note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SimulationPositionDailyResponse(BaseModel):
    snapshot_date: date
    snapshot_at: datetime
    symbol: str
    position_side: str
    quantity: float
    available_quantity: float
    frozen_quantity: float
    cost_price: float
    close_price: float
    market_value: float
    unrealized_pnl: float


class SimulationReplayResponse(BaseModel):
    snapshot_date: date
    account: SimulationFundSnapshotResponse
    positions: list[SimulationPositionDailyResponse]


class SimulationFillTraceResponse(BaseModel):
    fill_id: str
    order_id: str
    symbol: str
    side: str
    position_side: str
    trade_action: str | None = None
    fill_price: float
    fill_quantity: float
    gross_amount: float
    commission: float
    stamp_duty: float
    transfer_fee: float
    borrow_fee: float
    executed_at: datetime
    price_source: str | None = None
    session_phase: str | None = None


class SimulationPositionLotTraceResponse(BaseModel):
    id: int
    symbol: str
    position_side: str
    open_fill_id: str | None = None
    open_date: datetime | None = None
    quantity_open: float
    quantity_remaining: float
    cost_price: float
    cost_amount: float
    status: str
    closed_at: datetime | None = None


class SimulationReplayAuditResponse(BaseModel):
    snapshot_date: date
    account: SimulationFundSnapshotResponse
    positions: list[SimulationPositionDailyResponse]
    fills: list[SimulationFillTraceResponse]
    cash_ledger: list[SimulationCashLedgerResponse]
    position_lots: list[SimulationPositionLotTraceResponse]


class SimulationReplayTradeDateRequest(BaseModel):
    snapshot_date: date
    apply_to_cache: bool = True


class SimulationReplayLegacyTradesRequest(BaseModel):
    reset_existing: bool = True


class SimulationAccountAuditResponse(BaseModel):
    account_id: str
    tenant_id: str
    user_id: str
    sources: dict[str, Any]
    diffs: dict[str, Any]


@router.get("/settings")
async def get_simulation_settings(
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    manager = SimulationAccountManager(redis)
    data = await manager.get_settings(
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        default_initial_cash=DEFAULT_INITIAL_CASH,
        cooldown_days=COOLDOWN_DAYS,
    )
    return {
        "success": True,
        "data": {
            "initial_cash": data.get("initial_cash", DEFAULT_INITIAL_CASH),
            "can_modify": False,  # Modification deprecated
            "amount_step": SIM_AMOUNT_STEP,
            "cooldown_days": COOLDOWN_DAYS,
        },
    }


async def _capture_simulation_snapshot(redis: RedisClient) -> None:
    try:
        await SimulationFundSnapshotService.capture_all(redis)
    except Exception as exc:
        # 快照失败不应影响主流程；只记录日志，避免配置/重置接口被历史数据采集问题阻断。
        import logging

        logging.getLogger(__name__).warning(
            "Failed to capture simulation fund snapshot: %s",
            exc,
            exc_info=True,
        )


async def _purge_simulation_history(*, tenant_id: str, user_id: int) -> dict[str, int]:
    """清理当前租户/用户模拟盘历史，供账户重置使用。"""
    stats: dict[str, int] = {}
    normalized_user_id = normalize_trade_user_id(user_id) or str(user_id)
    legacy_user_id = str(int(normalized_user_id)) if normalized_user_id.isdigit() else normalized_user_id
    async with get_session(read_only=False) as session:
        statements = [
            (
                "sim_trades",
                text("""
                    DELETE FROM sim_trades
                    WHERE tenant_id = :tenant_id AND user_id = :user_id
                    """),
                {"tenant_id": tenant_id, "user_id": user_id},
            ),
            (
                "sim_orders",
                text("""
                    DELETE FROM sim_orders
                    WHERE tenant_id = :tenant_id AND user_id = :user_id
                    """),
                {"tenant_id": tenant_id, "user_id": user_id},
            ),
            (
                "simulation_fills",
                text("""
                    DELETE FROM simulation_fills
                    WHERE tenant_id = :tenant_id AND user_id = :normalized_user_id
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                },
            ),
            (
                "simulation_orders",
                text("""
                    DELETE FROM simulation_orders
                    WHERE tenant_id = :tenant_id AND user_id = :normalized_user_id
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                },
            ),
            (
                "simulation_cash_ledger",
                text("""
                    DELETE FROM simulation_cash_ledger
                    WHERE tenant_id = :tenant_id AND user_id = :normalized_user_id
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                },
            ),
            (
                "simulation_position_lots",
                text("""
                    DELETE FROM simulation_position_lots
                    WHERE tenant_id = :tenant_id AND user_id = :normalized_user_id
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                },
            ),
            (
                "simulation_account_daily",
                text("""
                    DELETE FROM simulation_account_daily
                    WHERE tenant_id = :tenant_id
                      AND (user_id = :normalized_user_id OR user_id = :legacy_user_id)
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                    "legacy_user_id": legacy_user_id,
                },
            ),
            (
                "simulation_position_daily",
                text("""
                    DELETE FROM simulation_position_daily
                    WHERE tenant_id = :tenant_id
                      AND (user_id = :normalized_user_id OR user_id = :legacy_user_id)
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                    "legacy_user_id": legacy_user_id,
                },
            ),
            (
                "simulation_rebalance_jobs",
                text("""
                    DELETE FROM simulation_rebalance_jobs
                    WHERE tenant_id = :tenant_id AND user_id = :normalized_user_id
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                },
            ),
            (
                "simulation_accounts",
                text("""
                    DELETE FROM simulation_accounts
                    WHERE tenant_id = :tenant_id
                      AND (user_id = :normalized_user_id OR user_id = :legacy_user_id)
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                    "legacy_user_id": legacy_user_id,
                },
            ),
            (
                "simulation_fund_snapshots",
                text("""
                    DELETE FROM simulation_fund_snapshots
                    WHERE tenant_id = :tenant_id
                      AND (user_id = :normalized_user_id OR user_id = :legacy_user_id)
                    """),
                {
                    "tenant_id": tenant_id,
                    "normalized_user_id": normalized_user_id,
                    "legacy_user_id": legacy_user_id,
                },
            ),
        ]
        for table_name, stmt, params in statements:
            result = await session.execute(stmt, params)
            stats[table_name] = int(result.rowcount or 0)
    return stats


# update_simulation_settings (PUT /settings) removed as it is deprecated.


@router.post("/reset")
async def reset_simulation_account(
    request: AccountResetRequest,
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    """
    Reset simulation account with initial cash.
    """
    manager = SimulationAccountManager(redis)
    initial_cash = DEFAULT_INITIAL_CASH

    # 模拟盘重置口径固定回到 100 万，不再接受外部初始资金参数。
    await manager.set_initial_cash(auth.user_id, initial_cash, tenant_id=auth.tenant_id)
    purge_stats = await _purge_simulation_history(
        tenant_id=auth.tenant_id,
        user_id=int(auth.user_id),
    )
    account = await manager.init_account(
        auth.user_id, initial_cash, tenant_id=auth.tenant_id
    )
    await _capture_simulation_snapshot(redis)
    return {
        "success": True,
        "message": "Simulation account reset",
        "data": account,
        "purged": purge_stats,
    }


@router.get("/account")
async def get_simulation_account(
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    """
    Get current simulation account state.
    如果账户不存在，返回空账户（total_asset=0），不自动初始化。
    """
    manager = SimulationAccountManager(redis)
    account = await manager.get_account(auth.user_id, tenant_id=auth.tenant_id)

    projection_account = None
    projection_positions: dict[str, dict[str, float]] = {}
    try:
        async with get_session(read_only=True) as session:
            projection = await SimulationProjectionService(session).load_projection(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                latest_price_loader=_get_latest_price,
            )
            projection_account = projection.account
            projection_positions = projection.positions
    except Exception as exc:
        logger.warning(
            "Failed to load simulation projection for tenant=%s user=%s: %s",
            auth.tenant_id,
            auth.user_id,
            exc,
        )

    if projection_account is None:
        normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
        inferred_initial_equity = float(
            (account or {}).get("initial_equity")
            or (((account or {}).get("baseline") or {}).get("initial_equity") if isinstance((account or {}).get("baseline"), dict) else 0.0)
            or DEFAULT_INITIAL_CASH
        )
        try:
            async with get_session(read_only=False) as session:
                migrated = await SimulationMigrationService(session).ensure_projection_from_legacy(
                    tenant_id=auth.tenant_id,
                    user_id=normalized_user_id,
                    initial_equity=inferred_initial_equity,
                )
                if migrated:
                    await session.commit()
            if migrated:
                async with get_session(read_only=True) as session:
                    projection = await SimulationProjectionService(session).load_projection(
                        tenant_id=auth.tenant_id,
                        user_id=auth.user_id,
                        latest_price_loader=_get_latest_price,
                    )
                    projection_account = projection.account
                    projection_positions = projection.positions
        except Exception as exc:
            logger.warning(
                "Failed to migrate legacy simulation trades into projection for tenant=%s user=%s: %s",
                auth.tenant_id,
                auth.user_id,
                exc,
            )

    if projection_account and not account:
        bootstrap_cache_payload = SimulationProjectionService.build_cache_payload(
            account=projection_account,
            positions=projection_positions,
            source="simulation_projection_bootstrap",
        )
        _persist_projection_cache(
            redis=redis,
            manager=manager,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            payload=bootstrap_cache_payload,
        )
        account = bootstrap_cache_payload

    if projection_account is not None and not _is_cache_payload_structurally_valid(account):
        rebuilt_cache_payload = SimulationProjectionService.build_cache_payload(
            account=projection_account,
            positions=projection_positions,
            source="simulation_projection_auto_rebuild",
        )
        _persist_projection_cache(
            redis=redis,
            manager=manager,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            payload=rebuilt_cache_payload,
        )
        account = rebuilt_cache_payload

    if not account:
        # 不再自动初始化，返回空账户标记
        return {
            "success": True,
            "data": {
                "cash": 0.0,
                "total_asset": 0.0,
                "market_value": 0.0,
                "positions": {},
                "account_not_initialized": True,
            },
        }

    # 从 settings 中读取初始资金与重置锚点；若账户本身带有显式基线，后续会优先使用账户口径。
    settings = await manager.get_settings(
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        default_initial_cash=DEFAULT_INITIAL_CASH,
        cooldown_days=COOLDOWN_DAYS,
    )
    initial_equity = float(settings.get("initial_cash", DEFAULT_INITIAL_CASH))
    reset_anchor_raw = settings.get("last_modified_at")
    reset_anchor = None
    if isinstance(reset_anchor_raw, str) and reset_anchor_raw.strip():
        try:
            reset_anchor = datetime.fromisoformat(
                reset_anchor_raw.replace("Z", "+00:00")
            )
        except Exception:
            reset_anchor = None

    cash = float(
        (projection_account.cash if projection_account is not None else None)
        or account.get("cash")
        or account.get("available_balance")
        or 0.0
    )
    market_value = 0.0
    positions: dict[str, dict[str, float]] = {}
    used_redis_positions_fallback = False
    valuation_source = "redis_positions_fallback"
    redis_positions_map = (
        account.get("positions") if isinstance(account.get("positions"), dict) else {}
    )
    if projection_account is not None:
        positions = projection_positions
        if projection_positions:
            _, _, market_value = (
                SimulationProjectionService.summarize_position_market_value(
                    projection_positions
                )
            )
        else:
            market_value = round(
                float(projection_account.long_market_value or 0.0)
                - float(projection_account.short_market_value or 0.0),
                2,
            )
        valuation_source = (
            "simulation_position_lots_projection"
            if projection_positions
            else "simulation_account_projection"
        )

    if not positions and projection_account is None:
        used_redis_positions_fallback = True
        # 新账本账户不存在时，才允许最终回退 Redis 历史持仓。
        raw_positions = account.get("positions") or {}
        if isinstance(raw_positions, dict):
            for sym, pos in raw_positions.items():
                symbol = str(sym or "").strip().upper()
                if not symbol or not isinstance(pos, dict):
                    continue
                volume = float(pos.get("volume") or 0.0)
                last_price = float(pos.get("price") or pos.get("last_price") or 0.0)
                if volume <= 0 or last_price <= 0:
                    continue
                market_val = round(volume * last_price, 2)
                cost_price = float(
                    pos.get("cost")
                    or pos.get("cost_price")
                    or pos.get("avg_cost")
                    or pos.get("avg_price")
                    or 0.0
                )
                positions[symbol] = {
                    "volume": volume,
                    "available_volume": float(pos.get("available_volume") or volume),
                    "frozen_volume": max(
                        0.0,
                        float(pos.get("volume") or volume)
                        - float(pos.get("available_volume") or volume),
                    ),
                    "price": round(last_price, 4),
                    "last_price": round(last_price, 4),
                    "market_value": market_val,
                    "cost_price": round(cost_price, 4) if cost_price > 0 else 0.0,
                    "side": str(pos.get("side") or "long").lower(),
                }
                side = str(pos.get("side") or "long").lower()
                market_value += (-market_val if side == "short" else market_val)
        market_value = round(market_value, 2)
    else:
        # DB 聚合口径优先时，补齐仓位成本价（来自 Redis 持仓对象）用于浮动盈亏计算。
        if isinstance(redis_positions_map, dict):
            for symbol, pos in positions.items():
                if not isinstance(pos, dict):
                    continue
                candidates = [
                    redis_positions_map.get(symbol),
                    redis_positions_map.get(f"{symbol}::long"),
                ]
                # Prefix / Suffix 双格式匹配
                if symbol.endswith((".SH", ".SZ", ".BJ")) and len(symbol) > 3:
                    prefix = f"{symbol[-2:]}{symbol[:-3]}"
                    candidates.append(redis_positions_map.get(prefix))
                    candidates.append(redis_positions_map.get(f"{prefix}::long"))
                elif symbol.startswith(("SH", "SZ", "BJ")) and len(symbol) > 2:
                    suffix = f"{symbol[2:]}.{symbol[:2]}"
                    candidates.append(redis_positions_map.get(suffix))
                    candidates.append(redis_positions_map.get(f"{suffix}::long"))

                redis_pos = next(
                    (item for item in candidates if isinstance(item, dict)), None
                )
                if redis_pos:
                    cost_price = float(
                        redis_pos.get("cost")
                        or redis_pos.get("cost_price")
                        or redis_pos.get("avg_cost")
                        or redis_pos.get("avg_price")
                        or 0.0
                    )
                    if cost_price > 0:
                        pos["cost_price"] = round(cost_price, 4)

    total_asset = round(cash + market_value, 2)
    floating_pnl = 0.0
    for pos in positions.values():
        if not isinstance(pos, dict):
            continue
        volume = float(pos.get("volume") or 0.0)
        last_price = float(pos.get("last_price") or pos.get("price") or 0.0)
        cost_price = float(
            pos.get("cost_price")
            or pos.get("avg_cost")
            or pos.get("avg_price")
            or pos.get("cost")
            or 0.0
        )
        side = str(pos.get("side") or "long").lower()
        if volume <= 0 or last_price <= 0 or cost_price <= 0:
            continue
        if side == "short":
            floating_pnl += (cost_price - last_price) * volume
        else:
            floating_pnl += (last_price - cost_price) * volume
    floating_pnl = round(floating_pnl, 2)

    account_initial_equity = float(
        (projection_account.initial_equity if projection_account is not None else None)
        or account.get("initial_equity")
        or account.get("initial_capital")
        or ((account.get("baseline") or {}).get("initial_equity") if isinstance(account.get("baseline"), dict) else 0.0)
        or 0.0
    )
    initial_equity = account_initial_equity if account_initial_equity > 0 else float(
        settings.get("initial_cash", DEFAULT_INITIAL_CASH)
    )
    if used_redis_positions_fallback:
        seed_initial_equity = _derive_seed_initial_equity_from_positions(
            cash=cash,
            positions=positions,
        )
        if seed_initial_equity and abs(seed_initial_equity - initial_equity) > 1.0:
            initial_equity = seed_initial_equity

    # 今日盈亏基线优先取上一交易日资金快照；没有历史快照时回退初始权益。
    day_open_equity = initial_equity
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    try:
        today = date.today()
        async with get_session(read_only=True) as session:
            prev_stmt = text("""
                SELECT total_asset
                FROM simulation_fund_snapshots
                WHERE tenant_id = :tenant_id
                  AND user_id = :user_id
                  AND snapshot_date < :today
                ORDER BY snapshot_date DESC
                LIMIT 1
            """)
            prev_row = (
                await session.execute(
                    prev_stmt,
                    {
                        "tenant_id": auth.tenant_id,
                        "user_id": normalized_user_id,
                        "today": today,
                    },
                )
            ).first()
            if prev_row and prev_row[0] is not None:
                day_open_equity = float(prev_row[0])
    except Exception:
        day_open_equity = initial_equity
    today_pnl = round(total_asset - day_open_equity, 2)
    total_pnl = round(total_asset - initial_equity, 2)
    daily_return_pct = (
        round((today_pnl / day_open_equity) * 100, 6) if day_open_equity > 0 else 0.0
    )
    total_return_pct = (
        round((total_pnl / initial_equity) * 100, 6) if initial_equity > 0 else 0.0
    )

    # 添加 initial_equity 和 baseline 字段
    account["cash"] = cash
    account["available_cash"] = cash
    account["market_value"] = market_value
    account["total_asset"] = total_asset
    account["today_pnl"] = today_pnl
    account["daily_pnl"] = today_pnl
    account["floating_pnl"] = floating_pnl
    account["total_pnl"] = total_pnl
    account["daily_return"] = daily_return_pct
    account["daily_return_pct"] = daily_return_pct
    account["daily_return_ratio"] = daily_return_pct / 100.0
    account["total_return"] = total_return_pct
    account["total_return_pct"] = total_return_pct
    account["total_return_ratio"] = total_return_pct / 100.0
    account["day_open_equity"] = day_open_equity
    account["positions"] = positions
    account["position_count"] = len(positions)
    account["initial_equity"] = initial_equity
    account["valuation_source"] = valuation_source
    account["baseline"] = {
        "initial_equity": initial_equity,
        "day_open_equity": day_open_equity,
        "month_open_equity": initial_equity,
    }

    return {"success": True, "data": account}


@router.get("/admin/account-audit", response_model=SimulationAccountAuditResponse)
async def get_simulation_account_audit(
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    manager = SimulationAccountManager(redis)
    redis_account = await manager.get_account(auth.user_id, tenant_id=auth.tenant_id)

    projection_account = None
    projection_positions: dict[str, dict[str, float]] = {}
    async with get_session(read_only=True) as session:
        projection = await SimulationProjectionService(session).load_projection(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            latest_price_loader=_get_latest_price,
        )
        projection_account = projection.account
        projection_positions = projection.positions

    trade_history_positions, trade_history_market_value, trade_history_source = (
        await _build_realtime_positions_from_trade_history(
            tenant_id=auth.tenant_id,
            user_id=str(auth.user_id),
        )
    )
    legacy_trade_history_positions: dict[str, dict[str, float]] | None = None
    legacy_trade_history_market_value = 0.0
    legacy_trade_history_source: str | None = None
    if trade_history_source == "trade_history_aggregate_empty":
        try:
            legacy_user_id = int(str(auth.user_id))
            (
                legacy_trade_history_positions,
                legacy_trade_history_market_value,
            ) = await _build_realtime_positions_from_db(
                tenant_id=auth.tenant_id,
                user_id=legacy_user_id,
            )
            legacy_trade_history_source = "legacy_trade_aggregate"
        except (TypeError, ValueError):
            legacy_trade_history_positions = None
            legacy_trade_history_market_value = 0.0
            legacy_trade_history_source = None

    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    return SimulationAccountAuditResponse(
        **_build_account_reconcile_report(
            tenant_id=auth.tenant_id,
            user_id=normalized_user_id,
            redis_account=redis_account if isinstance(redis_account, dict) else {},
            projection_account=projection_account,
            projection_positions=projection_positions,
            trade_history_positions=trade_history_positions,
            trade_history_market_value=trade_history_market_value,
            trade_history_source=trade_history_source,
            legacy_trade_history_positions=legacy_trade_history_positions,
            legacy_trade_history_market_value=legacy_trade_history_market_value,
            legacy_trade_history_source=legacy_trade_history_source,
        )
    )


@router.post("/snapshots/capture")
async def capture_simulation_fund_snapshot(
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    """手动触发一次模拟账户资金快照采集（按天 upsert）。"""
    result = await SimulationFundSnapshotService.capture_all(redis)
    return {
        "success": True,
        "message": "simulation fund snapshot captured",
        "data": {
            "upserted_rows": result.upserted_rows,
            "scanned_accounts": result.scanned_accounts,
            "requested_by": str(auth.user_id),
        },
    }


@router.get("/snapshots/daily", response_model=list[SimulationFundSnapshotResponse])
async def list_simulation_fund_snapshots(
    days: int = Query(default=30, ge=1, le=3650),
    auth: AuthContext = Depends(get_auth_context),
):
    """查询当前用户的模拟盘日级资金快照历史。"""
    snapshots_v2 = await SimulationFundSnapshotService.list_user_daily_v2(
        tenant_id=auth.tenant_id,
        user_id=normalize_trade_user_id(auth.user_id) or str(auth.user_id),
        days=days,
    )
    if snapshots_v2:
        ordered_v2 = list(reversed(snapshots_v2))
        previous_total_asset: float | None = None
        responses_v2: list[SimulationFundSnapshotResponse] = []
        for s in ordered_v2:
            total_asset = float(s.total_asset or 0)
            daily_pnl = float(s.daily_pnl or 0)
            total_pnl = float(s.total_pnl or 0)
            initial_capital = max(0.0, total_asset - total_pnl)
            day_open_equity = previous_total_asset or 0.0
            if day_open_equity <= 0 and initial_capital > 0:
                day_open_equity = initial_capital
            daily_return_pct = (
                (daily_pnl / day_open_equity * 100.0) if day_open_equity > 0 else 0.0
            )
            total_return_pct = (
                (total_pnl / initial_capital * 100.0) if initial_capital > 0 else 0.0
            )
            responses_v2.append(
                SimulationFundSnapshotResponse(
                    snapshot_date=s.snapshot_date,
                    total_asset=Decimal(str(s.total_asset or 0.0)),
                    available_balance=Decimal(str(s.available_cash or 0.0)),
                    frozen_balance=Decimal(str(s.frozen_cash or 0.0)),
                    market_value=Decimal(
                        str((s.long_market_value or 0.0) - (s.short_market_value or 0.0))
                    ),
                    initial_capital=Decimal(str(initial_capital)),
                    total_pnl=Decimal(str(total_pnl)),
                    today_pnl=Decimal(str(daily_pnl)),
                    daily_return_pct=round(daily_return_pct, 6),
                    daily_return_ratio=round(daily_return_pct / 100.0, 10),
                    total_return_pct=round(total_return_pct, 6),
                    total_return_ratio=round(total_return_pct / 100.0, 10),
                    source="simulation_account_daily",
                )
            )
            previous_total_asset = total_asset if total_asset > 0 else previous_total_asset
        return list(reversed(responses_v2))

    snapshots = await SimulationFundSnapshotService.list_user_daily(
        tenant_id=auth.tenant_id,
        user_id=normalize_trade_user_id(auth.user_id) or str(auth.user_id),
        days=days,
    )
    ordered = list(reversed(snapshots))
    previous_total_asset: float | None = None
    responses: list[SimulationFundSnapshotResponse] = []
    for s in ordered:
        total_asset = float(s.total_asset or 0)
        initial_capital = float(s.initial_capital or 0)
        today_pnl = float(s.today_pnl or 0)
        day_open_equity = previous_total_asset or 0.0
        if day_open_equity <= 0 and initial_capital > 0:
            day_open_equity = initial_capital
        daily_return_pct = (
            (today_pnl / day_open_equity * 100.0) if day_open_equity > 0 else 0.0
        )
        total_return_pct = (
            (float(s.total_pnl or 0) / initial_capital * 100.0)
            if initial_capital > 0
            else 0.0
        )
        responses.append(
            SimulationFundSnapshotResponse(
                snapshot_date=s.snapshot_date,
                total_asset=s.total_asset,
                available_balance=s.available_balance,
                frozen_balance=s.frozen_balance,
                market_value=s.market_value,
                initial_capital=s.initial_capital,
                total_pnl=s.total_pnl,
                today_pnl=s.today_pnl,
                daily_return_pct=round(daily_return_pct, 6),
                daily_return_ratio=round(daily_return_pct / 100.0, 10),
                total_return_pct=round(total_return_pct, 6),
                total_return_ratio=round(total_return_pct / 100.0, 10),
                source=s.source,
            )
        )
        previous_total_asset = total_asset if total_asset > 0 else previous_total_asset
    return list(reversed(responses))


@router.get("/positions/daily", response_model=list[SimulationPositionDailyResponse])
async def list_simulation_position_daily(
    days: int = Query(default=30, ge=1, le=3650),
    symbol: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=True) as session:
        stmt = (
            select(SimulationPositionDaily)
            .where(
                SimulationPositionDaily.tenant_id == auth.tenant_id,
                SimulationPositionDaily.user_id == normalized_user_id,
            )
            .order_by(
                SimulationPositionDaily.snapshot_date.desc(),
                SimulationPositionDaily.symbol.asc(),
                SimulationPositionDaily.position_side.asc(),
            )
            .limit(max(1, min(days * 200, 10000)))
        )
        if symbol:
            stmt = stmt.where(
                SimulationPositionDaily.symbol == str(symbol).strip().upper()
            )
        rows = (await session.execute(stmt)).scalars().all()
    ordered = list(reversed(rows))
    return [
        SimulationPositionDailyResponse(
            snapshot_date=row.snapshot_date,
            snapshot_at=row.snapshot_at,
            symbol=row.symbol,
            position_side=row.position_side,
            quantity=float(row.quantity or 0.0),
            available_quantity=float(row.available_quantity or 0.0),
            frozen_quantity=float(row.frozen_quantity or 0.0),
            cost_price=float(row.cost_price or 0.0),
            close_price=float(row.close_price or 0.0),
            market_value=float(row.market_value or 0.0),
            unrealized_pnl=float(row.unrealized_pnl or 0.0),
        )
        for row in ordered
    ]


@router.get("/cash-ledger", response_model=list[SimulationCashLedgerResponse])
async def list_simulation_cash_ledger(
    limit: int = Query(default=100, ge=1, le=1000),
    event_type: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=True) as session:
        stmt = (
            select(SimulationCashLedger)
            .where(
                SimulationCashLedger.tenant_id == auth.tenant_id,
                SimulationCashLedger.user_id == normalized_user_id,
            )
            .order_by(
                SimulationCashLedger.occurred_at.desc(),
                SimulationCashLedger.id.desc(),
            )
            .limit(limit)
        )
        if event_type:
            stmt = stmt.where(
                SimulationCashLedger.event_type == str(event_type).strip().upper()
            )
        rows = (await session.execute(stmt)).scalars().all()
    return [
        SimulationCashLedgerResponse(
            id=row.id,
            account_id=row.account_id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            event_type=row.event_type,
            ref_type=row.ref_type,
            ref_id=row.ref_id,
            amount=float(row.amount or 0.0),
            balance_after=float(row.balance_after) if row.balance_after is not None else None,
            trade_date=row.trade_date,
            occurred_at=row.occurred_at,
            currency=row.currency,
            note=row.note,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/sync/ocr")
async def ocr_sync_holdings(
    images: List[UploadFile] = File(...),
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    ocr_service = SimulationOCRService()
    image_data = []
    for img in images:
        content = await img.read()
        image_data.append(content)

    ocr_result = await ocr_service.analyze_images(image_data)
    recognized_items = ocr_result.get("holdings", [])
    available_cash = ocr_result.get("available_cash")

    # 4. 后处理：纠偏代码 & 获取实时行情
    results = []

    for item in recognized_items:
        original_symbol = item.get("symbol")
        name = item.get("name")

        # 优先使用 OCR 识别出的代码（已在服务层通过 stocks_index.json 对齐）
        symbol = (
            original_symbol if original_symbol else await _resolve_symbol_by_name(name)
        )

        if not symbol:
            logger.warning(f"Skipping holding {name}: Symbol could not be resolved.")
            continue

        current_price = await _get_latest_price(symbol)

        results.append(
            {
                **item,
                "symbol": symbol,
                "current_price": current_price,
                "market_value": round(current_price * item["quantity"], 2),
            }
        )

    return {"success": True, "data": results, "available_cash": available_cash}


@router.get("/rebalance-jobs", response_model=list[SimulationRebalanceJobResponse])
async def list_simulation_rebalance_jobs(
    strategy_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    auth: AuthContext = Depends(get_auth_context),
):
    async with get_session(read_only=True) as session:
        stmt = (
            select(SimulationRebalanceJob)
            .where(
                SimulationRebalanceJob.tenant_id == auth.tenant_id,
                SimulationRebalanceJob.user_id == (normalize_trade_user_id(auth.user_id) or str(auth.user_id)),
            )
            .order_by(
                SimulationRebalanceJob.created_at.desc(),
                SimulationRebalanceJob.id.desc(),
            )
            .limit(limit)
        )
        if strategy_id:
            stmt = stmt.where(SimulationRebalanceJob.strategy_id == str(strategy_id).strip())
        if status:
            stmt = stmt.where(SimulationRebalanceJob.status == str(status).strip().lower())
        rows = (await session.execute(stmt)).scalars().all()
    return [
        SimulationRebalanceJobResponse(
            job_id=row.job_id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            strategy_id=row.strategy_id,
            job_type=row.job_type,
            schedule_type=row.schedule_type,
            planned_run_at=row.planned_run_at,
            window_start_at=row.window_start_at,
            window_end_at=row.window_end_at,
            status=row.status,
            attempt_count=int(row.attempt_count or 0),
            last_error=row.last_error,
            idempotency_key=row.idempotency_key,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/rebalance-jobs/{job_id}", response_model=SimulationRebalanceJobResponse)
async def get_simulation_rebalance_job(
    job_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=True) as session:
        row = (
            await session.execute(
                select(SimulationRebalanceJob).where(
                    SimulationRebalanceJob.job_id == str(job_id).strip(),
                    SimulationRebalanceJob.tenant_id == auth.tenant_id,
                    SimulationRebalanceJob.user_id == normalized_user_id,
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Simulation rebalance job not found")
    return SimulationRebalanceJobResponse(
        job_id=row.job_id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        strategy_id=row.strategy_id,
        job_type=row.job_type,
        schedule_type=row.schedule_type,
        planned_run_at=row.planned_run_at,
        window_start_at=row.window_start_at,
        window_end_at=row.window_end_at,
        status=row.status,
        attempt_count=int(row.attempt_count or 0),
        last_error=row.last_error,
        idempotency_key=row.idempotency_key,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/rebalance-jobs", response_model=SimulationRebalanceJobResponse, status_code=status.HTTP_201_CREATED)
async def create_simulation_rebalance_job(
    payload: SimulationRebalanceJobCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    planned_run_at = payload.planned_run_at or datetime.now()
    job_suffix = planned_run_at.strftime("%Y%m%d%H%M%S")
    job_id = (
        f"manual_sim_{auth.tenant_id}_{normalized_user_id}_{str(payload.strategy_id).strip()}_{job_suffix}"
    )
    async with get_session(read_only=False) as session:
        row = SimulationRebalanceJob(
            job_id=job_id,
            tenant_id=auth.tenant_id,
            user_id=normalized_user_id,
            strategy_id=str(payload.strategy_id).strip(),
            job_type="rebalance",
            schedule_type=str(payload.schedule_type or "manual").strip().lower(),
            planned_run_at=planned_run_at,
            window_start_at=planned_run_at,
            window_end_at=planned_run_at,
            status="pending",
            attempt_count=0,
            idempotency_key=job_id,
        )
        if int(payload.window_seconds or 0) > 0:
            row.window_end_at = planned_run_at + timedelta(seconds=int(payload.window_seconds))
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return SimulationRebalanceJobResponse(
        job_id=row.job_id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        strategy_id=row.strategy_id,
        job_type=row.job_type,
        schedule_type=row.schedule_type,
        planned_run_at=row.planned_run_at,
        window_start_at=row.window_start_at,
        window_end_at=row.window_end_at,
        status=row.status,
        attempt_count=int(row.attempt_count or 0),
        last_error=row.last_error,
        idempotency_key=row.idempotency_key,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/corporate-actions", response_model=list[SimulationCorporateActionResponse])
async def list_simulation_corporate_actions(
    symbol: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(get_auth_context),
):
    async with get_session(read_only=True) as session:
        stmt = (
            select(SimulationCorporateAction)
            .order_by(
                SimulationCorporateAction.effective_date.desc().nullslast(),
                SimulationCorporateAction.ex_date.desc().nullslast(),
                SimulationCorporateAction.id.desc(),
            )
            .limit(limit)
        )
        if symbol:
            stmt = stmt.where(SimulationCorporateAction.symbol == str(symbol).strip().upper())
        if status:
            stmt = stmt.where(SimulationCorporateAction.status == str(status).strip().lower())
        rows = (await session.execute(stmt)).scalars().all()
    return [
        SimulationCorporateActionResponse(
            id=row.id,
            symbol=row.symbol,
            action_type=row.action_type,
            ex_date=row.ex_date,
            effective_date=row.effective_date,
            cash_dividend_per_share=float(row.cash_dividend_per_share or 0.0),
            share_ratio=float(row.share_ratio or 0.0),
            rights_price=float(row.rights_price or 0.0),
            source=row.source,
            note=row.note,
            status=row.status,
            applied_at=row.applied_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/corporate-actions", response_model=SimulationCorporateActionResponse, status_code=status.HTTP_201_CREATED)
async def create_simulation_corporate_action(
    payload: SimulationCorporateActionCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    async with get_session(read_only=False) as session:
        model = SimulationCorporateAction(
            symbol=StockCodeUtil.to_prefix(payload.symbol),
            action_type=str(payload.action_type).strip().lower(),
            ex_date=payload.ex_date,
            effective_date=payload.effective_date,
            cash_dividend_per_share=float(payload.cash_dividend_per_share or 0.0),
            share_ratio=float(payload.share_ratio or 0.0),
            rights_price=float(payload.rights_price or 0.0),
            source=str(payload.source or "manual").strip() or "manual",
            note=payload.note,
            status="pending",
        )
        session.add(model)
        await session.flush()
        await session.refresh(model)
    return SimulationCorporateActionResponse(
        id=model.id,
        symbol=model.symbol,
        action_type=model.action_type,
        ex_date=model.ex_date,
        effective_date=model.effective_date,
        cash_dividend_per_share=float(model.cash_dividend_per_share or 0.0),
        share_ratio=float(model.share_ratio or 0.0),
        rights_price=float(model.rights_price or 0.0),
        source=model.source,
        note=model.note,
        status=model.status,
        applied_at=model.applied_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


@router.post("/corporate-actions/apply")
async def apply_simulation_corporate_actions(
    auth: AuthContext = Depends(get_auth_context),
):
    applied = await SimulationCorporateActionService.apply_due_actions()
    return {
        "success": True,
        "message": "simulation corporate actions applied",
        "data": {
            "applied_count": applied,
            "requested_by": str(auth.user_id),
        },
    }


@router.post("/admin/replay-trade-date")
async def replay_simulation_trade_date(
    payload: SimulationReplayTradeDateRequest,
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=True) as session:
        account_row = (
            await session.execute(
                select(SimulationAccountDaily).where(
                    SimulationAccountDaily.tenant_id == auth.tenant_id,
                    SimulationAccountDaily.user_id == normalized_user_id,
                    SimulationAccountDaily.snapshot_date == payload.snapshot_date,
                )
            )
        ).scalar_one_or_none()
        if account_row is None:
            raise HTTPException(status_code=404, detail="Simulation daily snapshot not found")
        position_rows = list(
            (
                await session.execute(
                    select(SimulationPositionDaily).where(
                        SimulationPositionDaily.tenant_id == auth.tenant_id,
                        SimulationPositionDaily.user_id == normalized_user_id,
                        SimulationPositionDaily.snapshot_date == payload.snapshot_date,
                    )
                )
            ).scalars().all()
        )

    cache_payload = _build_cache_payload_from_daily_rows(
        account_row=account_row,
        position_rows=position_rows,
    )
    manager = SimulationAccountManager(redis)
    cache_key = manager._get_key(auth.user_id, auth.tenant_id)
    if payload.apply_to_cache:
        write_json_cache(redis, cache_key, cache_payload)
        write_trade_account_cache(
            redis,
            auth.tenant_id,
            normalized_user_id,
            dict(cache_payload),
        )

    return {
        "success": True,
        "message": "simulation trade date replayed",
        "data": {
            "snapshot_date": payload.snapshot_date.isoformat(),
            "applied_to_cache": bool(payload.apply_to_cache),
            "positions": len(position_rows),
            "cache_key": cache_key,
            "total_asset": round(float(cache_payload.get("total_asset") or 0.0), 2),
        },
    }


@router.get("/replay/{snapshot_date}", response_model=SimulationReplayResponse)
async def replay_simulation_snapshot_by_date(
    snapshot_date: date,
    auth: AuthContext = Depends(get_auth_context),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=True) as session:
        account_row = (
            await session.execute(
                select(SimulationAccountDaily).where(
                    SimulationAccountDaily.tenant_id == auth.tenant_id,
                    SimulationAccountDaily.user_id == normalized_user_id,
                    SimulationAccountDaily.snapshot_date == snapshot_date,
                )
            )
        ).scalar_one_or_none()
        if account_row is None:
            raise HTTPException(status_code=404, detail="Simulation daily snapshot not found")

        position_rows = (
            await session.execute(
                select(SimulationPositionDaily).where(
                    SimulationPositionDaily.tenant_id == auth.tenant_id,
                    SimulationPositionDaily.user_id == normalized_user_id,
                    SimulationPositionDaily.snapshot_date == snapshot_date,
                ).order_by(
                    SimulationPositionDaily.symbol.asc(),
                    SimulationPositionDaily.position_side.asc(),
                )
            )
        ).scalars().all()

    account_payload = _build_replay_account_payload(account_row)
    positions_payload = _build_replay_positions_payload(position_rows)
    return SimulationReplayResponse(
        snapshot_date=snapshot_date,
        account=account_payload,
        positions=positions_payload,
    )


@router.get("/replay/{snapshot_date}/audit", response_model=SimulationReplayAuditResponse)
async def replay_simulation_snapshot_audit(
    snapshot_date: date,
    auth: AuthContext = Depends(get_auth_context),
):
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=True) as session:
        account_row = (
            await session.execute(
                select(SimulationAccountDaily).where(
                    SimulationAccountDaily.tenant_id == auth.tenant_id,
                    SimulationAccountDaily.user_id == normalized_user_id,
                    SimulationAccountDaily.snapshot_date == snapshot_date,
                )
            )
        ).scalar_one_or_none()
        if account_row is None:
            raise HTTPException(status_code=404, detail="Simulation daily snapshot not found")

        position_rows = list(
            (
                await session.execute(
                    select(SimulationPositionDaily).where(
                        SimulationPositionDaily.tenant_id == auth.tenant_id,
                        SimulationPositionDaily.user_id == normalized_user_id,
                        SimulationPositionDaily.snapshot_date == snapshot_date,
                    ).order_by(
                        SimulationPositionDaily.symbol.asc(),
                        SimulationPositionDaily.position_side.asc(),
                    )
                )
            ).scalars().all()
        )
        fill_rows = list(
            (
                await session.execute(
                    select(SimulationFill).where(
                        SimulationFill.tenant_id == auth.tenant_id,
                        SimulationFill.user_id == normalized_user_id,
                        SimulationFill.account_id == account_row.account_id,
                        SimulationFill.executed_at <= account_row.snapshot_at,
                    ).order_by(
                        SimulationFill.executed_at.asc(),
                        SimulationFill.id.asc(),
                    )
                )
            ).scalars().all()
        )
        ledger_rows = list(
            (
                await session.execute(
                    select(SimulationCashLedger).where(
                        SimulationCashLedger.tenant_id == auth.tenant_id,
                        SimulationCashLedger.user_id == normalized_user_id,
                        SimulationCashLedger.account_id == account_row.account_id,
                        SimulationCashLedger.occurred_at <= account_row.snapshot_at,
                    ).order_by(
                        SimulationCashLedger.occurred_at.asc(),
                        SimulationCashLedger.id.asc(),
                    )
                )
            ).scalars().all()
        )
        lot_rows = list(
            (
                await session.execute(
                    select(SimulationPositionLot).where(
                        SimulationPositionLot.tenant_id == auth.tenant_id,
                        SimulationPositionLot.user_id == normalized_user_id,
                        SimulationPositionLot.account_id == account_row.account_id,
                        SimulationPositionLot.open_date <= account_row.snapshot_at,
                        (SimulationPositionLot.closed_at.is_(None))
                        | (SimulationPositionLot.closed_at > account_row.snapshot_at),
                    ).order_by(
                        SimulationPositionLot.open_date.asc().nullsfirst(),
                        SimulationPositionLot.id.asc(),
                    )
                )
            ).scalars().all()
        )

    return SimulationReplayAuditResponse(
        snapshot_date=snapshot_date,
        account=_build_replay_account_payload(account_row),
        positions=_build_replay_positions_payload(position_rows),
        fills=[
            SimulationFillTraceResponse(
                fill_id=str(row.fill_id),
                order_id=str(row.order_id),
                symbol=row.symbol,
                side=row.side,
                position_side=row.position_side,
                trade_action=row.trade_action,
                fill_price=float(row.fill_price or 0.0),
                fill_quantity=float(row.fill_quantity or 0.0),
                gross_amount=float(row.gross_amount or 0.0),
                commission=float(row.commission or 0.0),
                stamp_duty=float(row.stamp_duty or 0.0),
                transfer_fee=float(row.transfer_fee or 0.0),
                borrow_fee=float(row.borrow_fee or 0.0),
                executed_at=row.executed_at,
                price_source=row.price_source,
                session_phase=row.session_phase,
            )
            for row in fill_rows
        ],
        cash_ledger=[
            SimulationCashLedgerResponse(
                id=int(row.id),
                account_id=row.account_id,
                tenant_id=row.tenant_id,
                user_id=row.user_id,
                event_type=row.event_type,
                ref_type=row.ref_type,
                ref_id=row.ref_id,
                amount=float(row.amount or 0.0),
                balance_after=(
                    float(row.balance_after) if row.balance_after is not None else None
                ),
                trade_date=row.trade_date,
                occurred_at=row.occurred_at,
                currency=row.currency,
                note=row.note,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in ledger_rows
        ],
        position_lots=[
            SimulationPositionLotTraceResponse(
                id=int(row.id),
                symbol=row.symbol,
                position_side=row.position_side,
                open_fill_id=row.open_fill_id,
                open_date=row.open_date,
                quantity_open=float(row.quantity_open or 0.0),
                quantity_remaining=float(row.quantity_remaining or 0.0),
                cost_price=float(row.cost_price or 0.0),
                cost_amount=float(row.cost_amount or 0.0),
                status=row.status,
                closed_at=row.closed_at,
            )
            for row in lot_rows
        ],
    )


@router.post("/admin/rebuild-account")
async def rebuild_simulation_account_projection(
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    manager = SimulationAccountManager(redis)
    settings = await manager.get_settings(
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        default_initial_cash=DEFAULT_INITIAL_CASH,
        cooldown_days=COOLDOWN_DAYS,
    )
    current_account = await manager.get_account(auth.user_id, tenant_id=auth.tenant_id) or {}
    async with get_session(read_only=True) as session:
        projection = await SimulationProjectionService(session).load_projection(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            latest_price_loader=_get_latest_price,
        )

    projection_account = projection.account
    rebuilt_payload = SimulationProjectionService.build_cache_payload(
        account=projection_account,
        positions=projection.positions or current_account.get("positions") or {},
        source="simulation_projection_service",
    )
    sim_key = manager._get_key(auth.user_id, auth.tenant_id)
    write_json_cache(redis, sim_key, rebuilt_payload)
    write_trade_account_cache(
        redis,
        auth.tenant_id,
        normalize_trade_user_id(auth.user_id) or str(auth.user_id),
        dict(rebuilt_payload),
    )
    return {
        "success": True,
        "message": "simulation account projection rebuilt",
        "data": {
            "key": sim_key,
            "positions": len(rebuilt_payload.get("positions") or {}),
            "total_asset": round(float(rebuilt_payload.get("total_asset") or 0.0), 2),
        },
    }


@router.post("/admin/replay-legacy-trades")
async def replay_legacy_simulation_trades(
    payload: SimulationReplayLegacyTradesRequest,
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    manager = SimulationAccountManager(redis)
    settings = await manager.get_settings(
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        default_initial_cash=DEFAULT_INITIAL_CASH,
        cooldown_days=COOLDOWN_DAYS,
    )
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=False) as session:
        service = SimulationMigrationService(session)
        result = await service.replay_legacy_trades(
            tenant_id=auth.tenant_id,
            user_id=normalized_user_id,
            initial_equity=float(settings.get("initial_cash", DEFAULT_INITIAL_CASH) or DEFAULT_INITIAL_CASH),
            reset_existing=bool(payload.reset_existing),
        )
    # 回放完成后顺手重建当前缓存投影
    await rebuild_simulation_account_projection(auth=auth, redis=redis)
    return {
        "success": True,
        "message": "legacy simulation trades replayed into new ledger",
        "data": {
            "account_id": result.account_id,
            "replayed_trades": result.replayed_trades,
            "skipped_short_trades": result.skipped_short_trades,
            "reset_existing": bool(payload.reset_existing),
        },
    }


@router.post("/sync/confirm")
async def confirm_holding_sync(
    request: SyncHoldingsRequest,
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
):
    """
    确认同步 OCR 识别的持仓。
    逻辑：根据识别出的股票和数量，拉取当前最新市价，并重新计算账户初始金额，使同步后的盈亏对齐。
    """
    manager = SimulationAccountManager(redis)

    # 1. 预先获取所有股票的最新价格并计算总市值
    sync_positions = []
    total_market_value = 0.0

    for item in request.holdings:
        price = await _get_latest_price(item.symbol)

        if price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法获取股票 {item.symbol} 的实时价格或历史收盘价，同步中止。请检查代码是否正确。",
            )

        total_market_value += price * item.quantity
        sync_positions.append(
            {"symbol": item.symbol, "quantity": item.quantity, "price": price}
        )

    # 2. 计算同步后的”初始总资产”
    # 逻辑：我们将”可用现金”优先使用截图识别到的数值，如果没有则使用默认基数
    sync_cash = request.available_cash if request.available_cash is not None else 100.0
    calculated_initial_cash = total_market_value + sync_cash

    # 3. 更新 settings 中的 initial_cash（用于前端显示初始权益）
    await manager.set_initial_cash(
        auth.user_id, calculated_initial_cash, auth.tenant_id
    )

    # 4. 将确认后的快照直接落为“种子账本”，避免只写 Redis 而缺失持久化事实源。
    normalized_user_id = normalize_trade_user_id(auth.user_id) or str(auth.user_id)
    async with get_session(read_only=False) as session:
        await SimulationSeedService(session).reseed_from_holdings_snapshot(
            tenant_id=auth.tenant_id,
            user_id=normalized_user_id,
            initial_equity=calculated_initial_cash,
            available_cash=sync_cash,
            positions=sync_positions,
            clear_legacy_history=True,
            source="ocr_confirmed_snapshot",
        )
        await session.commit()

    await rebuild_simulation_account_projection(auth=auth, redis=redis)

    # 5. 捕获快照
    await _capture_simulation_snapshot(redis)

    return {
        "success": True,
        "message": f"持仓同步成功，初始资产已对齐至 {calculated_initial_cash:,.2f}",
    }
