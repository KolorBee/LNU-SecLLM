"""
Simulation ledger-native order model.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationOrderV2(Base, TimestampMixin):
    __tablename__ = "simulation_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, index=True
    )
    client_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    strategy_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    legacy_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    position_side: Mapped[str] = mapped_column(String(16), nullable=False, default="long")
    trade_action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(16), nullable=False, default="DAY")
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    trading_session_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_simulation_orders_owner_status", "tenant_id", "user_id", "status"),
        Index("idx_simulation_orders_owner_created", "tenant_id", "user_id", "created_at"),
    )
