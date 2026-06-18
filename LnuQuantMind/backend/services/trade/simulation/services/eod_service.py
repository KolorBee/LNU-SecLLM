"""
Simulation end-of-day settlement service.

Runs after market close (default 15:05 Asia/Shanghai) and performs:
1. Re-mark all accounts to latest close prices via projection service
2. Write daily account/position snapshots
3. Capture fund snapshots
4. Warn about stuck pending orders
5. Rebuild Redis cache from ledger projection
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select, func

from backend.services.trade.redis_client import redis_client
from backend.services.trade.simulation.models.account import SimulationAccount
from backend.services.trade.simulation.models.order_v2 import SimulationOrderV2
from backend.services.trade.simulation.models.order import OrderStatus
from backend.services.trade.simulation.services.daily_snapshot_service import (
    SimulationDailySnapshotService,
)
from backend.services.trade.simulation.services.fund_snapshot_service import (
    SimulationFundSnapshotService,
)
from backend.services.trade.simulation.services.projection_service import (
    SimulationProjectionService,
)
from backend.shared.database_manager_v2 import get_session
from backend.shared.trade_account_cache import write_json_cache, write_trade_account_cache
from backend.shared.trading_calendar import calendar_service

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Asia/Shanghai")
_TRIGGER_TIME = time(
    *map(int, (os.getenv("SIM_EOD_TRIGGER_TIME", "15:05") or "15:05").split(":"))
)
_INTERVAL_SEC = 60


async def _should_run_eod() -> bool:
    now = datetime.now(_TZ)
    today = now.date()
    try:
        return await calendar_service.is_trading_day(
            market="SSE",
            trade_date=today,
            tenant_id="default",
            user_id="0",
        )
    except Exception:
        from datetime import timedelta
        return today.weekday() < 5


def _past_trigger_window() -> bool:
    now = datetime.now(_TZ)
    trigger_dt = datetime.combine(now.date(), _TRIGGER_TIME, tzinfo=_TZ)
    return now >= trigger_dt


async def run_simulation_eod_worker() -> None:
    logger.info(
        "Simulation EOD worker started: trigger_time=%s", _TRIGGER_TIME.strftime("%H:%M")
    )
    last_run_date: date | None = None

    while True:
        try:
            now = datetime.now(_TZ)
            today = now.date()

            if (
                last_run_date != today
                and _past_trigger_window()
                and await _should_run_eod()
            ):
                result = await _execute_eod(today)
                if result:
                    last_run_date = today
                    logger.info("Simulation EOD completed for %s", today)
        except asyncio.CancelledError:
            logger.info("Simulation EOD worker cancelled")
            raise
        except Exception as exc:
            logger.error("Simulation EOD error: %s", exc, exc_info=True)

        await asyncio.sleep(_INTERVAL_SEC)


async def _execute_eod(trade_date: date) -> bool:
    """Run the full EOD pipeline. Returns True on success."""
    try:
        async with get_session(read_only=False) as session:
            accounts = list(
                (
                    await session.execute(
                        select(SimulationAccount).where(
                            SimulationAccount.status == "active"
                        )
                    )
                ).scalars().all()
            )

            if not accounts:
                return True

            projection_svc = SimulationProjectionService(session)
            snapshot_svc = SimulationDailySnapshotService(session)

            for account in accounts:
                try:
                    projection = await projection_svc.load_projection(
                        tenant_id=account.tenant_id,
                        user_id=account.user_id,
                        latest_price_loader=lambda symbol: _load_close_price(
                            session, symbol
                        ),
                    )
                    projection_account = projection.account
                    if projection_account is None:
                        continue

                    positions = projection.positions or {}

                    long_mv = 0.0
                    short_mv = 0.0
                    for pos in positions.values():
                        if not isinstance(pos, dict):
                            continue
                        mv = float(pos.get("market_value") or 0.0)
                        side = str(pos.get("side") or "long").strip().lower()
                        if side == "short":
                            short_mv += mv
                        else:
                            long_mv += mv

                    cash = float(projection_account.cash or 0.0)
                    liabilities = float(projection_account.liabilities or 0.0)
                    total_asset = round(cash + long_mv - short_mv, 4)

                    projection_account.long_market_value = round(long_mv, 4)
                    projection_account.short_market_value = round(short_mv, 4)
                    projection_account.total_asset = total_asset
                    projection_account.equity = total_asset
                    if liabilities > 0:
                        projection_account.maintenance_margin_ratio = round(
                            total_asset / liabilities, 6
                        )
                    projection_account.last_projected_at = datetime.utcnow()

                    account_payload = (
                        SimulationProjectionService.build_cache_payload(
                            account=projection_account,
                            positions=positions,
                            source="eod_remarking",
                        )
                    )

                    await snapshot_svc.replace_daily_snapshot(
                        tenant_id=account.tenant_id,
                        user_id=account.user_id,
                        account_id=account.account_id,
                        snapshot_date=trade_date,
                        account_payload=account_payload,
                        positions=positions,
                    )

                    _rebuild_redis(
                        account=projection_account,
                        positions=positions,
                        tenant_id=account.tenant_id,
                        user_id=account.user_id,
                    )
                except Exception as exc:
                    logger.error(
                        "EOD remark failed for account=%s: %s",
                        account.account_id,
                        exc,
                        exc_info=True,
                    )

            await session.commit()

        pending_count = await _check_pending_orders()
        if pending_count > 0:
            logger.warning(
                "EOD: %d simulation order(s) still in pending status", pending_count
            )

        try:
            await SimulationFundSnapshotService.capture_all(redis_client)
        except Exception as exc:
            logger.warning("EOD fund snapshot capture failed: %s", exc)

        return True

    except Exception as exc:
        logger.error("EOD pipeline failed: %s", exc, exc_info=True)
        return False


async def _check_pending_orders() -> int:
    try:
        async with get_session(read_only=True) as session:
            result = await session.execute(
                select(func.count()).select_from(SimulationOrderV2).where(
                    SimulationOrderV2.status == OrderStatus.PENDING.value,
                )
            )
            return int(result.scalar_one_or_none() or 0)
    except Exception:
        return 0


def _rebuild_redis(
    *,
    account: SimulationAccount,
    positions: dict,
    tenant_id: str,
    user_id: str,
) -> None:
    if not redis_client.client:
        return
    payload = SimulationProjectionService.build_cache_payload(
        account=account,
        positions=positions,
        source="eod_remarking",
    )
    sim_key = f"simulation:account:{tenant_id}:{str(user_id).strip()}"
    write_json_cache(redis_client, sim_key, payload)
    write_trade_account_cache(redis_client, tenant_id, user_id, payload)


async def _load_close_price(session, symbol: str) -> float:
    from sqlalchemy import text
    from backend.shared.stock_utils import StockCodeUtil

    prefix = StockCodeUtil.to_prefix(symbol)
    suffix = StockCodeUtil.to_suffix(prefix)
    query = text(
        "SELECT close, adj_factor FROM stock_daily_latest "
        "WHERE symbol = :symbol ORDER BY trade_date DESC LIMIT 1"
    )
    for candidate in (prefix, suffix):
        result = await session.execute(query, {"symbol": candidate})
        row = result.fetchone()
        if not row:
            continue
        hfq_close = float(row[0] or 0.0)
        adj_factor = float(row[1] or 1.0)
        if hfq_close <= 0:
            continue
        return hfq_close / adj_factor if adj_factor > 0 else hfq_close
    return 0.0
