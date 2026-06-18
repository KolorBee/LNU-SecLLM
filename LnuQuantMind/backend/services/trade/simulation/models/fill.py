"""
Simulation ledger-native fill model.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationFill(Base, TimestampMixin):
    __tablename__ = "simulation_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    legacy_trade_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    strategy_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    position_side: Mapped[str] = mapped_column(String(16), nullable=False, default="long")
    trade_action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    fill_price: Mapped[float] = mapped_column(Float, nullable=False)
    fill_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    gross_amount: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stamp_duty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transfer_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    borrow_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    price_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_phase: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("idx_simulation_fills_owner_symbol", "tenant_id", "user_id", "symbol"),
        Index("idx_simulation_fills_owner_executed", "tenant_id", "user_id", "executed_at"),
    )
