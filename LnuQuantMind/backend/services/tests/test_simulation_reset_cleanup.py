import pytest

from backend.services.trade.routers import simulation


class _FakeResult:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.committed = False
        self._rowcounts = iter([1, 2, 3])

    async def execute(self, statement, params):
        self.calls.append((str(statement), dict(params)))
        return _FakeResult(next(self._rowcounts))

    async def commit(self):
        self.committed = True


class _FakeSessionContext:
    def __init__(self, session: _FakeSession):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_purge_simulation_history_clears_user_scoped_tables(monkeypatch):
    session = _FakeSession()

    def _fake_get_session(*, read_only: bool):
        assert read_only is False
        return _FakeSessionContext(session)

    monkeypatch.setattr(simulation, "get_session", _fake_get_session)

    stats = await simulation._purge_simulation_history(
        tenant_id="tenant-a",
        user_id=1001,
    )

    assert stats == {
        "sim_trades": 1,
        "sim_orders": 2,
        "simulation_fund_snapshots": 3,
    }
    assert session.committed is True
    assert [call[1] for call in session.calls] == [
        {"tenant_id": "tenant-a", "user_id": "1001"},
        {"tenant_id": "tenant-a", "user_id": "1001"},
        {"tenant_id": "tenant-a", "user_id": "1001"},
    ]
    assert "DELETE FROM sim_trades" in session.calls[0][0]
    assert "DELETE FROM sim_orders" in session.calls[1][0]
    assert "DELETE FROM simulation_fund_snapshots" in session.calls[2][0]
