"""Shared schedule/reporting policy for QMT Agent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SchedulePolicy:
    trading_session_label: str = "周一至周五 09:00-11:30 / 13:00-15:00"
    offhours_report_interval_seconds: int = 30 * 60

    def is_trading_session(self, now: datetime | None = None) -> bool:
        current = now or datetime.now()
        if current.weekday() >= 5:
            return False
        hm = current.hour * 60 + current.minute
        return (9 * 60 <= hm < 11 * 60 + 30) or (13 * 60 <= hm < 15 * 60)

    def current_reporting_mode(self, now: datetime | None = None) -> str:
        return "trading" if self.is_trading_session(now) else "offhours"

    def seconds_until_transition(self, now: datetime | None = None) -> int:
        current = now or datetime.now()
        boundaries: list[datetime] = []
        if current.weekday() < 5:
            for hour, minute in ((9, 0), (11, 30), (13, 0), (15, 0)):
                boundary = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if boundary > current:
                    boundaries.append(boundary)
        if boundaries:
            next_boundary = min(boundaries)
            return max(1, int((next_boundary - current).total_seconds()))

        next_day = current + timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        next_boundary = next_day.replace(hour=9, minute=0, second=0, microsecond=0)
        return max(1, int((next_boundary - current).total_seconds()))

    def schedule_wait_seconds(self, trading_session: bool, now: datetime | None = None) -> int:
        transition = self.seconds_until_transition(now)
        cap = 30 if trading_session else 60
        return max(1, min(cap, transition))

    def effective_report_interval_seconds(
        self,
        base_seconds: int,
        *,
        schedule_mode: str | None = None,
        now: datetime | None = None,
    ) -> int:
        base = max(1, int(base_seconds or 1))
        mode = schedule_mode or self.current_reporting_mode(now)
        if mode == "trading":
            return base
        return max(base, int(self.offhours_report_interval_seconds))

    def report_wait_seconds(
        self,
        base_seconds: int,
        *,
        schedule_mode: str | None = None,
        now: datetime | None = None,
    ) -> int:
        return max(
            1,
            min(
                self.effective_report_interval_seconds(base_seconds, schedule_mode=schedule_mode, now=now),
                self.seconds_until_transition(now),
            ),
        )
