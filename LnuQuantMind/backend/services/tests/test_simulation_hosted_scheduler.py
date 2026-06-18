from datetime import datetime
from zoneinfo import ZoneInfo

from backend.services.trade.services.simulation_hosted_scheduler import (
    _next_scheduled_trigger,
    _normalize_live_trade_config,
    _should_trigger,
)


def test_same_sell_buy_time_triggers_all_phase():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 1,
            "enabled_sessions": ["PM"],
            "sell_time": "14:50",
            "buy_time": "14:50",
        }
    )

    decision = _should_trigger(
        now=datetime(2026, 6, 2, 14, 50, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=None,
    )

    assert decision.should_trigger is True
    assert decision.phase == "ALL"
    assert decision.trade_date == "2026-06-02"


def test_same_sell_buy_time_only_triggers_on_configured_minute():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 1,
            "enabled_sessions": ["AM"],
            "sell_time": "09:30",
            "buy_time": "09:30",
        }
    )

    decision = _should_trigger(
        now=datetime(2026, 6, 2, 10, 40, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=None,
    )

    assert decision.should_trigger is False
    assert decision.reason == "before_window"


def test_pm_config_does_not_trigger_at_am_open():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 1,
            "enabled_sessions": ["PM"],
            "sell_time": "14:45",
            "buy_time": "14:50",
        }
    )

    decision = _should_trigger(
        now=datetime(2026, 6, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=None,
    )

    assert decision.should_trigger is False
    assert decision.reason == "outside_session"


def test_interval_schedule_uses_strategy_start_anchor():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 3,
            "enabled_sessions": ["PM"],
            "sell_time": "14:45",
            "buy_time": "14:50",
        }
    )

    decision = _should_trigger(
        now=datetime(2026, 6, 3, 14, 50, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=datetime(2026, 6, 2, tzinfo=ZoneInfo("Asia/Shanghai")).date(),
    )

    assert decision.should_trigger is False
    assert decision.reason == "interval_skip"


def test_weekly_schedule_respects_configured_weekday():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "weekly",
            "trade_weekdays": ["TUE"],
            "enabled_sessions": ["PM"],
            "sell_time": "14:45",
            "buy_time": "14:50",
        }
    )

    decision = _should_trigger(
        now=datetime(2026, 6, 2, 14, 45, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=None,
    )

    assert decision.should_trigger is True
    assert decision.phase == "SELL"


def test_scheduler_skips_non_trading_day():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 1,
            "enabled_sessions": ["PM"],
            "sell_time": "14:45",
            "buy_time": "14:50",
        }
    )

    decision = _should_trigger(
        now=datetime(2026, 6, 6, 14, 50, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=None,
    )

    assert decision.should_trigger is False
    assert decision.reason == "non_trading_day"


def test_am_same_time_interval_follows_configured_trade_days():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 3,
            "enabled_sessions": ["AM"],
            "sell_time": "09:30",
            "buy_time": "09:30",
            "sell_first": True,
            "order_type": "MARKET",
            "max_price_deviation": 0.02,
            "max_orders_per_cycle": 20,
        }
    )
    started_day = datetime(2026, 6, 3, tzinfo=ZoneInfo("Asia/Shanghai")).date()

    first_day = _should_trigger(
        now=datetime(2026, 6, 3, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=started_day,
    )
    skipped_day = _should_trigger(
        now=datetime(2026, 6, 4, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=started_day,
    )
    third_trade_day = _should_trigger(
        now=datetime(2026, 6, 8, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=started_day,
    )

    assert first_day.should_trigger is True
    assert first_day.phase == "ALL"
    assert skipped_day.should_trigger is False
    assert skipped_day.reason == "interval_skip"
    assert third_trade_day.should_trigger is True
    assert third_trade_day.phase == "ALL"


def test_next_scheduled_trigger_skips_missed_window_and_returns_next_interval_day():
    cfg = _normalize_live_trade_config(
        {
            "schedule_type": "interval",
            "rebalance_days": 3,
            "enabled_sessions": ["AM"],
            "sell_time": "09:30",
            "buy_time": "09:30",
        }
    )

    next_trigger = _next_scheduled_trigger(
        now=datetime(2026, 6, 3, 13, 9, 46, tzinfo=ZoneInfo("Asia/Shanghai")),
        live_trade_config=cfg,
        started_day=datetime(2026, 6, 3, tzinfo=ZoneInfo("Asia/Shanghai")).date(),
    )

    assert next_trigger is not None
    assert next_trigger.phase == "ALL"
    assert next_trigger.trade_date == "2026-06-08"
    assert next_trigger.target_at.isoformat() == "2026-06-08T09:30:00+08:00"
    assert next_trigger.window_end_at.isoformat() == "2026-06-08T09:31:30+08:00"
