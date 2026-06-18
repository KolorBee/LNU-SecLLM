from datetime import datetime
from zoneinfo import ZoneInfo

from backend.services.trade.routers.real_trading_lifecycle import (
    _build_next_scheduled_execution,
    _is_native_strategy_config_without_on_tick,
    _prepare_native_simulation_bootstrap,
)


def test_native_strategy_config_without_on_tick_returns_true():
    code = """
STRATEGY_CONFIG = {"class": "RedisLongShortTopkStrategy"}
"""
    assert _is_native_strategy_config_without_on_tick(code) is True


def test_native_strategy_config_with_on_tick_returns_false():
    code = """
STRATEGY_CONFIG = {"class": "RedisLongShortTopkStrategy"}

def on_tick(context):
    context.log("tick")
"""
    assert _is_native_strategy_config_without_on_tick(code) is False


def test_prepare_native_simulation_bootstrap_shares_scheduler_scope_on_configured_minute():
    payload = _prepare_native_simulation_bootstrap(
        tenant_id="default",
        user_id="79311845",
        strategy_id="1039",
        live_trade_config={
            "schedule_type": "interval",
            "rebalance_days": 3,
            "enabled_sessions": ["AM"],
            "sell_time": "09:30",
            "buy_time": "09:30",
            "sell_first": True,
            "order_type": "MARKET",
            "max_price_deviation": 0.02,
            "max_orders_per_cycle": 20,
        },
        now=datetime(2026, 6, 9, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert payload["task_id"]
    assert payload["lock_key"]
    assert payload["trigger_context"]["dedupe_scope"] == "simulation_scheduler_shared"
    assert payload["trigger_context"]["phase"] == "ALL"
    assert payload["trigger_context"]["runner_trade_date"] == "2026-06-09"


def test_prepare_native_simulation_bootstrap_does_not_backfill_after_configured_minute():
    payload = _prepare_native_simulation_bootstrap(
        tenant_id="default",
        user_id="79311845",
        strategy_id="1039",
        live_trade_config={
            "schedule_type": "interval",
            "rebalance_days": 1,
            "enabled_sessions": ["AM"],
            "sell_time": "09:30",
            "buy_time": "09:30",
            "sell_first": True,
            "order_type": "MARKET",
            "max_price_deviation": 0.02,
            "max_orders_per_cycle": 20,
        },
        now=datetime(2026, 6, 9, 10, 40, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert payload["task_id"] is None
    assert payload["lock_key"] is None
    assert payload["trigger_context"] == {
        "source": "simulation_native_bootstrap",
        "reason": "native_strategy_config_without_on_tick",
    }


def test_prepare_native_simulation_bootstrap_keeps_legacy_mode_outside_window():
    payload = _prepare_native_simulation_bootstrap(
        tenant_id="default",
        user_id="79311845",
        strategy_id="1039",
        live_trade_config={
            "schedule_type": "interval",
            "rebalance_days": 3,
            "enabled_sessions": ["PM"],
            "sell_time": "14:45",
            "buy_time": "14:50",
        },
        now=datetime(2026, 6, 8, 10, 40, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert payload["task_id"] is None
    assert payload["lock_key"] is None
    assert payload["trigger_context"] == {
        "source": "simulation_native_bootstrap",
        "reason": "native_strategy_config_without_on_tick",
    }


def test_build_next_scheduled_execution_for_simulation_returns_next_window():
    payload = _build_next_scheduled_execution(
        current_mode="SIMULATION",
        active_data={
            "started_at": "2026-06-15T04:56:38.866883+00:00",
        },
        active_live_trade_config={
            "schedule_type": "interval",
            "rebalance_days": 3,
            "enabled_sessions": ["AM"],
            "sell_time": "09:30",
            "buy_time": "09:30",
        },
    )

    assert payload is not None
    assert payload["phase"] == "ALL"
    assert payload["trade_date"] >= "2026-06-15"
    assert payload["target_at"].endswith("+08:00")
