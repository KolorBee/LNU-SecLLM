"""
Simulation rebalance job persistence service.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from backend.services.trade.simulation.models.rebalance_job import SimulationRebalanceJob
from backend.shared.database_manager_v2 import get_session


class SimulationRebalanceJobService:
    @staticmethod
    async def ensure_job(
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
        strategy_id: str,
        schedule_type: str,
        planned_run_at: datetime,
        window_seconds: int,
        idempotency_key: str,
    ) -> None:
        async with get_session(read_only=False) as session:
            row = (
                await session.execute(
                    select(SimulationRebalanceJob).where(
                        SimulationRebalanceJob.job_id == job_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = SimulationRebalanceJob(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    job_type="rebalance",
                    schedule_type=schedule_type,
                    planned_run_at=planned_run_at,
                    window_start_at=planned_run_at,
                    window_end_at=planned_run_at + timedelta(seconds=max(1, int(window_seconds))),
                    status="pending",
                    idempotency_key=idempotency_key,
                )
                session.add(row)
            else:
                row.schedule_type = schedule_type
                row.planned_run_at = planned_run_at
                row.window_start_at = planned_run_at
                row.window_end_at = planned_run_at + timedelta(seconds=max(1, int(window_seconds)))
                row.idempotency_key = idempotency_key
                if str(row.status or "").lower() in {"failed", "expired", "skipped"}:
                    row.status = "pending"
                    row.last_error = None
                    row.started_at = None
                    row.finished_at = None

    @staticmethod
    async def mark_ready(job_id: str) -> None:
        async with get_session(read_only=False) as session:
            row = (
                await session.execute(
                    select(SimulationRebalanceJob).where(
                        SimulationRebalanceJob.job_id == job_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            if str(row.status or "").lower() in {"pending", "ready"}:
                row.status = "ready"
                row.last_error = None

    @staticmethod
    async def mark_started(job_id: str) -> None:
        async with get_session(read_only=False) as session:
            row = (
                await session.execute(
                    select(SimulationRebalanceJob).where(
                        SimulationRebalanceJob.job_id == job_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.status = "running"
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.started_at = datetime.utcnow()
            row.last_error = None

    @staticmethod
    async def mark_skipped(job_id: str, *, last_error: str | None = None) -> None:
        async with get_session(read_only=False) as session:
            row = (
                await session.execute(
                    select(SimulationRebalanceJob).where(
                        SimulationRebalanceJob.job_id == job_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.status = "skipped"
            row.finished_at = datetime.utcnow()
            row.last_error = (str(last_error).strip() or None) if last_error else None

    @staticmethod
    async def expire_outdated_jobs(*, now: datetime) -> int:
        expired = 0
        async with get_session(read_only=False) as session:
            rows = (
                await session.execute(
                    select(SimulationRebalanceJob).where(
                        SimulationRebalanceJob.status.in_(("pending", "ready")),
                        SimulationRebalanceJob.window_end_at.is_not(None),
                        SimulationRebalanceJob.window_end_at < now,
                    )
                )
            ).scalars().all()
            for row in rows:
                row.status = "expired"
                row.finished_at = now
                row.last_error = "execution window elapsed before scheduler could run"
                expired += 1
        return expired

    @staticmethod
    async def mark_finished(job_id: str, *, status: str, last_error: str | None = None) -> None:
        async with get_session(read_only=False) as session:
            row = (
                await session.execute(
                    select(SimulationRebalanceJob).where(
                        SimulationRebalanceJob.job_id == job_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.status = status
            row.finished_at = datetime.utcnow()
            row.last_error = (str(last_error).strip() or None) if last_error else None
