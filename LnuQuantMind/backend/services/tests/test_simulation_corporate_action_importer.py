from datetime import datetime

from backend.services.trade.simulation.services.corporate_action_importer import (
    load_raw_corporate_action_csv,
    map_raw_corporate_action_row,
)


def test_map_raw_dividend_bonus_per_ten_shares():
    decision = map_raw_corporate_action_row(
        {
            "symbol": "sh600857.SH",
            "code": "600857.SH",
            "date": "2026-06-01",
            "type": "1",
            "bonus": "0.45",
            "allotment": "0.0",
        },
        source="raw_csv:test.csv",
    )

    assert decision.status == "accepted"
    assert decision.reason == "cash_dividend_per_10_shares"
    assert decision.mapped is not None
    assert decision.mapped.symbol == "SH600857"
    assert decision.mapped.action_type == "dividend"
    assert decision.mapped.ex_date == datetime(2026, 6, 1)
    assert decision.mapped.cash_dividend_per_share == 0.045


def test_map_raw_large_bonus_still_divides_by_ten():
    decision = map_raw_corporate_action_row(
        {
            "symbol": "sh603658.SH",
            "code": "603658.SH",
            "date": "2026-06-01",
            "type": "1",
            "bonus": "13.1",
            "allotment": "0.0",
        },
        source="raw_csv:test.csv",
    )

    assert decision.status == "accepted"
    assert decision.mapped is not None
    assert decision.mapped.symbol == "SH603658"
    assert decision.mapped.cash_dividend_per_share == 1.31


def test_map_raw_type_15_is_skipped():
    decision = map_raw_corporate_action_row(
        {
            "symbol": "sz000793.SZ",
            "code": "000793.SZ",
            "date": "2026-06-22",
            "type": "15",
            "bonus": "0.0",
            "allotment": "0.0",
        },
        source="raw_csv:test.csv",
    )

    assert decision.status == "skipped"
    assert decision.reason == "unsupported_type"


def test_map_raw_zero_bonus_is_skipped():
    decision = map_raw_corporate_action_row(
        {
            "symbol": "sh688416.SH",
            "code": "688416.SH",
            "date": "2026-06-24",
            "type": "1",
            "bonus": "0.0",
            "allotment": "0.0",
        },
        source="raw_csv:test.csv",
    )

    assert decision.status == "skipped"
    assert decision.reason == "non_positive_bonus"


def test_load_raw_csv_reads_utf8_sig(tmp_path):
    csv_path = tmp_path / "corporate_actions.csv"
    csv_path.write_text(
        "\ufeffsymbol,code,date,type,bonus,allotment\n"
        "sh600857.SH,600857.SH,2026-06-01,1,0.45,0.0\n",
        encoding="utf-8",
    )

    decisions = load_raw_corporate_action_csv(csv_path)

    assert len(decisions) == 1
    assert decisions[0].status == "accepted"
    assert decisions[0].mapped is not None
    assert decisions[0].mapped.cash_dividend_per_share == 0.045
