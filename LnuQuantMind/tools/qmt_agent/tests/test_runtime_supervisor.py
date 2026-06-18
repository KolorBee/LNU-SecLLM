from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.runtime_supervisor import RestartPolicy, RuntimeSupervisor


class _FakeAgent:
    def __init__(self, stop_event: threading.Event, crash_once: list[bool]) -> None:
        self.stop_event = threading.Event()
        self._external_stop_event = stop_event
        self._crash_once = crash_once
        self.stopped = False

    def run_forever(self, external_stop_event: threading.Event | None = None) -> None:
        if self._crash_once and self._crash_once.pop(0):
            raise RuntimeError("boom")
        assert external_stop_event is self._external_stop_event
        external_stop_event.set()

    def stop(self) -> None:
        self.stopped = True
        self.stop_event.set()


def test_runtime_supervisor_restarts_after_crash_and_clears_agent() -> None:
    shutdown_event = threading.Event()
    created: list[_FakeAgent] = []
    cleared: list[_FakeAgent] = []
    crash_once = [True, False]

    supervisor = RuntimeSupervisor(
        agent_factory=lambda: _FakeAgent(shutdown_event, crash_once),
        stop_event=shutdown_event,
        policy=RestartPolicy(
            auto_restart_on_crash=True,
            restart_base_delay_seconds=0,
            restart_max_delay_seconds=0,
            restart_window_seconds=60,
            restart_max_attempts_per_window=3,
        ),
        logger=logging.getLogger("test-runtime-supervisor"),
        service_name="test-runtime-supervisor",
        on_agent_created=created.append,
        on_agent_cleared=cleared.append,
    )

    result = supervisor.run()

    assert result == 0
    assert len(created) == 2
    assert len(cleared) == 2
    assert all(agent.stopped for agent in cleared)
