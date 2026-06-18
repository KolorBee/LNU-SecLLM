"""
Simulation account daily snapshot model.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationAccountDaily(Base, TimestampMixin):
    __tablename__ = "simulation_account_daily"

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
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    available_cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    frozen_cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    long_market_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    short_market_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_asset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    liabilities: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    __table_args__ = (
        Index(
            "idx_sim_account_daily_owner_time",
            "tenant_id",
            "user_id",
            "snapshot_at",
        ),
        Index(
            "idx_sim_account_daily_owner_date",
            "tenant_id",
            "user_id",
            "snapshot_date",
        ),
    )
