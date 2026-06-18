from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.qmt_agent.agent as agent_mod


class _FakeStopEvent:
    def __init__(self) -> None:
        self._set = False

    def is_set(self) -> bool:
        return self._set


class _FakeDirtyEvent:
    def __init__(self, responses: list[bool], clock: list[float]) -> None:
        self._responses = list(responses)
        self._clock = clock
        self.clear_calls = 0
        self.wait_timeouts: list[float] = []

    def wait(self, timeout: float | None = None) -> bool:
        timeout = float(timeout or 0.0)
        self.wait_timeouts.append(timeout)
        if self._responses:
            result = self._responses.pop(0)
        else:
            result = False
        # 模拟等待过程中的时间流逝，便于测试 deadline 重置逻辑。
        self._clock[0] += timeout / 2 if result else timeout + 0.1
        return result

    def clear(self) -> None:
        self.clear_calls += 1


def test_wait_for_snapshot_settle_coalesces_bursty_dirty_events(monkeypatch) -> None:
    clock = [100.0]
    fake_dirty = _FakeDirtyEvent([True, True, False], clock)
    fake_stop = _FakeStopEvent()
    agent = object.__new__(agent_mod.QMTAgent)
    agent._dirty_event = fake_dirty
    agent.stop_event = fake_stop

    monkeypatch.setattr(agent_mod.time, "time", lambda: clock[0])

    settled = agent._wait_for_snapshot_settle(1)

    assert settled is True
    assert fake_dirty.clear_calls >= 2
    assert fake_dirty.wait_timeouts[0] == 1.0
    assert fake_dirty.wait_timeouts[1] == 1.0
