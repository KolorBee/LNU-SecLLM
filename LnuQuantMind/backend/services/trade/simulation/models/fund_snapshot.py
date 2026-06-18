from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationFundSnapshot(Base, TimestampMixin):
    __tablename__ = "simulation_fund_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True, default="default")
    user_id: Mapped[str] = mapped_column(String(50), index=True)
    account_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    snapshot_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_asset: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    available_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    frozen_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    market_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    today_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(
        String(64), default="redis_simulation_account", nullable=False
    )
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
