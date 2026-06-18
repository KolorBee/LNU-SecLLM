from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.agent import QMTAgent


def _make_agent() -> QMTAgent:
    agent = object.__new__(QMTAgent)
    agent._schedule_lock = RLock()
    agent._schedule_mode = "unknown"
    return agent


def test_trading_session_covers_morning_and_afternoon_windows() -> None:
    agent = _make_agent()

    assert agent._is_trading_session(datetime(2026, 6, 15, 9, 0, 0)) is True
    assert agent._is_trading_session(datetime(2026, 6, 15, 11, 29, 59)) is True
    assert agent._is_trading_session(datetime(2026, 6, 15, 11, 30, 0)) is False
    assert agent._is_trading_session(datetime(2026, 6, 15, 12, 0, 0)) is False
    assert agent._is_trading_session(datetime(2026, 6, 15, 13, 0, 0)) is True
    assert agent._is_trading_session(datetime(2026, 6, 15, 14, 59, 59)) is True
    assert agent._is_trading_session(datetime(2026, 6, 15, 15, 0, 0)) is False


def test_offhours_reporting_interval_is_promoted_to_30_minutes(monkeypatch) -> None:
    agent = _make_agent()
    monkeypatch.setattr(
        "tools.qmt_agent.schedule_policy.datetime",
        type(
            "_FakeDatetime",
            (),
            {"now": staticmethod(lambda: datetime(2026, 6, 15, 12, 0, 0))},
        ),
    )

    assert agent._current_reporting_mode() == "offhours"
    assert agent._effective_report_interval_seconds(15) == 1800
    assert agent._effective_report_interval_seconds(30) == 1800
