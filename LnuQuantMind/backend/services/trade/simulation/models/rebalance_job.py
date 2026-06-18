"""
Simulation rebalance/scheduled job model.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.services.trade.simulation.models import Base, TimestampMixin


class SimulationRebalanceJob(Base, TimestampMixin):
    __tablename__ = "simulation_rebalance_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rebalance")
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False, default="interval")
    planned_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "idx_sim_rebalance_jobs_owner_status",
            "tenant_id",
            "user_id",
            "status",
        ),
    )
