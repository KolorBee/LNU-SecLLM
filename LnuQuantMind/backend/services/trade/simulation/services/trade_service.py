"""
Simulation trade read service.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.simulation.models.fill import SimulationFill
from backend.services.trade.simulation.models.order import TradingMode
from backend.services.trade.simulation.services.migration_service import (
    SimulationMigrationService,
)


class SimTradeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_trade_response(fill: SimulationFill) -> SimpleNamespace:
        trade_value = float(fill.gross_amount or 0.0)
        total_fee = float(fill.commission or 0.0) + float(fill.stamp_duty or 0.0) + float(fill.transfer_fee or 0.0)
        return SimpleNamespace(
            id=fill.id,
            trade_id=fill.fill_id,
            order_id=fill.order_id,
            tenant_id=fill.tenant_id,
            user_id=int(fill.user_id),
            portfolio_id=int(fill.portfolio_id or 0),
            symbol=fill.symbol,
            side=str(fill.side or "").lower(),
            trading_mode=TradingMode.SIMULATION,
            quantity=float(fill.fill_quantity or 0.0),
            price=float(fill.fill_price or 0.0),
            trade_value=trade_value,
            commission=float(fill.commission or 0.0),
            stamp_duty=float(fill.stamp_duty or 0.0),
            transfer_fee=float(fill.transfer_fee or 0.0),
            total_fee=total_fee,
            executed_at=fill.executed_at,
            price_source=fill.price_source,
            session_phase=fill.session_phase,
            created_at=fill.created_at,
            updated_at=fill.updated_at,
        )

    async def get_trade(self, tenant_id: str, user_id: int, trade_id: UUID):
        fill = (
            await self.db.execute(
                select(SimulationFill).where(
                    SimulationFill.tenant_id == tenant_id,
                    SimulationFill.user_id == str(user_id),
                    SimulationFill.fill_id == trade_id,
                )
            )
        ).scalar_one_or_none()
        if fill is None:
            await SimulationMigrationService(self.db).ensure_history_models_backfilled(
                tenant_id=tenant_id,
                user_id=str(user_id),
            )
            fill = (
                await self.db.execute(
                    select(SimulationFill).where(
                        SimulationFill.tenant_id == tenant_id,
                        SimulationFill.user_id == str(user_id),
                        SimulationFill.fill_id == trade_id,
                    )
                )
            ).scalar_one_or_none()
        if fill is not None:
            return self._to_trade_response(fill)
        return None

    async def list_trades(
        self,
        tenant_id: str,
        user_id: int,
        *,
        portfolio_id: int | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        fill_conditions = [
            SimulationFill.tenant_id == tenant_id,
            SimulationFill.user_id == str(user_id),
        ]
        if portfolio_id is not None:
            fill_conditions.append(SimulationFill.portfolio_id == portfolio_id)
        if symbol:
            fill_conditions.append(SimulationFill.symbol == symbol.upper())

        fill_stmt = (
            select(SimulationFill)
            .where(and_(*fill_conditions))
            .order_by(SimulationFill.executed_at.desc(), SimulationFill.id.desc())
            .limit(limit)
            .offset(offset)
        )
        fills = list((await self.db.execute(fill_stmt)).scalars().all())
        if not fills:
            await SimulationMigrationService(self.db).ensure_history_models_backfilled(
                tenant_id=tenant_id,
                user_id=str(user_id),
            )
            fills = list((await self.db.execute(fill_stmt)).scalars().all())
        if fills:
            return [self._to_trade_response(fill) for fill in fills]
        return []

    async def get_stats(self, tenant_id: str, user_id: int, portfolio_id: int | None = None) -> dict:
        fill_conditions = [
            SimulationFill.tenant_id == tenant_id,
            SimulationFill.user_id == str(user_id),
        ]
        if portfolio_id is not None:
            fill_conditions.append(SimulationFill.portfolio_id == portfolio_id)

        fill_summary_stmt = select(
            func.count(SimulationFill.id).label("total_trades"),
            func.coalesce(func.sum(SimulationFill.gross_amount), 0.0).label("total_value"),
            func.coalesce(func.sum(SimulationFill.commission), 0.0).label("total_commission"),
            func.coalesce(func.sum(case((SimulationFill.side == "buy", 1), else_=0)), 0).label("buy_trades"),
            func.coalesce(func.sum(case((SimulationFill.side == "sell", 1), else_=0)), 0).label("sell_trades"),
        ).where(and_(*fill_conditions))
        fill_summary_row = (await self.db.execute(fill_summary_stmt)).one()
        if int(fill_summary_row.total_trades or 0) <= 0:
            await SimulationMigrationService(self.db).ensure_history_models_backfilled(
                tenant_id=tenant_id,
                user_id=str(user_id),
            )
            fill_summary_row = (await self.db.execute(fill_summary_stmt)).one()

        if int(fill_summary_row.total_trades or 0) > 0:
            day_bucket = func.date(SimulationFill.executed_at)
            fill_daily_stmt = (
                select(day_bucket.label("trade_day"), func.count(SimulationFill.id).label("trade_count"))
                .where(and_(*fill_conditions))
                .group_by(day_bucket)
                .order_by(day_bucket.asc())
            )
            fill_daily_rows = (await self.db.execute(fill_daily_stmt)).all()
            daily_counts = []
            for row in fill_daily_rows:
                trade_day = row.trade_day
                if not trade_day:
                    continue
                day_text = trade_day.isoformat()
                daily_counts.append(
                    {
                        "timestamp": f"{day_text}T00:00:00Z",
                        "value": int(row.trade_count or 0),
                        "label": "trade_count",
                    }
                )
            return {
                "daily_counts": daily_counts,
                "total_trades": int(fill_summary_row.total_trades or 0),
                "total_value": float(fill_summary_row.total_value or 0.0),
                "total_commission": float(fill_summary_row.total_commission or 0.0),
                "buy_trades": int(fill_summary_row.buy_trades or 0),
                "sell_trades": int(fill_summary_row.sell_trades or 0),
            }
        return {
            "daily_counts": [],
            "total_trades": 0,
            "total_value": 0.0,
            "total_commission": 0.0,
            "buy_trades": 0,
            "sell_trades": 0,
        }
