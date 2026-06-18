"""
Simulation position daily snapshot model.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationPositionDaily(Base, TimestampMixin):
    __tablename__ = "simulation_position_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    position_side: Mapped[str] = mapped_column(
        String(16), nullable=False, default="long", index=True
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    available_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    frozen_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    close_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    market_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    __table_args__ = (
        Index(
            "idx_sim_position_daily_owner_symbol_time",
            "tenant_id",
            "user_id",
            "symbol",
            "snapshot_at",
        ),
        Index(
            "idx_sim_position_daily_owner_symbol_date",
            "tenant_id",
            "user_id",
            "symbol",
            "snapshot_date",
        ),
    )
