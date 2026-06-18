from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.trade.routers import simulation_batch


@pytest.mark.asyncio
async def test_simulation_batch_rejects_user_override():
    auth = SimpleNamespace(user_id=1001, tenant_id="tenant-a")

    with pytest.raises(HTTPException) as exc_info:
        await simulation_batch.trigger_simulation_step(
            {"user_id": "1002", "strategy_id": "s1"},
            db=object(),
            auth=auth,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_simulation_batch_passes_tenant_to_settler(monkeypatch):
    calls = []

    async def _fake_run_daily_settlement(db, user_id, strategy_id, *, tenant_id):
        calls.append(
            {
                "db": db,
                "user_id": user_id,
                "strategy_id": strategy_id,
                "tenant_id": tenant_id,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(
        simulation_batch.settler,
        "run_daily_settlement",
        _fake_run_daily_settlement,
    )
    db = object()
    auth = SimpleNamespace(user_id=1001, tenant_id="tenant-a")

    result = await simulation_batch.trigger_simulation_step(
        {"user_id": "1001", "strategy_id": "s1", "tenant_id": "tenant-a"},
        db=db,
        auth=auth,
    )

    assert result["status"] == "success"
    assert calls == [
        {
            "db": db,
            "user_id": 1001,
            "strategy_id": "s1",
            "tenant_id": "tenant-a",
        }
    ]
