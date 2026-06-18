"""
融资融券每日计息扫描器 (Simulation Ledger)

每日执行一次，扫描所有的仿真/模拟账户，扣除融资和融券利息。
- 融资利息基数：可用现金为负的部分
- 融券利息基数：空头头寸总市值 (short_market_value)
- 费率：年化 6%，按 365 自然日计算
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.services.trade.redis_client import redis_client
from backend.services.trade.simulation.models.account import SimulationAccount
from backend.services.trade.simulation.models.cash_ledger import SimulationCashLedger
from backend.shared.database_manager_v2 import get_session
from backend.services.trade.simulation.services.ledger_service import (
    SimulationLedgerService,
)
from backend.shared.trade_account_cache import write_json_cache, write_trade_account_cache

logger = logging.getLogger(__name__)

_INTERVAL_SEC = 3600  # 默认每小时检查一次，但内部根据上次结算时间控制每日一次


def _compute_margin_interest_charge(
    *,
    cash: float,
    short_market_value: float,
    days_diff: int,
    annual_rate: float = 0.06,
) -> float:
    cash_debt = max(0.0, -float(cash or 0.0))
    total_debt = max(0.0, float(short_market_value or 0.0)) + cash_debt
    if total_debt <= 0 or days_diff <= 0:
        return 0.0
    return total_debt * float(annual_rate) / 365.0 * int(days_diff)


async def _scan_and_settle() -> int:
    """扫描所有仿真账户，应用日计息。"""
    try:
        settled_count = 0
        now = datetime.now(timezone.utc)

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
            for account in accounts:
                try:
                    last_interest_date = (
                        await session.execute(
                            select(func.max(SimulationCashLedger.occurred_at)).where(
                                SimulationCashLedger.account_id == account.account_id,
                                SimulationCashLedger.event_type == "MARGIN_INTEREST",
                            )
                        )
                    ).scalar_one_or_none()
                    last_date = (
                        last_interest_date.date()
                        if last_interest_date is not None
                        else (
                            account.created_at.date()
                            if account.created_at is not None
                            else now.date()
                        )
                    )
                    days_diff = (now.date() - last_date).days
                    if days_diff <= 0:
                        continue

                    interest_charge = _compute_margin_interest_charge(
                        cash=float(account.cash or 0.0),
                        short_market_value=float(account.short_market_value or 0.0),
                        days_diff=days_diff,
                    )
                    if interest_charge <= 0:
                        continue

                    account.cash = float(account.cash or 0.0) - interest_charge
                    account.available_cash = float(account.available_cash or 0.0) - interest_charge
                    account.total_asset = float(account.total_asset or 0.0) - interest_charge
                    account.equity = float(account.equity or account.total_asset or 0.0) - interest_charge
                    if float(account.liabilities or 0.0) > 0:
                        account.maintenance_margin_ratio = float(account.equity or 0.0) / float(account.liabilities or 1.0)
                    account.last_projected_at = now.replace(tzinfo=None)

                    session.add(
                        SimulationCashLedger(
                            account_id=account.account_id,
                            tenant_id=account.tenant_id,
                            user_id=account.user_id,
                            event_type="MARGIN_INTEREST",
                            ref_type="interest",
                            ref_id=now.strftime("%Y-%m-%d"),
                            amount=-interest_charge,
                            balance_after=float(account.cash or 0.0),
                            trade_date=now.replace(tzinfo=None),
                            occurred_at=now.replace(tzinfo=None),
                            note=f"margin interest for {days_diff} day(s)",
                        )
                    )
                    settled_count += 1

                    if redis_client.client:
                        payload = {
                            "cash": float(account.cash or 0.0),
                            "available_cash": float(account.available_cash or 0.0),
                            "frozen_cash": float(account.frozen_cash or 0.0),
                            "market_value": float(account.long_market_value or 0.0)
                            - float(account.short_market_value or 0.0),
                            "short_market_value": float(account.short_market_value or 0.0),
                            "total_asset": float(account.total_asset or 0.0),
                            "liabilities": float(account.liabilities or 0.0),
                            "equity": float(account.equity or 0.0),
                            "maintenance_margin_ratio": float(account.maintenance_margin_ratio or 0.0),
                            "last_interest_date": now.date().isoformat(),
                            "last_interest_amount": round(float(interest_charge), 6),
                            "reprojected_from": "simulation_accounts",
                        }
                        sim_key = SimulationLedgerService.build_account_id(
                            account.tenant_id, account.user_id
                        ).replace("sim:", "simulation:account:", 1)
                        write_json_cache(redis_client, sim_key, payload)
                        write_trade_account_cache(
                            redis_client,
                            account.tenant_id,
                            account.user_id,
                            payload,
                        )

                    if interest_charge > 1:
                        logger.info(
                            "Account %s charged %.2f margin interest for %s days.",
                            account.account_id,
                            interest_charge,
                            days_diff,
                        )
                except Exception as e:
                    logger.error(
                        "Failed to process margin interest for account=%s: %s",
                        account.account_id,
                        e,
                    )

        return settled_count

    except Exception as exc:
        logger.error(f"Margin interest scan failed: {exc}", exc_info=True)
        return 0


async def run_margin_interest_scanner() -> None:
    """后台无限循环，定期执行融资融券日结计息。"""
    logger.info("Margin interest scanner started.")
    while True:
        try:
            count = await _scan_and_settle()
            if count > 0:
                logger.info(f"Margin interest scanner completed for {count} accounts.")
        except Exception as exc:
            logger.error("Margin interest scanner error: %s", exc)
        await asyncio.sleep(_INTERVAL_SEC)
