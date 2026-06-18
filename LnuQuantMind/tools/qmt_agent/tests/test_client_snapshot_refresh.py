from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from threading import RLock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qmt_agent.client import QMTClient


class _FakeTrader:
    def __init__(self, asset: object, positions: list[object]) -> None:
        self._asset = asset
        self._positions = positions

    def query_stock_asset(self, account: object) -> object:
        return self._asset

    def query_stock_positions(self, account: object) -> list[object]:
        return list(self._positions)

    def query_stk_compacts(self, account: object) -> list[object]:
        return []

    def query_credit_subjects(self, account: object) -> list[object]:
        return []


def _make_client(old_asset: object, old_positions: list[object], fresh_asset: object, fresh_positions: list[object]) -> QMTClient:
    client = object.__new__(QMTClient)
    client.cfg = SimpleNamespace(
        account_id="8886664999",
        account_type="STOCK",
        enable_short_trading=False,
        short_check_cache_ttl_sec=30,
    )
    client.enabled = True
    client._execution_callback = None
    client._work_path = None
    client._last_asset_cache = old_asset
    client._last_positions_cache = list(old_positions)
    client._cache_lock = RLock()
    client._query_lock = RLock()
    client._lock = RLock()
    client._trader = _FakeTrader(fresh_asset, fresh_positions)
    client._account = object()
    client._last_short_check_at = None
    client._shortable_symbols_count = 0
    client._short_quota_cache = {}
    client._reconnect_event = None
    client.xtquant_error = ""
    client.xtquant_search_paths = []
    client._XtQuantTrader = None
    client._XtQuantTraderCallback = object
    client._StockAccount = None
    client._xtconstant = None
    client._xtdata = None
    return client


def _asset(total_asset: float, cash: float, market_value: float, today_pnl: float, total_pnl: float, floating_pnl: float) -> object:
    return SimpleNamespace(
        cash=cash,
        available_cash=cash,
        total_asset=total_asset,
        market_value=market_value,
        frozen_cash=max(0.0, total_asset - cash - market_value),
        today_pnl=today_pnl,
        total_pnl=total_pnl,
        floating_pnl=floating_pnl,
    )


def _position(symbol: str, volume: int, cost_price: float, last_price: float) -> object:
    return SimpleNamespace(
        stock_code=symbol,
        volume=volume,
        can_use_volume=volume,
        cost_price=cost_price,
        last_price=last_price,
        market_value=float(volume) * float(last_price),
    )


def test_prefer_fresh_snapshot_refreshes_cached_account_state() -> None:
    cached_asset = _asset(21_852_149.35, 5_356_712.35, 16_495_437.0, 0.0, 852_149.35, 0.0)
    cached_positions = [_position("600000.SH", 76, 21.00, 21.48)]
    fresh_asset = _asset(21_535_239.35, 5_211_798.03, 16_178_527.0, -316_910.0, 535_239.35, 0.0)
    fresh_positions = [_position("600000.SH", 77, 20.50, 21.00)]

    client = _make_client(cached_asset, cached_positions, fresh_asset, fresh_positions)

    stale_snapshot = client.snapshot()
    fresh_snapshot = client.snapshot(prefer_fresh=True)
    refreshed_snapshot = client.snapshot()

    assert stale_snapshot["total_asset"] == 21_852_149.35
    assert stale_snapshot["cash"] == 5_356_712.35
    assert fresh_snapshot["total_asset"] == 21_535_239.35
    assert fresh_snapshot["cash"] == 5_211_798.03
    assert len(fresh_snapshot["positions"]) == 1
    assert refreshed_snapshot["total_asset"] == 21_535_239.35
    assert refreshed_snapshot["cash"] == 5_211_798.03
