import os
import sys
import types
from contextlib import asynccontextmanager
from datetime import date

import pytest

os.environ["DEBUG"] = "false"
os.environ["debug"] = "false"

auth_module = types.ModuleType("backend.services.api.user_app.middleware.auth")
auth_module.get_current_user = lambda: {}
sys.modules.setdefault("backend.services.api.user_app.middleware.auth", auth_module)

from backend.services.api.routers import research


class _FakeMappingsResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _FakeMappingsResult(self._rows)


def test_format_candidate_record_keeps_missing_returns_nullable():
    payload = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SH605006",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "return_1d": None,
            "return_3d": None,
        }
    )

    assert payload["nextDayReturn"] is None
    assert payload["day3Return"] is None


def test_format_candidate_record_keeps_bidirectional_volume_trend():
    payload_up = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SH600000",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "volume_trend_3d": 1,
        }
    )
    payload_down = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SH600001",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "volume_trend_3d": -1,
        }
    )
    payload_flat = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SH600002",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "volume_trend_3d": 0,
        }
    )

    assert payload_up["volumeTrend3d"] == pytest.approx(1.0)
    assert payload_down["volumeTrend3d"] == pytest.approx(-1.0)
    assert payload_flat["volumeTrend3d"] == pytest.approx(0.0)


def test_format_candidate_record_falls_back_to_stock_index_json(tmp_path, monkeypatch):
    stock_index = tmp_path / "stocks_index.json"
    stock_index.write_text(
        '{"items": [{"symbol": "SZ300274", "code": "300274", "name": "阳光电源"}]}',
        encoding="utf-8",
    )

    research_service = research._research_service  # noqa: SLF001
    research_service._STOCK_META_CACHE.clear()  # noqa: SLF001
    monkeypatch.setenv("STOCK_INDEX_JSON_PATH", str(stock_index))
    monkeypatch.setattr(research_service, "_STOCK_INDEX_JSON_PATH", str(stock_index))

    payload = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SZ300274",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "stock_name": "",
        }
    )

    assert payload["name"] == "阳光电源"


def test_format_candidate_record_falls_back_to_stock_index_industry(tmp_path, monkeypatch):
    stock_index = tmp_path / "stocks_index.json"
    stock_index.write_text(
        '{"items": [{"symbol": "SZ300274", "code": "300274", "name": "阳光电源", "csrc1_industry":"制造业"}]}',
        encoding="utf-8",
    )

    research_service = research._research_service  # noqa: SLF001
    research_service._STOCK_META_CACHE.clear()  # noqa: SLF001
    monkeypatch.setenv("STOCK_INDEX_JSON_PATH", str(stock_index))
    monkeypatch.setattr(research_service, "_STOCK_INDEX_JSON_PATH", str(stock_index))

    payload = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SZ300274",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "industry": "",
        }
    )

    assert payload["sector"] == "制造业"


def test_format_candidate_record_normalizes_amount_wanyuan_to_yi():
    payload = research._format_candidate_record(  # noqa: SLF001
        {
            "symbol": "SH600000",
            "run_id": "run_demo",
            "fusion_score": 0.1,
            "amount": 16385.371147,  # 万元口径
        }
    )

    assert payload["amount"] == pytest.approx(1.6385)


@pytest.mark.asyncio
async def test_do_get_overview_uses_run_date_market_snapshot(monkeypatch):
    class _FakeSession:
        async def execute(self, statement, params=None):
            if "COUNT(*) AS total_count" in str(statement):
                return _FakeResult(
                    [
                        {
                            "total_count": 1,
                            "tradable_count": 1,
                            "hs300_count": 0,
                            "zz1000_count": 1,
                            "margin_count": 0,
                            "chinext_count": 0,
                            "avg_score": 0.0629,
                            "high_confidence_count": 0,
                            "strong_count": 1,
                            "last_updated_at": None,
                        }
                    ]
                )
            return _FakeResult(
                [
                    {
                        "run_id": "run_20260401_4b8db856",
                        "model_id": "mdl_demo",
                        "symbol": "SH605006",
                        "score_rank": 6,
                        "fusion_score": 0.0629,
                        "stock_name": "山东玻纤",
                        "industry": "制造业",
                        "latest_change_pct": 10.0,
                        "turnover_rate": 2.82,
                        "amount": 163853711.47,
                        "total_mv": 922090646.95,
                        "float_mv": 500000000.0,
                        "listed_days": 800,
                        "close_price": 12.37,
                        "return_1d": -1.96443007,
                        "return_3d": -4.34,
                        "concept_tags": ["玻纤"],
                        "index_tags": ["中证1000"],
                        "risk_flags": [],
                        "is_st": False,
                        "is_hs300": False,
                        "is_csi1000": True,
                    }
                ]
            )

    @asynccontextmanager
    async def _fake_get_session(read_only=True):
        yield _FakeSession()

    monkeypatch.setattr(research, "get_session", _fake_get_session)

    result = await research._do_get_overview(  # noqa: SLF001
        tid="default",
        uid="10000001",
        model_id=None,
        run_id="run_20260401_4b8db856",
        limit=1000,
        offset=0,
    )

    item = result["items"][0]
    assert item["latestChange"] == pytest.approx(10.0)
    assert item["nextDayReturn"] == pytest.approx(-1.96443007)
    assert item["day3Return"] == pytest.approx(-4.34)
    assert "(sdl_run.close_next_1d / NULLIF(sdl_run.close, 0) - 1) * 100" in research._research_service._SDL_SELECT_BY_RUN_DATE  # noqa: SLF001
    assert "(sdl_run.close_next_3d / NULLIF(sdl_run.close, 0) - 1) * 100" in research._research_service._SDL_SELECT_BY_RUN_DATE  # noqa: SLF001


def test_invalid_sdl_symbols_cache_detects_decimal_returns():
    trade_date = date(2026, 6, 11)
    symbol_map = {
        f"SH600{i:03d}": {"return_1d": 0.02, "return_3d": 0.08}
        for i in range(25)
    }

    assert research._research_service._is_invalid_sdl_symbols_cache(trade_date, symbol_map) is True  # noqa: SLF001


@pytest.mark.asyncio
async def test_load_sdl_day_map_does_not_fallback_trade_date(monkeypatch):
    calls = {"count": 0}
    research_service = research._research_service  # noqa: SLF001

    class _FakeMarketSession:
        async def execute(self, statement, params=None):
            calls["count"] += 1
            return _FakeResult([])

    @asynccontextmanager
    async def _fake_market_session():
        yield _FakeMarketSession()

    monkeypatch.setattr(research_service, "_load_sdl_from_remote_redis", lambda trade_date: {})
    monkeypatch.setattr(research_service, "_redis_get_json", lambda key: None)
    monkeypatch.setattr(research_service, "_redis_set_json", lambda key, value, ttl_seconds: None)
    monkeypatch.setattr(research_service, "get_market_session", _fake_market_session)

    result = await research_service._load_sdl_day_map(None, date(2026, 6, 11))  # noqa: SLF001

    assert result == {}
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_get_research_universe_uses_short_ttl_cache(monkeypatch):
    calls = {"count": 0}
    research_service = research._research_service  # noqa: SLF001
    research_service._UNIVERSE_CACHE.clear()  # noqa: SLF001

    async def _fake_do_get_universe_with_sdl_redis(*args, **kwargs):
        calls["count"] += 1
        return {"items": [{"runId": "run_demo"}], "summary": {"total": 1}}

    monkeypatch.setattr(research_service, "_do_get_universe_with_sdl_redis", _fake_do_get_universe_with_sdl_redis)

    payload_1 = await research_service.get_research_universe("default", "u1", "run_demo", 1000)
    payload_2 = await research_service.get_research_universe("default", "u1", "run_demo", 1000)

    assert calls["count"] == 1
    assert payload_1 == payload_2


@pytest.mark.asyncio
async def test_get_stock_kline_uses_sdl_cache(monkeypatch):
    calls = {"count": 0}
    research_service = research._research_service  # noqa: SLF001
    research_service._SDL_CACHE.clear()  # noqa: SLF001

    class _FakeSession:
        async def execute(self, statement, params=None):
            calls["count"] += 1
            return _FakeResult(
                [
                    {
                        "trade_date": "2026-05-09",
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.2,
                        "volume": 1000000.0,
                    },
                    {
                        "trade_date": "2026-05-08",
                        "open": 9.9,
                        "high": 10.1,
                        "low": 9.7,
                        "close": 10.0,
                        "volume": 900000.0,
                    },
                ]
            )

    @asynccontextmanager
    async def _fake_market_session():
        yield _FakeSession()

    monkeypatch.setattr(research_service, "get_market_session", _fake_market_session)

    payload_1 = await research_service.get_stock_kline("sh600000", 2)
    payload_2 = await research_service.get_stock_kline("SH600000", 2)

    assert calls["count"] == 1
    assert payload_1 == payload_2
    assert payload_1["data"]["symbol"] == "SH600000"
