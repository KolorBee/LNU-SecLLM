from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from threading import RLock
import queue

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.qmt_agent.agent as agent_mod


class _FakeThread:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


def _make_agent(*, heartbeat_age: float, account_age: float, alive: bool) -> object:
    agent = object.__new__(agent_mod.QMTAgent)
    agent.cfg = SimpleNamespace(
        heartbeat_interval_seconds=15,
        account_report_interval_seconds=30,
        reconnect_interval_seconds=5,
    )
    agent._state_lock = RLock()
    agent._dispatch_metrics_lock = RLock()
    agent._startup_grace_seconds = 60
    now = time.time()
    agent.last_heartbeat_at = now - heartbeat_age
    agent.last_account_report_at = now - account_age
    agent.last_start_at = now - 10
    agent._dispatch_queue_maxsize = 500
    agent._dispatch_submit_interval_ms = 50
    agent._dispatch_queue = queue.PriorityQueue(maxsize=500)
    agent._dispatch_enqueued = 0
    agent._dispatch_dropped = 0
    agent._dispatch_processed = 0
    agent._dispatch_max_queue_depth = 0
    agent._dispatch_last_queue_wait_ms = 0
    agent._dispatch_last_submit_at = None
    agent._dispatch_last_submit_kind = ""
    agent._dispatch_seq = 0
    agent._schedule_lock = RLock()
    agent._schedule_mode = "trading"
    agent._threads = {
        "bridge-websocket": _FakeThread(alive),
        "bridge-refresh": _FakeThread(alive),
        "bridge-heartbeat": _FakeThread(alive),
        "bridge-account": _FakeThread(alive),
        "bridge-order-timeout": _FakeThread(alive),
        "bridge-order-dispatch": _FakeThread(alive),
        "bridge-smart-execution": _FakeThread(alive),
        "bridge-app-ping": _FakeThread(alive),
        "bridge-watchdog": _FakeThread(alive),
        "qmt-reconnect": _FakeThread(alive),
        "qmt-schedule": _FakeThread(alive),
    }
    return agent


def test_runtime_health_is_healthy_when_threads_alive_and_snapshot_is_fresh() -> None:
    agent = _make_agent(heartbeat_age=10, account_age=20, alive=True)

    health = agent._runtime_health_snapshot()

    assert health["health"] == "healthy"
    assert health["health_reason"] == ""
    assert health["heartbeat_age_seconds"] == 10
    assert health["account_age_seconds"] == 20


def test_runtime_health_marks_degraded_when_critical_thread_is_dead() -> None:
    agent = _make_agent(heartbeat_age=10, account_age=20, alive=False)

    health = agent._runtime_health_snapshot()

    assert health["health"] == "degraded"
    assert "thread_dead" in health["health_reason"]
    assert "bridge-websocket" in health["health_reason"]


def test_runtime_health_marks_stale_when_heartbeat_expires() -> None:
    agent = _make_agent(heartbeat_age=40, account_age=20, alive=True)
    agent.last_start_at = time.time() - 1000

    health = agent._runtime_health_snapshot()

    assert health["health"] == "stale"
    assert "heartbeat_stale" in health["health_reason"]


def test_runtime_health_handles_missing_initial_samples_without_crashing() -> None:
    agent = _make_agent(heartbeat_age=float("inf"), account_age=float("inf"), alive=True)

    health = agent._runtime_health_snapshot()

    assert health["health"] == "healthy"
    assert health["health_reason"] == ""
    assert health["in_startup_grace"] is True
    assert health["heartbeat_age_seconds"] is None
    assert health["account_age_seconds"] is None


def test_runtime_health_marks_stale_after_startup_grace() -> None:
    agent = _make_agent(heartbeat_age=float("inf"), account_age=float("inf"), alive=True)
    agent.last_start_at = time.time() - 1000

    health = agent._runtime_health_snapshot()

    assert health["health"] == "stale"
    assert "未上报" in health["health_reason"]


def test_runtime_health_uses_offhours_report_interval() -> None:
    agent = _make_agent(heartbeat_age=1900, account_age=1900, alive=True)
    agent._schedule_mode = "offhours"
    agent.last_start_at = time.time() - 4000

    health = agent._runtime_health_snapshot()

    assert health["health"] == "healthy"
    assert health["heartbeat_interval_seconds"] == 1800
    assert health["account_report_interval_seconds"] == 1800
