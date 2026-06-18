"""
Simulation corporate action model.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationCorporateAction(Base, TimestampMixin):
    __tablename__ = "simulation_corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ex_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    effective_date: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    cash_dividend_per_share: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    share_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rights_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "idx_sim_corporate_actions_symbol_dates",
            "symbol",
            "ex_date",
            "effective_date",
        ),
        Index(
            "idx_sim_corporate_actions_status_effective",
            "status",
            "effective_date",
        ),
    )
