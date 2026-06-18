"""
Simulation order service.
"""

from collections import defaultdict
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.simulation.models.fill import SimulationFill
from backend.services.trade.simulation.models.order import (
    OrderSide,
    OrderStatus,
    OrderType,
    SimOrder,
    TradingMode,
)
from backend.services.trade.simulation.models.order_v2 import SimulationOrderV2
from backend.services.trade.simulation.schemas.order import SimOrderCreate
from backend.services.trade.simulation.services.migration_service import (
    SimulationMigrationService,
)
from backend.services.trade.simulation.services.projection_service import (
    SimulationProjectionService,
)
from backend.shared.stock_utils import StockCodeUtil


class SimOrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalize_query_datetime(value: datetime | None) -> datetime | None:
        """Convert timezone-aware datetimes to naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    async def create_order(
        self,
        tenant_id: str,
        user_id: int,
        data: SimOrderCreate,
        *,
        trigger_source: str = "manual",
    ):
        normalized_symbol = StockCodeUtil.to_prefix(data.symbol)
        normalized_trigger_source = (
            str(trigger_source or "manual").strip().lower() or "manual"
        )
        order_v2 = SimulationOrderV2(
            client_order_id=str(data.client_order_id or "").strip() or None,
            tenant_id=tenant_id,
            user_id=str(user_id),
            strategy_id=str(data.strategy_id) if data.strategy_id is not None else None,
            account_id=SimulationProjectionService.build_account_id(tenant_id, user_id),
            portfolio_id=int(data.portfolio_id or 0),
            legacy_order_id=None,
            symbol=normalized_symbol,
            side=str(data.side.value),
            position_side=str(data.position_side or "long"),
            trade_action=data.trade_action,
            order_type=str(data.order_type.value),
            time_in_force=str(data.time_in_force or "DAY").strip().upper() or "DAY",
            quantity=float(data.quantity),
            price=float(data.price) if data.price is not None else None,
            trigger_source=normalized_trigger_source,
            status=str(OrderStatus.PENDING.value),
            trading_session_date=date.today(),
            submitted_at=None,
            expires_at=self._normalize_query_datetime(data.expires_at),
        )
        self.db.add(order_v2)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(order_v2)
        return self._build_runtime_order(order_v2, remarks=data.remarks, is_margin_trade=data.is_margin_trade)

    async def sync_order_projection(
        self,
        order: Any,
        *,
        rejected_reason: str | None = None,
    ) -> None:
        result = await self.db.execute(
            select(SimulationOrderV2).where(SimulationOrderV2.order_id == order.order_id)
        )
        order_v2 = result.scalar_one_or_none()
        if order_v2 is None:
            return
        order_v2.status = str(order.status.value)
        order_v2.rejected_reason = rejected_reason
        order_v2.submitted_at = order.submitted_at
        order_v2.trading_session_date = getattr(order, "trading_session_date", None)
        if getattr(order, "cancelled_at", None) is not None:
            order_v2.updated_at = order.cancelled_at

    async def get_order(
        self, tenant_id: str, user_id: int, order_id: UUID
    ):
        order_v2 = (
            await self.db.execute(
                select(SimulationOrderV2).where(
                    SimulationOrderV2.tenant_id == tenant_id,
                    SimulationOrderV2.user_id == str(user_id),
                    SimulationOrderV2.order_id == order_id,
                )
            )
        ).scalar_one_or_none()
        if order_v2 is None:
            await SimulationMigrationService(self.db).ensure_history_models_backfilled(
                tenant_id=tenant_id,
                user_id=str(user_id),
            )
            order_v2 = (
                await self.db.execute(
                    select(SimulationOrderV2).where(
                        SimulationOrderV2.tenant_id == tenant_id,
                        SimulationOrderV2.user_id == str(user_id),
                        SimulationOrderV2.order_id == order_id,
                    )
                )
            ).scalar_one_or_none()
        if order_v2 is not None:
            fills = list(
                (
                    await self.db.execute(
                        select(SimulationFill)
                        .where(SimulationFill.order_id == order_v2.order_id)
                        .order_by(SimulationFill.executed_at.asc(), SimulationFill.id.asc())
                    )
                ).scalars().all()
            )
            return self._to_order_response(order_v2, fills)
        return None

    async def get_projection_order_by_client_order_id(
        self,
        tenant_id: str,
        user_id: int,
        client_order_id: str,
    ) -> SimulationOrderV2 | None:
        normalized = str(client_order_id or "").strip()
        if not normalized:
            return None
        return (
            await self.db.execute(
                select(SimulationOrderV2).where(
                    SimulationOrderV2.tenant_id == tenant_id,
                    SimulationOrderV2.user_id == str(user_id),
                    SimulationOrderV2.client_order_id == normalized,
                )
            )
        ).scalar_one_or_none()

    async def list_orders(
        self,
        tenant_id: str,
        user_id: int,
        *,
        portfolio_id: int | None = None,
        status: str | None = None,
        symbol: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        v2_conditions = [
            SimulationOrderV2.tenant_id == tenant_id,
            SimulationOrderV2.user_id == str(user_id),
        ]
        start_date = self._normalize_query_datetime(start_date)
        end_date = self._normalize_query_datetime(end_date)
        if portfolio_id is not None:
            v2_conditions.append(SimulationOrderV2.portfolio_id == portfolio_id)
        if status:
            v2_conditions.append(SimulationOrderV2.status == status.lower())
        if symbol:
            v2_conditions.append(
                SimulationOrderV2.symbol == StockCodeUtil.to_prefix(symbol)
            )
        if start_date:
            v2_conditions.append(SimulationOrderV2.created_at >= start_date)
        if end_date:
            v2_conditions.append(SimulationOrderV2.created_at <= end_date)

        v2_stmt = (
            select(SimulationOrderV2)
            .where(and_(*v2_conditions))
            .order_by(SimulationOrderV2.created_at.desc(), SimulationOrderV2.id.desc())
            .limit(limit)
            .offset(offset)
        )
        v2_orders = list((await self.db.execute(v2_stmt)).scalars().all())
        if not v2_orders:
            await SimulationMigrationService(self.db).ensure_history_models_backfilled(
                tenant_id=tenant_id,
                user_id=str(user_id),
            )
            v2_orders = list((await self.db.execute(v2_stmt)).scalars().all())
        if v2_orders:
            fills_by_order_id = await self._load_fills_by_order_ids(
                [order.order_id for order in v2_orders]
            )
            return [
                self._to_order_response(order, fills_by_order_id.get(order.order_id, []))
                for order in v2_orders
            ]
        return []

    async def cancel_order(
        self, order: Any, reason: str | None = None
    ):
        current_status = str(getattr(getattr(order, "status", None), "value", getattr(order, "status", "")) or "").lower()
        if current_status in {
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.EXPIRED.value,
        }:
            raise ValueError(f"Cannot cancel order in status: {current_status}")
        result = await self.db.execute(
            select(SimulationOrderV2).where(SimulationOrderV2.order_id == order.order_id)
        )
        order_v2 = result.scalar_one_or_none()
        if order_v2 is None:
            raise ValueError("Simulation order projection not found")
        order_v2.status = OrderStatus.CANCELLED.value
        order_v2.rejected_reason = reason
        order_v2.updated_at = datetime.now()
        await self.db.commit()
        fills = list(
            (
                await self.db.execute(
                    select(SimulationFill)
                    .where(SimulationFill.order_id == order_v2.order_id)
                    .order_by(SimulationFill.executed_at.asc(), SimulationFill.id.asc())
                )
            ).scalars().all()
        )
        return self._to_order_response(order_v2, fills)

    async def queue_order(
        self,
        order: Any,
        reason: str,
        *,
        trading_session_date: date | None = None,
    ):
        result = await self.db.execute(
            select(SimulationOrderV2).where(SimulationOrderV2.order_id == order.order_id)
        )
        order_v2 = result.scalar_one_or_none()
        if order_v2 is None:
            raise ValueError("Simulation order projection not found")
        order_v2.status = OrderStatus.PENDING.value
        order_v2.rejected_reason = reason
        order_v2.submitted_at = None
        if trading_session_date is not None:
            order_v2.trading_session_date = trading_session_date
        order_v2.updated_at = datetime.now()
        if hasattr(order, "status"):
            order.status = OrderStatus.PENDING
        if hasattr(order, "submitted_at"):
            order.submitted_at = None
        if hasattr(order, "trading_session_date") and trading_session_date is not None:
            order.trading_session_date = trading_session_date
        if hasattr(order, "remarks"):
            order.remarks = reason
        await self.db.commit()
        fills = list(
            (
                await self.db.execute(
                    select(SimulationFill)
                    .where(SimulationFill.order_id == order_v2.order_id)
                    .order_by(SimulationFill.executed_at.asc(), SimulationFill.id.asc())
                )
            ).scalars().all()
        )
        return self._to_order_response(order_v2, fills)

    async def _load_fills_by_order_ids(
        self,
        order_ids: list[UUID],
    ) -> dict[UUID, list[SimulationFill]]:
        if not order_ids:
            return {}
        rows = list(
            (
                await self.db.execute(
                    select(SimulationFill)
                    .where(SimulationFill.order_id.in_(order_ids))
                    .order_by(SimulationFill.executed_at.asc(), SimulationFill.id.asc())
                )
            ).scalars().all()
        )
        grouped: dict[UUID, list[SimulationFill]] = defaultdict(list)
        for row in rows:
            grouped[row.order_id].append(row)
        return grouped

    @staticmethod
    def _to_order_response(
        order: SimulationOrderV2,
        fills: list[SimulationFill],
    ) -> SimpleNamespace:
        filled_quantity = round(
            sum(float(fill.fill_quantity or 0.0) for fill in fills),
            6,
        )
        filled_value = round(
            sum(float(fill.gross_amount or 0.0) for fill in fills),
            2,
        )
        total_commission = round(
            sum(float(fill.commission or 0.0) for fill in fills),
            2,
        )
        average_price = round((filled_value / filled_quantity), 4) if filled_quantity > 0 else None
        filled_at = fills[-1].executed_at if fills else None
        price_source = fills[-1].price_source if fills else None
        strategy_id = (
            int(str(order.strategy_id))
            if str(order.strategy_id or "").isdigit()
            else None
        )
        status_value = str(order.status or "pending").lower()
        return SimpleNamespace(
            id=int(order.legacy_order_id or order.id),
            order_id=order.order_id,
            tenant_id=order.tenant_id,
            user_id=int(order.user_id),
            portfolio_id=int(order.portfolio_id or 0),
            strategy_id=strategy_id,
            client_order_id=order.client_order_id,
            trigger_source=str(order.trigger_source or "manual"),
            time_in_force=str(order.time_in_force or "DAY"),
            expires_at=order.expires_at,
            symbol=order.symbol,
            side=str(order.side or "").lower(),
            order_type=str(order.order_type or "").lower(),
            quantity=float(order.quantity or 0.0),
            price=float(order.price) if order.price is not None else None,
            remarks=order.rejected_reason,
            trading_mode=TradingMode.SIMULATION,
            status=status_value,
            trading_session_date=order.trading_session_date,
            filled_quantity=filled_quantity,
            average_price=average_price,
            order_value=round(float(order.quantity or 0.0) * float(order.price or 0.0), 2),
            filled_value=filled_value,
            commission=total_commission,
            submitted_at=order.submitted_at,
            filled_at=filled_at,
            cancelled_at=None if status_value != "cancelled" else order.updated_at,
            execution_model="synthetic_price",
            price_source=price_source,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _build_runtime_order(
        order_v2: SimulationOrderV2,
        *,
        remarks: str | None = None,
        is_margin_trade: bool = False,
    ) -> SimOrder:
        runtime = SimOrder(
            tenant_id=order_v2.tenant_id,
            user_id=int(order_v2.user_id),
            portfolio_id=int(order_v2.portfolio_id or 0),
            strategy_id=int(order_v2.strategy_id) if str(order_v2.strategy_id or "").isdigit() else None,
            symbol=order_v2.symbol,
            side=OrderSide(str(order_v2.side or "").lower()),
            order_type=OrderType(str(order_v2.order_type or "").lower()),
            quantity=float(order_v2.quantity or 0.0),
            price=float(order_v2.price) if order_v2.price is not None else None,
            remarks=remarks,
            status=OrderStatus(str(order_v2.status or "pending").lower()),
            trade_action=order_v2.trade_action,
            position_side=order_v2.position_side or "long",
            is_margin_trade=1 if is_margin_trade else 0,
        )
        runtime.id = int(order_v2.id)
        runtime.order_id = order_v2.order_id
        runtime.client_order_id = order_v2.client_order_id
        runtime.trigger_source = str(order_v2.trigger_source or "manual")
        runtime.time_in_force = str(order_v2.time_in_force or "DAY")
        runtime.expires_at = order_v2.expires_at
        runtime.trading_session_date = order_v2.trading_session_date
        runtime.created_at = order_v2.created_at
        runtime.updated_at = order_v2.updated_at
        runtime.submitted_at = order_v2.submitted_at
        runtime.filled_quantity = 0.0
        runtime.average_price = None
        runtime.filled_value = 0.0
        runtime.order_value = round(float(order_v2.quantity or 0.0) * float(order_v2.price or 0.0), 2)
        runtime.commission = 0.0
        runtime.total_fee = 0.0
        runtime.execution_model = "synthetic_price"
        runtime.price_source = None
        return runtime

    async def build_runtime_order_by_id(
        self,
        order_id: UUID,
    ) -> SimOrder | None:
        row = (
            await self.db.execute(
                select(SimulationOrderV2).where(SimulationOrderV2.order_id == order_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return self._build_runtime_order(row, remarks=row.rejected_reason)
