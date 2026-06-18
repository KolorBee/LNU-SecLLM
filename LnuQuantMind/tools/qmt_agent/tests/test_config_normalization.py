from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.config import normalize_agent_config_data


def test_normalize_enforces_safe_minimum_intervals() -> None:
    normalized = normalize_agent_config_data(
        {
            "heartbeat_interval_seconds": 1,
            "account_report_interval_seconds": 2,
            "reconnect_interval_seconds": 1,
            "ws_ping_interval_seconds": 1,
            "ws_ping_timeout_seconds": 1,
        }
    )

    assert normalized["heartbeat_interval_seconds"] == 10
    assert normalized["account_report_interval_seconds"] == 20
    assert normalized["reconnect_interval_seconds"] == 3
    assert normalized["ws_ping_interval_seconds"] == 20
    assert normalized["ws_ping_timeout_seconds"] == 5
