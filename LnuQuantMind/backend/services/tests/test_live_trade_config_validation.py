from backend.services.trade.routers.real_trading_utils import (
    _default_execution_config,
    _default_live_trade_config,
    _normalize_execution_config,
    _normalize_live_trade_config,
)


def test_live_trade_config_accepts_same_sell_buy_time_for_all_phase():
    live_config = _normalize_live_trade_config(
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
        },
        _default_live_trade_config(),
    )
    execution_config = _normalize_execution_config(
        {
            "max_buy_drop": -0.03,
            "stop_loss": -0.08,
        },
        _default_execution_config(),
    )

    assert live_config["schedule_type"] == "interval"
    assert live_config["rebalance_days"] == 3
    assert live_config["enabled_sessions"] == ["AM"]
    assert live_config["sell_time"] == "09:30"
    assert live_config["buy_time"] == "09:30"
    assert live_config["order_type"] == "MARKET"
    assert execution_config["max_buy_drop"] == -0.03
    assert execution_config["stop_loss"] == -0.08
