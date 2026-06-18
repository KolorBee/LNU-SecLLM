"""
Apply simulation corporate actions to lots, cash ledger, and account projection.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import asyncio
import logging

from sqlalchemy import Select, or_, select
from sqlalchemy import text

from backend.services.trade.simulation.models.account import SimulationAccount
from backend.services.trade.simulation.models.cash_ledger import SimulationCashLedger
from backend.services.trade.simulation.models.corporate_action import (
    SimulationCorporateAction,
)
from backend.services.trade.simulation.models.position_lot import SimulationPositionLot
from backend.services.trade.simulation.services.projection_service import (
    SimulationProjectionService,
)
from backend.shared.stock_utils import StockCodeUtil
from backend.shared.database_manager_v2 import get_session

logger = logging.getLogger(__name__)


class SimulationCorporateActionService:
    @staticmethod
    def _merge_action_note(action: SimulationCorporateAction, summary: str) -> None:
        summary_text = str(summary or "").strip()
        if not summary_text:
            return
        existing = str(action.note or "").strip()
        action.note = f"{existing}; {summary_text}" if existing else summary_text

    @staticmethod
    def compute_dividend_cash(quantity: float, per_share: float) -> float:
        return round(max(0.0, float(quantity or 0.0)) * float(per_share or 0.0), 4)

    @staticmethod
    def compute_share_multiplier(action_type: str, share_ratio: float) -> float:
        normalized = str(action_type or "").strip().lower()
        ratio = float(share_ratio or 0.0)
        if normalized in {"bonus_share", "rights_issue"}:
            return max(0.0, 1.0 + ratio)
        if normalized in {"split", "reverse_split"}:
            return max(0.0, ratio if ratio > 0 else 1.0)
        return 1.0

    @classmethod
    async def apply_due_actions(cls, *, now: datetime | None = None) -> int:
        cutoff = now or datetime.utcnow()
        applied = 0
        async with get_session(read_only=False) as session:
            stmt: Select[tuple[SimulationCorporateAction]] = (
                select(SimulationCorporateAction)
                .where(
                    SimulationCorporateAction.status == "pending",
                    or_(
                        (
                            SimulationCorporateAction.effective_date.is_not(None)
                            & (SimulationCorporateAction.effective_date <= cutoff)
                        ),
                        (
                            SimulationCorporateAction.effective_date.is_(None)
                            & SimulationCorporateAction.ex_date.is_not(None)
                            & (SimulationCorporateAction.ex_date <= cutoff)
                        ),
                    ),
                )
                .order_by(
                    SimulationCorporateAction.effective_date.asc().nullsfirst(),
                    SimulationCorporateAction.ex_date.asc().nullsfirst(),
                    SimulationCorporateAction.id.asc(),
                )
            )
            actions = list((await session.execute(stmt)).scalars().all())
            for action in actions:
                await cls._apply_action(session=session, action=action, applied_at=cutoff)
                applied += 1
        return applied

    @classmethod
    async def _apply_action(
        cls,
        *,
        session,
        action: SimulationCorporateAction,
        applied_at: datetime,
    ) -> None:
        normalized_type = str(action.action_type or "").strip().lower()
        normalized_symbol = StockCodeUtil.to_prefix(action.symbol)
        lots = list(
            (
                await session.execute(
                    select(SimulationPositionLot).where(
                        SimulationPositionLot.symbol == normalized_symbol,
                        SimulationPositionLot.position_side == "long",
                        SimulationPositionLot.status == "open",
                        SimulationPositionLot.quantity_remaining > 0,
                    )
                )
            ).scalars().all()
        )

        if normalized_type == "dividend":
            by_account: dict[str, list[SimulationPositionLot]] = defaultdict(list)
            for lot in lots:
                by_account[str(lot.account_id)].append(lot)
            applied_accounts = 0
            for account_id, account_lots in by_account.items():
                qty = sum(float(lot.quantity_remaining or 0.0) for lot in account_lots)
                cash = cls.compute_dividend_cash(qty, float(action.cash_dividend_per_share or 0.0))
                if cash <= 0:
                    continue
                account = await session.get(SimulationAccount, account_id)
                if account is None:
                    continue
                account.cash = float(account.cash or 0.0) + cash
                account.available_cash = float(account.available_cash or 0.0) + cash
                account.total_asset = float(account.total_asset or 0.0) + cash
                account.equity = float(account.equity or account.total_asset or 0.0) + cash
                account.last_projected_at = applied_at
                session.add(
                    SimulationCashLedger(
                        account_id=account.account_id,
                        tenant_id=account.tenant_id,
                        user_id=account.user_id,
                        event_type="DIVIDEND_CASH",
                        ref_type="corporate_action",
                        ref_id=str(action.id),
                        amount=cash,
                        balance_after=float(account.cash or 0.0),
                        trade_date=applied_at,
                        occurred_at=applied_at,
                        note=f"{normalized_symbol} dividend",
                    )
                )
                await cls._refresh_account_projection(
                    session=session,
                    account_id=account.account_id,
                    applied_at=applied_at,
                )
                applied_accounts += 1
            cls._merge_action_note(
                action,
                f"dividend_applied_accounts={applied_accounts}",
            )
        elif normalized_type in {"bonus_share", "split", "reverse_split"}:
            multiplier = cls.compute_share_multiplier(normalized_type, float(action.share_ratio or 0.0))
            if multiplier <= 0:
                multiplier = 1.0
            touched_accounts: set[str] = set()
            for lot in lots:
                old_open = float(lot.quantity_open or 0.0)
                old_remaining = float(lot.quantity_remaining or 0.0)
                if old_open <= 0 or old_remaining <= 0:
                    continue
                lot.quantity_open = round(old_open * multiplier, 6)
                lot.quantity_remaining = round(old_remaining * multiplier, 6)
                if lot.quantity_open > 0:
                    lot.cost_price = round(
                        float(lot.cost_amount or 0.0) / float(lot.quantity_open),
                        6,
                    )
                touched_accounts.add(str(lot.account_id))
            for account_id in touched_accounts:
                await cls._refresh_account_projection(
                    session=session,
                    account_id=account_id,
                    applied_at=applied_at,
                )
            cls._merge_action_note(
                action,
                f"{normalized_type}_applied_accounts={len(touched_accounts)}",
            )
        elif normalized_type == "rights_issue":
            by_account: dict[str, list[SimulationPositionLot]] = defaultdict(list)
            for lot in lots:
                by_account[str(lot.account_id)].append(lot)
            applied_accounts = 0
            skipped_accounts = 0
            for account_id, account_lots in by_account.items():
                account = await session.get(SimulationAccount, account_id)
                if account is None:
                    continue
                subscribed_qty = sum(
                    max(0.0, float(lot.quantity_remaining or 0.0))
                    * max(0.0, float(action.share_ratio or 0.0))
                    for lot in account_lots
                )
                subscribed_qty = round(subscribed_qty, 6)
                if subscribed_qty <= 0:
                    continue
                total_cost = round(subscribed_qty * float(action.rights_price or 0.0), 4)
                if total_cost <= 0:
                    continue
                available_cash = float(account.available_cash or 0.0)
                if available_cash + 1e-6 < total_cost:
                    skipped_accounts += 1
                    session.add(
                        SimulationCashLedger(
                            account_id=account.account_id,
                            tenant_id=account.tenant_id,
                            user_id=account.user_id,
                            event_type="RIGHTS_SUBSCRIPTION_SKIPPED",
                            ref_type="corporate_action",
                            ref_id=str(action.id),
                            amount=0.0,
                            balance_after=float(account.cash or 0.0),
                            trade_date=applied_at,
                            occurred_at=applied_at,
                            note=(
                                f"{normalized_symbol} rights issue skipped: "
                                f"insufficient_cash available={available_cash:.4f} required={total_cost:.4f}"
                            ),
                        )
                    )
                    continue
                account.cash = float(account.cash or 0.0) - total_cost
                account.available_cash = available_cash - total_cost
                account.long_market_value = float(account.long_market_value or 0.0) + total_cost
                account.last_projected_at = applied_at
                session.add(
                    SimulationCashLedger(
                        account_id=account.account_id,
                        tenant_id=account.tenant_id,
                        user_id=account.user_id,
                        event_type="RIGHTS_SUBSCRIPTION",
                        ref_type="corporate_action",
                        ref_id=str(action.id),
                        amount=-total_cost,
                        balance_after=float(account.cash or 0.0),
                        trade_date=applied_at,
                        occurred_at=applied_at,
                        note=f"{normalized_symbol} rights issue",
                    )
                )
                session.add(
                    SimulationPositionLot(
                        account_id=account.account_id,
                        tenant_id=account.tenant_id,
                        user_id=account.user_id,
                        symbol=normalized_symbol,
                        position_side="long",
                        open_fill_id=f"corporate_action:{action.id}",
                        open_date=applied_at,
                        quantity_open=subscribed_qty,
                        quantity_remaining=subscribed_qty,
                        cost_price=float(action.rights_price or 0.0),
                        cost_amount=total_cost,
                        status="open",
                    )
                )
                await cls._refresh_account_projection(
                    session=session,
                    account_id=account.account_id,
                    applied_at=applied_at,
                )
                applied_accounts += 1
            cls._merge_action_note(
                action,
                "rights_issue_applied_accounts="
                f"{applied_accounts},skipped_accounts={skipped_accounts}",
            )

        action.status = "applied"
        action.applied_at = applied_at

    @classmethod
    async def _refresh_account_projection(
        cls,
        *,
        session,
        account_id: str,
        applied_at: datetime,
    ) -> None:
        account = await session.get(SimulationAccount, account_id)
        if account is None:
            return
        projection = await SimulationProjectionService(session).load_projection(
            tenant_id=account.tenant_id,
            user_id=account.user_id,
            latest_price_loader=lambda symbol: cls._load_latest_price(session, symbol),
        )
        positions = projection.positions or {}
        long_market_value = 0.0
        short_market_value = 0.0
        for pos in positions.values():
            if not isinstance(pos, dict):
                continue
            market_value = float(pos.get("market_value") or 0.0)
            side = str(pos.get("side") or "long").strip().lower()
            if side == "short":
                short_market_value += market_value
            else:
                long_market_value += market_value
        cash = float(account.cash or 0.0)
        liabilities = float(account.liabilities or 0.0)
        total_asset = round(cash + long_market_value - short_market_value, 4)
        account.long_market_value = round(long_market_value, 4)
        account.short_market_value = round(short_market_value, 4)
        account.total_asset = total_asset
        account.equity = total_asset
        account.last_projected_at = applied_at

    @staticmethod
    async def _load_latest_price(session, symbol: str) -> float:
        prefix_symbol = StockCodeUtil.to_prefix(symbol)
        suffix_symbol = StockCodeUtil.to_suffix(prefix_symbol)
        query = text(
            """
            SELECT close, adj_factor
            FROM stock_daily_latest
            WHERE symbol = :symbol
            ORDER BY trade_date DESC
            LIMIT 1
            """
        )
        for candidate in (prefix_symbol, suffix_symbol):
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


async def run_simulation_corporate_action_worker(interval_seconds: int = 3600) -> None:
    while True:
        try:
            await SimulationCorporateActionService.apply_due_actions()
        except Exception as exc:
            logger.error("Simulation corporate action worker failed: %s", exc, exc_info=True)
        await asyncio.sleep(max(60, int(interval_seconds or 3600)))
