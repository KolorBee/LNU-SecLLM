"""
Helpers for importing raw corporate action CSV files into simulation events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import csv
from pathlib import Path

from backend.shared.stock_utils import StockCodeUtil


@dataclass(slots=True)
class SimulationCorporateActionImportRow:
    symbol: str
    action_type: str
    ex_date: datetime | None
    effective_date: datetime | None
    cash_dividend_per_share: float
    share_ratio: float
    rights_price: float
    source: str
    note: str | None


@dataclass(slots=True)
class CorporateActionImportDecision:
    status: str
    reason: str
    raw_symbol: str
    raw_type: str
    raw_bonus: float
    raw_allotment: float
    mapped: SimulationCorporateActionImportRow | None = None


def _parse_float(value: str | None) -> float:
    try:
        return float(str(value or "").strip() or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d")


def map_raw_corporate_action_row(
    raw_row: dict[str, str],
    *,
    source: str,
) -> CorporateActionImportDecision:
    raw_symbol = str(raw_row.get("symbol") or "").strip()
    raw_code = str(raw_row.get("code") or "").strip()
    raw_type = str(raw_row.get("type") or "").strip()
    raw_bonus = _parse_float(raw_row.get("bonus"))
    raw_allotment = _parse_float(raw_row.get("allotment"))
    ex_date = _parse_datetime(raw_row.get("date"))

    if not raw_symbol and not raw_code:
        return CorporateActionImportDecision(
            status="skipped",
            reason="missing_symbol",
            raw_symbol=raw_symbol,
            raw_type=raw_type,
            raw_bonus=raw_bonus,
            raw_allotment=raw_allotment,
        )

    normalized_symbol = StockCodeUtil.to_prefix(raw_code or raw_symbol)

    # Current upstream CSV semantics confirmed with user samples:
    # type=1 + bonus>0 means cash dividend where bonus is "cash per 10 shares".
    if raw_type != "1":
        return CorporateActionImportDecision(
            status="skipped",
            reason="unsupported_type",
            raw_symbol=normalized_symbol,
            raw_type=raw_type,
            raw_bonus=raw_bonus,
            raw_allotment=raw_allotment,
        )

    if raw_bonus <= 0:
        return CorporateActionImportDecision(
            status="skipped",
            reason="non_positive_bonus",
            raw_symbol=normalized_symbol,
            raw_type=raw_type,
            raw_bonus=raw_bonus,
            raw_allotment=raw_allotment,
        )

    if raw_allotment > 0:
        return CorporateActionImportDecision(
            status="skipped",
            reason="unsupported_allotment_format",
            raw_symbol=normalized_symbol,
            raw_type=raw_type,
            raw_bonus=raw_bonus,
            raw_allotment=raw_allotment,
        )

    per_share_dividend = round(raw_bonus / 10.0, 6)
    note = (
        "imported_from_raw_csv"
        f"; raw_type={raw_type}"
        f"; raw_bonus_per_10_shares={raw_bonus}"
        f"; raw_allotment={raw_allotment}"
    )
    return CorporateActionImportDecision(
        status="accepted",
        reason="cash_dividend_per_10_shares",
        raw_symbol=normalized_symbol,
        raw_type=raw_type,
        raw_bonus=raw_bonus,
        raw_allotment=raw_allotment,
        mapped=SimulationCorporateActionImportRow(
            symbol=normalized_symbol,
            action_type="dividend",
            ex_date=ex_date,
            effective_date=None,
            cash_dividend_per_share=per_share_dividend,
            share_ratio=0.0,
            rights_price=0.0,
            source=source,
            note=note,
        ),
    )


def load_raw_corporate_action_csv(
    file_path: str | Path,
    *,
    source: str | None = None,
) -> list[CorporateActionImportDecision]:
    path = Path(file_path)
    resolved_source = source or f"raw_csv:{path.name}"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            map_raw_corporate_action_row(row, source=resolved_source)
            for row in reader
        ]
