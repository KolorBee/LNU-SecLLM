from __future__ import annotations

import json
import queue
import sys
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.agent import QMTAgent


class _FakeReporter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def report_execution(self, payload: dict) -> None:
        self.events.append(dict(payload))


def _make_agent(queue_maxsize: int = 5) -> QMTAgent:
    agent = object.__new__(QMTAgent)
    agent.cfg = SimpleNamespace(account_id="8886664999")
    agent.reporter = _FakeReporter()
    agent._state_lock = RLock()
    agent._dispatch_metrics_lock = RLock()
    agent._dispatch_seq = 0
    agent._dispatch_queue_maxsize = queue_maxsize
    agent._dispatch_submit_interval_ms = 50
    agent._dispatch_queue = queue.PriorityQueue(maxsize=queue_maxsize)
    agent._dispatch_enqueued = 0
    agent._dispatch_dropped = 0
    agent._dispatch_processed = 0
    agent._dispatch_max_queue_depth = 0
    agent._dispatch_last_queue_wait_ms = 0
    agent._dispatch_last_submit_at = None
    agent._dispatch_last_submit_kind = ""
    agent._threads = {}
    return agent


def test_cancel_has_higher_dispatch_priority_than_order() -> None:
    agent = _make_agent()

    assert agent._enqueue_dispatch("order", {"client_order_id": "cid-order"}, priority=1) is True
    assert agent._enqueue_dispatch("cancel", {"client_order_id": "cid-cancel"}, priority=0) is True

    first = agent._dispatch_queue.get_nowait()
    second = agent._dispatch_queue.get_nowait()

    assert first[2]["kind"] == "cancel"
    assert second[2]["kind"] == "order"


def test_queue_full_rejects_new_order_and_reports_execution() -> None:
    agent = _make_agent(queue_maxsize=1)
    agent._dispatch_queue.put_nowait((1, 1, {"kind": "order", "payload": {"client_order_id": "existing"}}))

    accepted = agent._enqueue_dispatch(
        "order",
        {
            "client_order_id": "cid-overflow",
            "symbol": "600000.SH",
            "side": "BUY",
        },
        priority=1,
    )

    assert accepted is False
    assert agent._dispatch_dropped == 1
    assert len(agent.reporter.events) == 1
    event = agent.reporter.events[0]
    assert event["client_order_id"] == "cid-overflow"
    assert event["status"] == "REJECTED"
    assert "派单队列已满" in event["message"]


def test_on_message_enqueues_order_without_direct_execution() -> None:
    agent = _make_agent()

    agent.on_message(
        None,
        json.dumps(
            {
                "type": "order",
                "payload": {"client_order_id": "cid-queued", "symbol": "600000.SH", "side": "BUY"},
            }
        ),
    )

    queued = agent._dispatch_queue.get_nowait()
    assert queued[2]["kind"] == "order"
    assert queued[2]["payload"]["client_order_id"] == "cid-queued"
