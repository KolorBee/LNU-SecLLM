from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.trade.portfolio.models import Portfolio
from backend.services.trade.services.manual_execution_service import ManualExecutionService


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.execute_count = 0
        self.flush_count = 0
        self.refresh_count = 0

    async def execute(self, _stmt):
        self.execute_count += 1
        return _ScalarResult(self.existing)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1

    async def refresh(self, value):
        self.refresh_count += 1
        if getattr(value, "id", None) is None:
            value.id = 101


@pytest.mark.asyncio
async def test_ensure_real_portfolio_reuses_existing_portfolio(monkeypatch):
    service = ManualExecutionService()
    existing = SimpleNamespace(id=7, name="existing")
    db = _FakeDb(existing=existing)

    async def _unexpected_snapshot(**_kwargs):
        raise AssertionError("不应在已有组合时读取账户快照")

    monkeypatch.setattr(service, "_load_latest_account_snapshot", _unexpected_snapshot)

    portfolio = await service._ensure_real_portfolio_for_task(
        db,
        tenant_id="tenant-a",
        user_id="42",
        strategy_id="12",
        strategy_name="默认 Top-K 选股策略",
    )

    assert portfolio is existing
    assert db.added == []
    assert db.flush_count == 0
    assert db.refresh_count == 0


@pytest.mark.asyncio
async def test_ensure_real_portfolio_auto_initializes_from_latest_snapshot(monkeypatch):
    service = ManualExecutionService()
    db = _FakeDb()

    async def _snapshot(**kwargs):
        assert kwargs == {"tenant_id": "tenant-a", "user_id": "42", "trading_mode": "REAL"}
        return {
            "total_asset": 1_000_000,
            "available_cash": 800_000,
            "market_value": 200_000,
            "account_id": "qmt-account-1",
        }

    monkeypatch.setattr(service, "_load_latest_account_snapshot", _snapshot)

    portfolio = await service._ensure_real_portfolio_for_task(
        db,
        tenant_id="tenant-a",
        user_id="42",
        strategy_id="12",
        strategy_name="默认 Top-K 选股策略",
    )

    assert isinstance(portfolio, Portfolio)
    assert portfolio in db.added
    assert db.flush_count == 1
    assert db.refresh_count == 1
    assert portfolio.tenant_id == "tenant-a"
    assert portfolio.user_id == 42
    assert portfolio.status == "active"
    assert portfolio.trading_mode == "REAL"
    assert portfolio.run_status == "running"
    assert portfolio.strategy_id == 12
    assert portfolio.initial_capital == 1_000_000
    assert portfolio.current_capital == 1_000_000
    assert portfolio.available_cash == 800_000
    assert portfolio.total_value == 1_000_000
    assert portfolio.broker_type == "QMT"
    assert portfolio.broker_account_id == "qmt-account-1"
    assert portfolio.broker_params == {"source": "manual_execution_auto_init"}


@pytest.mark.asyncio
async def test_ensure_real_portfolio_returns_none_without_snapshot(monkeypatch):
    service = ManualExecutionService()
    db = _FakeDb()

    async def _no_snapshot(**_kwargs):
        return None

    monkeypatch.setattr(service, "_load_latest_account_snapshot", _no_snapshot)

    portfolio = await service._ensure_real_portfolio_for_task(
        db,
        tenant_id="tenant-a",
        user_id="42",
        strategy_id="12",
        strategy_name="默认 Top-K 选股策略",
    )

    assert portfolio is None
    assert db.added == []
    assert db.flush_count == 0
    assert db.refresh_count == 0
