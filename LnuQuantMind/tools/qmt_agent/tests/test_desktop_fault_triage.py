from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.triage import classify_runtime_fault


def test_fault_triage_flags_stopped_agent() -> None:
    result = classify_runtime_fault(
        {
            "runtime_state": "stopped",
            "runtime_health": "healthy",
            "qmt_connected": False,
        }
    )

    assert result["layer"] == "本地运行态"
    assert "已停止" in result["reason"]


def test_fault_triage_flags_bridge_failure() -> None:
    result = classify_runtime_fault(
        {
            "runtime_state": "running",
            "runtime_health": "healthy",
            "qmt_connected": True,
            "last_bridge_connect_at": None,
        }
    )

    assert result["layer"] == "云端连接"
    assert "bridge" in result["reason"]


def test_fault_triage_prefers_runtime_staleness() -> None:
    result = classify_runtime_fault(
        {
            "runtime_state": "running",
            "runtime_health": "stale",
            "heartbeat_age_seconds": 101,
            "account_age_seconds": 121,
            "worker_threads": {"bridge-heartbeat": False},
        }
    )

    assert result["layer"] == "本地运行态"
    assert "心跳" in result["reason"]
    assert "线程" in result["reason"]
