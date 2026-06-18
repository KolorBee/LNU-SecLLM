from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.agent import QMTAgent


def test_run_forever_waits_until_external_stop_event() -> None:
    agent = object.__new__(QMTAgent)
    agent.stop_event = threading.Event()
    started = threading.Event()
    external_stop_event = threading.Event()

    def _fake_start() -> None:
        started.set()

    agent.start = _fake_start  # type: ignore[method-assign]

    worker = threading.Thread(
        target=QMTAgent.run_forever,
        args=(agent,),
        kwargs={"external_stop_event": external_stop_event, "poll_interval_seconds": 0.05},
        daemon=True,
    )
    worker.start()

    assert started.wait(0.5)
    assert worker.is_alive()

    external_stop_event.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_run_forever_waits_until_agent_stop_event() -> None:
    agent = object.__new__(QMTAgent)
    agent.stop_event = threading.Event()
    started = threading.Event()

    def _fake_start() -> None:
        started.set()

    agent.start = _fake_start  # type: ignore[method-assign]

    worker = threading.Thread(
        target=QMTAgent.run_forever,
        args=(agent,),
        kwargs={"poll_interval_seconds": 0.05},
        daemon=True,
    )
    worker.start()

    assert started.wait(0.5)
    assert worker.is_alive()

    agent.stop_event.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()
