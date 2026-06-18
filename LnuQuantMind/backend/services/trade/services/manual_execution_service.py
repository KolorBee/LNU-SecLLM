from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import redis as redis_lib
from fastapi import HTTPException
from sqlalchemy import text, and_, select, delete

try:
    import exchange_calendars as xcals
except ImportError:  # pragma: no cover - optional in local/unit test env
    xcals = None

from backend.services.trade.redis_client import get_redis
from backend.services.trade.trade_config import settings
from backend.shared.database_manager_v2 import get_session
from backend.shared.fundamental_aligner import fundamental_aligner
from backend.shared.strategy_storage import get_strategy_storage_service
from backend.shared.trade_redis_keys import normalize_trade_user_id

from backend.services.trade.portfolio.models import Portfolio
from backend.services.trade.models.order import Order

from .manual_execution_log_stream import manual_execution_log_stream
from .manual_execution_persistence import manual_execution_persistence

logger = logging.getLogger(__name__)

_quote_redis = None
_SH_TZ = ZoneInfo("Asia/Shanghai")


def _get_quote_redis():
    global _quote_redis
    if _quote_redis is None:
        try:
            host = os.getenv("REMOTE_QUOTE_REDIS_HOST", "quantmind-market-redis")
            port = int(os.getenv("REMOTE_QUOTE_REDIS_PORT", "6379"))
            password = os.getenv("REMOTE_QUOTE_REDIS_PASSWORD", "quantmind_market_2026")
            db = int(os.getenv("REMOTE_QUOTE_REDIS_DB", "0"))
            _quote_redis = redis_lib.Redis(
                host=host,
                port=port,
                password=password,
                db=db,
                decode_responses=True,
                socket_timeout=2,
            )
            _quote_redis.ping()
            logger.info(f"[ManualExecution] 已连接行情 Redis: {host}:{port} db={db}")
        except Exception as e:
            logger.warning(f"[ManualExecution] 无法连接行情 Redis: {e}")
            _quote_redis = None
    return _quote_redis


def _get_realtime_price(symbol: str) -> float | None:
    try:
        r = _get_quote_redis()
        if not r:
            return None
        sym = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")
        if symbol.startswith("SH"):
            key = f"stock:{sym}.SH"
        elif symbol.startswith("SZ"):
            key = f"stock:{sym}.SZ"
        elif symbol.startswith("BJ") or symbol.startswith("920"):
            key = f"stock:{sym}.BJ"
        else:
            key = f"stock:{symbol}"
        price = r.hget(key, "Now")
        if price:
            return float(price)
    except Exception as e:
        logger.debug(f"[ManualExecution] 获取 {symbol} 实时价格失败: {e}")
    return None


_TOPK_STYLE_STRATEGIES = {
    "topkdropout",
    "standard_topk",
    "alpha_cross_section",
    "momentum",
    "adaptive_drift",
    "deep_time_series",
    "volatilityweighted",
    "score_weighted",
    "weightstrategy",
}


@dataclass
class PreparedManualExecution:
    task_id: str
    tenant_id: str
    user_id: str
    strategy_id: str
    strategy_name: str
    run_id: str
    model_id: str
    prediction_trade_date: date
    trading_mode: str
    request_payload: dict[str, Any]
    run: dict[str, Any]
    strategy: dict[str, Any]


def _parse_iso_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text_value = str(value or "").strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="prediction_trade_date 缺失")
    try:
        return date.fromisoformat(text_value[:10])
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"prediction_trade_date 非法: {exc}"
        )


def _normalize_trading_mode(value: Any) -> str:
    mode = str(getattr(value, "value", value) or "").strip().upper()
    if mode not in {"REAL", "SHADOW", "SIMULATION"}:
        raise HTTPException(status_code=400, detail=f"unsupported trading_mode: {mode}")
    return mode


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _normalize_to_broker_symbol(sym: str) -> str:
    s = str(sym or "").strip().upper()
    if s.startswith("SH") and len(s) > 2:
        return f"{s[2:]}.SH"
    elif s.startswith("SZ") and len(s) > 2:
        return f"{s[2:]}.SZ"
    elif s.startswith("BJ") and len(s) > 2:
        return f"{s[2:]}.BJ"
    return s


def _manual_task_sell_buy_interval_seconds() -> int:
    raw = _to_int(os.getenv("MANUAL_TASK_SELL_BUY_INTERVAL_SECONDS"), 300)
    if raw < 0:
        return 0
    return min(raw, 3600)


def _manual_task_wait_next_account_timeout_seconds() -> int:
    raw = _to_int(
        os.getenv("MANUAL_TASK_WAIT_NEXT_ACCOUNT_TIMEOUT_SECONDS"),
        120,
    )
    return max(10, min(raw, 1800))


def _manual_task_account_poll_interval_seconds() -> int:
    raw = _to_int(os.getenv("MANUAL_TASK_ACCOUNT_POLL_INTERVAL_SECONDS"), 3)
    return max(1, min(raw, 30))


def _manual_task_buy_cancel_timeout_seconds() -> int:
    raw = _to_int(os.getenv("MANUAL_TASK_BUY_CANCEL_TIMEOUT_SECONDS"), 300)
    return max(10, min(raw, 3600))


def _parse_snapshot_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _is_cancelable_buy_status(value: Any) -> bool:
    status = str(getattr(value, "value", value) or "").strip().lower()
    return status in {"submitted", "partially_filled"}


def _rebuild_buy_orders_by_available_cash(
    buy_orders: list[dict[str, Any]],
    *,
    available_cash: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    rebuilt: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    remaining_cash = max(0.0, _to_float(available_cash, 0.0))

    for row in buy_orders:
        symbol = str(row.get("symbol") or "").strip().upper()
        reference_price = _to_float(
            row.get("reference_price") or row.get("price"),
            0.0,
        )
        if reference_price <= 0:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": "缺少买入参考价格，无法按最新资金重算",
                    "source": "buy_rebudget",
                }
            )
            continue

        planned_budget = _to_float(
            row.get("planned_budget")
            or row.get("allocated_budget")
            or row.get("estimated_notional"),
            0.0,
        )
        if planned_budget <= 0:
            lot_size = _resolve_board_lot_size(symbol)
            planned_budget = round(reference_price * lot_size, 2)

        if remaining_cash + 1e-6 < planned_budget:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": (
                        f"最新可用资金不足预分配预算 {planned_budget:.2f}，"
                        f"当前仅 {remaining_cash:.2f}"
                    ),
                    "source": "buy_rebudget",
                }
            )
            continue

        lot_size = _resolve_board_lot_size(symbol)
        quantity = _floor_board_lot(planned_budget / reference_price, lot_size)
        if quantity <= 0:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": (
                        f"预分配预算 {planned_budget:.2f} 不足以买入最小手数 {lot_size} 股"
                    ),
                    "source": "buy_rebudget",
                }
            )
            continue

        estimated_notional = round(quantity * reference_price, 2)
        if estimated_notional > remaining_cash + 1e-6:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": (
                        f"最新可用资金不足以覆盖重算买入金额 {estimated_notional:.2f}"
                    ),
                    "source": "buy_rebudget",
                }
            )
            continue

        remaining_cash = max(0.0, remaining_cash - estimated_notional)
        rebuilt_row = dict(row)
        rebuilt_row["planned_budget"] = round(planned_budget, 2)
        rebuilt_row["quantity"] = quantity
        rebuilt_row["estimated_notional"] = estimated_notional
        rebuilt_row["reason"] = "按预分配预算并基于最新可用资金顺序重算"
        rebuilt.append(rebuilt_row)

    return rebuilt, skipped, round(remaining_cash, 2)


def _rebuild_buy_orders_for_simulation_cash(
    buy_orders: list[dict[str, Any]],
    *,
    available_cash: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    """模拟盘重算买单：按当前可用资金等额分配，不沿用旧预案预算。"""
    price_drift_threshold = _to_float(
        os.getenv("SIM_BUY_REBUDGET_PRICE_DRIFT_THRESHOLD", "0.2"),
        0.2,
    )
    price_drift_threshold = min(max(price_drift_threshold, 0.0), 1.0)
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    remaining_cash = max(0.0, _to_float(available_cash, 0.0))

    for row in buy_orders:
        symbol = str(row.get("symbol") or "").strip().upper()
        plan_reference_price = _to_float(
            row.get("reference_price") or row.get("price"),
            0.0,
        )
        realtime_price = _to_float(_get_realtime_price(symbol), 0.0)
        reference_price = realtime_price if realtime_price > 0 else plan_reference_price
        drift_ratio = 0.0
        if plan_reference_price > 0 and realtime_price > 0:
            drift_ratio = abs(realtime_price - plan_reference_price) / plan_reference_price
            if drift_ratio >= price_drift_threshold:
                reference_price = realtime_price
        if reference_price <= 0:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": "缺少行情价格，无法生成模拟买单",
                    "source": "buy_rebudget_sim",
                }
            )
            continue
        candidates.append(
            dict(
                row,
                symbol=symbol,
                reference_price=reference_price,
                plan_reference_price=plan_reference_price,
                realtime_price=realtime_price,
                price_drift_ratio=round(drift_ratio, 6),
            )
        )

    if not candidates or remaining_cash <= 0:
        return [], skipped, round(remaining_cash, 2)

    rebuilt: list[dict[str, Any]] = []
    for index, row in enumerate(candidates):
        left = len(candidates) - index
        alloc_budget = remaining_cash / max(1, left)
        symbol = str(row.get("symbol") or "").strip().upper()
        reference_price = _to_float(row.get("reference_price"), 0.0)
        lot_size = _resolve_board_lot_size(symbol)
        quantity = _floor_board_lot(alloc_budget / max(reference_price, 1e-12), lot_size)
        if quantity <= 0:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": f"等额预算 {alloc_budget:.2f} 不足最小手数 {lot_size}",
                    "source": "buy_rebudget_sim",
                }
            )
            continue
        estimated_notional = round(quantity * reference_price, 2)
        if estimated_notional > remaining_cash + 1e-6:
            skipped.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": f"可用资金不足覆盖买入金额 {estimated_notional:.2f}",
                    "source": "buy_rebudget_sim",
                }
            )
            continue
        remaining_cash = max(0.0, remaining_cash - estimated_notional)
        rebuilt_row = dict(row)
        rebuilt_row["reference_price"] = reference_price
        rebuilt_row["price"] = reference_price
        rebuilt_row["planned_budget"] = round(alloc_budget, 2)
        rebuilt_row["quantity"] = quantity
        rebuilt_row["estimated_notional"] = estimated_notional
        rebuilt_row["reason"] = "模拟盘按当前可用资金等额重算买单（实时价优先）"
        rebuilt.append(rebuilt_row)

    return rebuilt, skipped, round(remaining_cash, 2)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _floor_board_lot(quantity: float, lot_size: int = 100) -> int:
    if quantity <= 0:
        return 0
    return int(quantity // lot_size) * lot_size


def _resolve_board_lot_size(symbol: str) -> int:
    s = str(symbol or "").strip().upper()
    code = s.split(".", 1)[0]
    if code.startswith("SH") and len(code) > 2:
        code = code[2:]
    elif code.startswith("SZ") and len(code) > 2:
        code = code[2:]
    elif code.startswith("BJ") and len(code) > 2:
        code = code[2:]

    if code.startswith("688"):
        return max(1, int(getattr(settings, "MIN_LOT_STAR_BOARD", 200)))
    if code.startswith("30"):
        return max(1, int(getattr(settings, "MIN_LOT_GEM_BOARD", 100)))
    if s.endswith(".BJ") or code.startswith(("8", "9")):
        return max(1, int(getattr(settings, "MIN_LOT_BJ_BOARD", 100)))
    return max(1, int(getattr(settings, "MIN_LOT_MAIN_BOARD", 100)))


def _build_preview_hash(payload: dict[str, Any]) -> str:
    # 只对稳定的"执行意图"做哈希，避免 preview->submit 间隔内实时行情波动
    # 导致参考价/估算金额变化，从而误报 409。
    strategy_context = (
        payload.get("strategy_context")
        if isinstance(payload.get("strategy_context"), dict)
        else {}
    )
    stable_context = {
        "model_id": str(strategy_context.get("model_id") or "").strip(),
        "run_id": str(strategy_context.get("run_id") or "").strip(),
        "prediction_trade_date": str(
            strategy_context.get("prediction_trade_date") or ""
        ).strip(),
        "strategy_id": str(strategy_context.get("strategy_id") or "").strip(),
        "trading_mode": str(strategy_context.get("trading_mode") or "").strip(),
    }

    def _normalize_orders(items: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return normalized
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "symbol": str(item.get("symbol") or "").strip().upper(),
                    "side": str(item.get("side") or "").strip().upper(),
                    "trade_action": str(item.get("trade_action") or "").strip().upper(),
                    "order_type": str(item.get("order_type") or "").strip().upper(),
                    "quantity": _to_int(item.get("quantity"), 0),
                }
            )
        normalized.sort(
            key=lambda row: (
                str(row.get("symbol") or ""),
                str(row.get("side") or ""),
                str(row.get("trade_action") or ""),
                str(row.get("order_type") or ""),
                _to_int(row.get("quantity"), 0),
            )
        )
        return normalized

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    stable = {
        "strategy_context": stable_context,
        "sell_orders": _normalize_orders(payload.get("sell_orders")),
        "buy_orders": _normalize_orders(payload.get("buy_orders")),
        "summary": {
            "sell_order_count": _to_int(summary.get("sell_order_count"), 0),
            "buy_order_count": _to_int(summary.get("buy_order_count"), 0),
        },
    }
    return hashlib.sha256(_stable_json(stable).encode("utf-8")).hexdigest()


def _normalize_strategy_params(strategy: dict[str, Any] | None) -> dict[str, Any]:
    params = strategy.get("parameters") if isinstance(strategy, dict) else {}
    return params if isinstance(params, dict) else {}


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _resolve_run_target_horizon_days(run: dict[str, Any] | None) -> int:
    request_payload = _parse_json_object((run or {}).get("request_json"))
    result_payload = _parse_json_object((run or {}).get("result_json"))
    for source in (request_payload, result_payload):
        horizon = _to_int(source.get("target_horizon_days"), 0)
        if horizon > 0:
            return horizon
    return 5


def _require_strict_hosted_signal_context(
    *,
    strategy_params: dict[str, Any],
    signal_rows: list[dict[str, Any]],
) -> None:
    if not signal_rows:
        raise HTTPException(
            status_code=409,
            detail="当前策略最新推理批次无可用信号，已拒绝自动托管执行",
        )

    strategy_type = str(strategy_params.get("strategy_type") or "").strip().lower()
    has_explicit_side = any(
        str(item.get("signal_side") or "").strip().lower() in {"buy", "sell"}
        for item in signal_rows
        if isinstance(item, dict)
    )
    if strategy_type in _TOPK_STYLE_STRATEGIES and not has_explicit_side:
        if _to_int(strategy_params.get("topk"), 0) <= 0:
            raise HTTPException(
                status_code=409,
                detail="当前策略缺少有效的 topk 参数，系统已拒绝回退默认 TopK 执行",
            )


def _extract_fundamental_constraints(strategy_params: dict[str, Any]) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for key, value in (strategy_params or {}).items():
        if isinstance(key, str) and key.startswith("f_"):
            constraints[key[2:]] = value
    return constraints


def _apply_fundamental_constraints_to_signal_rows(
    rows: list[dict[str, Any]],
    *,
    strategy_params: dict[str, Any],
    trade_date: date | None,
) -> tuple[list[dict[str, Any]], int]:
    if not rows or trade_date is None:
        return rows, 0

    constraints = _extract_fundamental_constraints(strategy_params)
    if not constraints:
        return rows, 0

    explicit_sell_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        side = str(row.get("signal_side") or "").strip().lower()
        if side == "sell":
            explicit_sell_rows.append(dict(row))
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        normalized = dict(row)
        normalized["symbol"] = symbol
        candidates.append(normalized)

    if not candidates:
        return explicit_sell_rows, 0

    input_symbols = [str(row["symbol"]) for row in candidates]
    filtered_symbols = set(
        fundamental_aligner.filter_instruments(
            trade_date,
            input_symbols,
            constraints=constraints,
        )
    )
    filtered_rows = [row for row in candidates if row["symbol"] in filtered_symbols]
    dropped_count = len(candidates) - len(filtered_rows)
    merged_rows = explicit_sell_rows + filtered_rows
    return merged_rows, max(0, dropped_count)


def _normalize_positions(raw_positions: Any) -> dict[str, dict[str, Any]]:
    if isinstance(raw_positions, dict):
        iterable = []
        for key, value in raw_positions.items():
            item = dict(value or {}) if isinstance(value, dict) else {}
            item.setdefault("symbol", key)
            iterable.append(item)
    elif isinstance(raw_positions, list):
        iterable = [
            dict(item or {}) for item in raw_positions if isinstance(item, dict)
        ]
    else:
        iterable = []

    positions: dict[str, dict[str, Any]] = {}
    for item in iterable:
        symbol = (
            str(item.get("symbol") or item.get("stock_code") or item.get("code") or "")
            .strip()
            .upper()
        )
        if not symbol:
            continue
        total_volume = _to_int(item.get("volume") or item.get("quantity"), 0)
        available_volume = _to_int(
            item.get("available_volume")
            or item.get("available_quantity")
            or total_volume,
            total_volume,
        )
        last_price = _to_float(
            item.get("last_price") or item.get("current_price") or item.get("price"),
            0.0,
        )
        market_value = _to_float(
            item.get("market_value"),
            last_price * total_volume if last_price > 0 else 0.0,
        )
        cost_price = _to_float(
            item.get("cost_price") or item.get("avg_cost") or item.get("avg_price"), 0.0
        )
        positions[symbol] = {
            "symbol": symbol,
            "name": str(item.get("symbol_name") or item.get("name") or "").strip(),
            "volume": total_volume,
            "available_volume": max(0, available_volume),
            "last_price": last_price,
            "cost_price": cost_price,
            "market_value": market_value,
        }
    return positions


def _filter_signal_rows(
    rows: list[dict[str, Any]],
    strategy_params: dict[str, Any],
    current_positions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sorted_rows = sorted(
        [dict(row or {}) for row in rows if isinstance(row, dict)],
        key=lambda item: (
            -_to_float(item.get("fusion_score"), float("-inf")),
            str(item.get("symbol") or ""),
        ),
    )
    strategy_type = str(strategy_params.get("strategy_type") or "").strip().lower()
    topk = max(1, _to_int(strategy_params.get("topk"), 50))
    n_drop = max(0, _to_int(strategy_params.get("n_drop"), 0))
    current_symbols = set(current_positions.keys())

    explicit_buys = [
        row
        for row in sorted_rows
        if str(row.get("signal_side") or "").strip().lower() == "buy"
    ]
    explicit_sells = [
        row
        for row in sorted_rows
        if str(row.get("signal_side") or "").strip().lower() == "sell"
    ]

    score_lookup = {
        str(row.get("symbol") or "").strip().upper(): _to_float(
            row.get("fusion_score"), -999999.0
        )
        for row in sorted_rows
    }
    inferred = False
    buy_candidates: list[dict[str, Any]]
    sell_candidates: list[dict[str, Any]] = []

    if explicit_buys or explicit_sells:
        buy_candidates = explicit_buys[:topk]
        sell_candidates = explicit_sells
        if (
            not explicit_sells
            and strategy_type in _TOPK_STYLE_STRATEGIES
            and buy_candidates
        ):
            target_symbols = {
                str(row.get("symbol") or "").strip().upper() for row in buy_candidates
            }
            inferred_sell_symbols = sorted(
                [symbol for symbol in current_symbols if symbol not in target_symbols],
                key=lambda symbol: (score_lookup.get(symbol, -999999.0), symbol),
            )
            if n_drop > 0:
                inferred_sell_symbols = inferred_sell_symbols[:n_drop]
            sell_candidates = [
                {
                    "symbol": symbol,
                    "signal_side": "sell",
                    "reason": "不在当前策略目标持仓",
                }
                for symbol in inferred_sell_symbols
            ]
    else:
        inferred = True
        ranked = sorted_rows[:topk]
        target_symbols = {
            str(row.get("symbol") or "").strip().upper() for row in ranked
        }
        inferred_sell_symbols = sorted(
            [symbol for symbol in current_symbols if symbol not in target_symbols],
            key=lambda symbol: (score_lookup.get(symbol, -999999.0), symbol),
        )
        if n_drop > 0:
            inferred_sell_symbols = inferred_sell_symbols[:n_drop]
        sell_candidates = [
            {
                "symbol": symbol,
                "signal_side": "sell",
                "reason": "TopK 调仓卖出非目标持仓",
            }
            for symbol in inferred_sell_symbols
        ]
        buy_pool = [
            row
            for row in ranked
            if str(row.get("symbol") or "").strip().upper() not in current_symbols
        ]
        if current_symbols and n_drop > 0:
            buy_pool = buy_pool[: len(sell_candidates)]
        buy_candidates = buy_pool if buy_pool else ranked

    return {
        "strategy_type": strategy_type,
        "topk": topk,
        "n_drop": n_drop,
        "rows": sorted_rows,
        "buy_candidates": buy_candidates,
        "sell_candidates": sell_candidates,
        "inferred": inferred,
    }


def _build_execution_plan_from_signals(
    *,
    signal_rows: list[dict[str, Any]],
    strategy_params: dict[str, Any],
    account_snapshot: dict[str, Any],
    prediction_trade_date: date | None = None,
) -> dict[str, Any]:
    constrained_rows, fundamental_filtered_count = _apply_fundamental_constraints_to_signal_rows(
        signal_rows,
        strategy_params=strategy_params,
        trade_date=prediction_trade_date,
    )
    positions = _normalize_positions((account_snapshot or {}).get("positions"))
    cash = _to_float(
        account_snapshot.get("available_cash") or account_snapshot.get("cash"), 0.0
    )
    signal_plan = _filter_signal_rows(constrained_rows, strategy_params, positions)
    skipped_items: list[dict[str, Any]] = []
    sell_orders: list[dict[str, Any]] = []
    buy_orders: list[dict[str, Any]] = []

    for row in signal_plan["sell_candidates"]:
        symbol = str(row.get("symbol") or "").strip().upper()
        position = positions.get(symbol)
        if not position or _to_int(position.get("available_volume"), 0) <= 0:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "action": "SELL",
                    "reason": "当前无可卖持仓",
                    "source": "sell_signal",
                }
            )
            continue
        quantity = max(0, _to_int(position.get("available_volume"), 0))
        expected_price = _to_float(row.get("expected_price"), 0.0)
        reference_price = expected_price or _to_float(position.get("last_price"), 0.0)
        if reference_price <= 0:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "action": "SELL",
                    "reason": "缺少卖出参考价格",
                    "source": "sell_signal",
                }
            )
            continue
        # 始终使用限价单：优先用信号预期价，无预期价则用持仓最新价。
        # 避免市价单因无法获取实时行情被风控拒绝。
        limit_price = expected_price if expected_price > 0 else reference_price
        sell_orders.append(
            {
                "symbol": symbol,
                "name": position.get("name") or "",
                "side": "SELL",
                "trade_action": "SELL_TO_CLOSE",
                "quantity": quantity,
                "order_type": "MARKET",
                "price": limit_price,
                "reference_price": reference_price,
                "estimated_notional": round(quantity * reference_price, 2),
                "current_volume": _to_int(position.get("volume"), 0),
                "current_market_value": round(
                    _to_float(position.get("market_value"), 0.0), 2
                ),
                "reason": str(row.get("reason") or "卖出信号触发调仓"),
                "fusion_score": _to_float(row.get("fusion_score"), 0.0),
            }
        )

    estimated_sell_proceeds = sum(
        _to_float(item.get("estimated_notional"), 0.0) for item in sell_orders
    )
    buy_budget = cash + estimated_sell_proceeds
    sequential_budget = buy_budget

    raw_buy_candidates = signal_plan["buy_candidates"]
    valid_candidates: list[dict[str, Any]] = []
    for row in raw_buy_candidates:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if symbol in positions:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": "当前已持仓，首版预案不做加仓",
                    "source": "buy_signal",
                }
            )
            continue
        reference_price = _to_float(row.get("expected_price"), 0.0)
        if reference_price <= 0:
            reference_price = _get_realtime_price(symbol) or 0.0
        valid_candidates.append(
            dict(row, symbol=symbol, reference_price=reference_price)
        )

    per_order_budget = (
        (sequential_budget / len(valid_candidates))
        if valid_candidates
        else 0.0
    )

    for row in valid_candidates:
        ref_price = row.get("reference_price", 0.0)
        if ref_price <= 0:
            quantity = 0
            estimated_notional = 0.0
            reason = "缺少实时价格，无法估算买入数量"
        else:
            lot_size = _resolve_board_lot_size(str(row["symbol"]))
            quantity = _floor_board_lot(per_order_budget / ref_price, lot_size)
            if quantity <= 0:
                skipped_items.append(
                    {
                        "symbol": row["symbol"],
                        "action": "BUY",
                        "reason": (
                            f"预分配预算 {per_order_budget:.2f} 不足以买入最小手数 {lot_size} 股"
                        ),
                        "source": "buy_signal",
                    }
                )
                continue
            estimated_notional = round(quantity * ref_price, 2)
            sequential_budget = max(0.0, sequential_budget - estimated_notional)
            reason = "按预分配预算等额生成买单"

        buy_orders.append(
            {
                "symbol": row["symbol"],
                "name": "",
                "side": "BUY",
                "trade_action": "BUY_TO_OPEN",
                "quantity": quantity,
                "order_type": "MARKET",
                "price": ref_price,
                "reference_price": ref_price,
                "planned_budget": round(per_order_budget, 2),
                "estimated_notional": estimated_notional,
                "current_volume": 0,
                "current_market_value": 0.0,
                "reason": reason,
                "fusion_score": _to_float(row.get("fusion_score"), 0.0),
            }
        )

    return {
        "sell_orders": sell_orders,
        "buy_orders": buy_orders,
        "skipped_items": skipped_items,
        "summary": {
            "signal_count": len(constrained_rows),
            "raw_signal_count": len(signal_rows),
            "fundamental_filtered_count": fundamental_filtered_count,
            "buy_candidate_count": len(raw_buy_candidates),
            "sell_candidate_count": len(signal_plan["sell_candidates"]),
            "sell_order_count": len(sell_orders),
            "buy_order_count": len(buy_orders),
            "skipped_count": len(skipped_items),
            "estimated_sell_proceeds": round(estimated_sell_proceeds, 2),
            "estimated_buy_amount": round(
                sum(
                    _to_float(item.get("estimated_notional"), 0.0)
                    for item in buy_orders
                ),
                2,
            ),
            "estimated_remaining_cash": round(sequential_budget, 2),
            "available_cash": round(cash, 2),
            "inferred_signal_plan": bool(signal_plan["inferred"]),
            "strategy_type": signal_plan["strategy_type"],
            "topk": signal_plan["topk"],
            "n_drop": signal_plan["n_drop"],
        },
    }


def _normalize_hosted_signal_rows(raw_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_signals or []:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_to_broker_symbol(item.get("symbol"))
        side = str(
            item.get("action")
            or item.get("side")
            or item.get("signal_side")
            or ""
        ).strip().upper()
        if not symbol or side not in {"BUY", "SELL"}:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "signal_side": side.lower(),
                "expected_price": _to_float(
                    item.get("expected_price") or item.get("price"), 0.0
                ),
                "fusion_score": _to_float(
                    item.get("fusion_score") or item.get("score"), 0.0
                ),
                "reason": str(item.get("reason") or item.get("remark") or "").strip(),
                "trade_action": str(item.get("trade_action") or "").strip().upper(),
                "position_side": str(item.get("position_side") or "").strip().upper(),
                "is_margin_trade": bool(item.get("is_margin_trade")),
                "source_signal": dict(item),
            }
        )
    return normalized


def _stage_label(stage: str) -> str:
    mapping = {
        "queued": "排队中",
        "validating": "校验中",
        "signal_loading": "加载信号",
        "dispatching": "派发订单",
        "running": "执行中",
        "completed": "已完成",
        "failed": "已失败",
    }
    return mapping.get(str(stage or "").strip().lower(), str(stage or ""))


def _error_stage_label(stage: str) -> str:
    mapping = {
        "validating": "任务校验",
        "signal_loading": "信号加载",
        "dispatching": "信号派发",
        "risk_check": "风控校验",
        "order_submit": "订单提交",
        "portfolio_lookup": "账户/组合查询",
        "strategy_loading": "策略加载",
        "unexpected": "未知异常",
    }
    return mapping.get(str(stage or "").strip().lower(), str(stage or ""))


def _shift_trading_sessions(start_date: date, sessions: int) -> date:
    if xcals is None:
        offset = pd.tseries.offsets.BDay(max(0, sessions))
        return (pd.Timestamp(start_date) + offset).date()
    cal = xcals.get_calendar("XSHG")
    session = cal.date_to_session(pd.Timestamp(start_date), direction="previous")
    for _ in range(max(0, sessions)):
        session = cal.next_session(session)
    return session.date() if hasattr(session, "date") else session


class ManualExecutionService:
    """手动执行任务服务。"""

    def __init__(self) -> None:
        self._strategy_storage = get_strategy_storage_service()

    @staticmethod
    def _build_task_label(task_type: str) -> str:
        return "自动托管任务" if str(task_type or "").strip().lower() == "hosted" else "手动执行任务"

    @staticmethod
    def _build_strategy_snapshot(
        *,
        strategy: dict[str, Any] | None,
        execution_config: dict[str, Any] | None = None,
        live_trade_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        if isinstance(strategy, dict):
            snapshot["strategy"] = {
                "id": strategy.get("id"),
                "name": strategy.get("name"),
                "is_verified": bool(strategy.get("is_verified")),
                "parameters": strategy.get("parameters") or {},
            }
        if isinstance(execution_config, dict):
            snapshot["execution_config"] = execution_config
        if isinstance(live_trade_config, dict):
            snapshot["live_trade_config"] = live_trade_config
        return snapshot

    async def _load_latest_account_snapshot(
        self, *, tenant_id: str, user_id: str, trading_mode: str = "REAL"
    ) -> dict[str, Any] | None:
        mode = _normalize_trading_mode(trading_mode)
        if mode == "SIMULATION":
            redis_wrapper = get_redis()
            redis_client = getattr(redis_wrapper, "client", None)
            if redis_client is None:
                return None
            normalized_user_id = normalize_trade_user_id(user_id) or str(user_id)
            key = f"simulation:account:{tenant_id}:{normalized_user_id}"
            raw = redis_client.get(key)
            if not raw and normalized_user_id.isdigit():
                legacy_key = f"simulation:account:{tenant_id}:{int(normalized_user_id)}"
                raw = redis_client.get(legacy_key)
            if not raw:
                return None
            try:
                account = json.loads(raw)
            except Exception:
                return None
            if not isinstance(account, dict):
                return None
            # 与实盘快照结构做最小兼容，供下游复用 available_cash/cash/snapshot_at。
            return {
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
                "available_cash": _to_float(
                    account.get("cash") or account.get("available_balance"), 0.0
                ),
                "cash": _to_float(
                    account.get("cash") or account.get("available_balance"), 0.0
                ),
                "total_asset": _to_float(account.get("total_asset"), 0.0),
                "market_value": _to_float(account.get("market_value"), 0.0),
                "positions": account.get("positions") or {},
                "source": "simulation_redis_account",
            }

        async with get_session(read_only=True) as session:
            from backend.services.trade.routers.real_trading_utils import (
                _fetch_latest_real_account_snapshot,
            )

            return await _fetch_latest_real_account_snapshot(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
            )

    async def _wait_for_next_account_snapshot(
        self,
        *,
        tenant_id: str,
        user_id: str,
        trading_mode: str,
        baseline_snapshot_at: datetime | None,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> tuple[dict[str, Any] | None, int]:
        started_at = datetime.now(timezone.utc)
        baseline = baseline_snapshot_at
        while True:
            snapshot = await self._load_latest_account_snapshot(
                tenant_id=tenant_id,
                user_id=user_id,
                trading_mode=trading_mode,
            )
            snapshot_at = _parse_snapshot_at(
                snapshot.get("snapshot_at") if isinstance(snapshot, dict) else None
            )
            if snapshot is not None and snapshot_at is not None:
                if baseline is None or snapshot_at > baseline:
                    waited = max(
                        0,
                        int((datetime.now(timezone.utc) - started_at).total_seconds()),
                    )
                    return snapshot, waited

            waited_seconds = int(
                (datetime.now(timezone.utc) - started_at).total_seconds()
            )
            if waited_seconds >= timeout_seconds:
                return None, waited_seconds
            await asyncio.sleep(poll_interval_seconds)

    async def _load_user_default_model_record(
        self, *, tenant_id: str, user_id: str
    ) -> dict[str, Any] | None:
        async with get_session(read_only=True) as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT model_id, metadata_json, status, activated_at, updated_at
                        FROM qm_user_models
                        WHERE tenant_id = :tenant_id
                          AND user_id = :user_id
                          AND is_default = TRUE
                          AND status IN ('ready', 'active')
                        ORDER BY activated_at DESC NULLS LAST, updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_id, "user_id": user_id},
                )
            ).mappings().first()
        return dict(row) if row else None

    async def _load_latest_default_model_inference_run(
        self, *, tenant_id: str, user_id: str, model_id: str
    ) -> dict[str, Any] | None:
        async with get_session(read_only=True) as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT *
                        FROM qm_model_inference_runs
                        WHERE tenant_id = :tenant_id
                          AND user_id = :user_id
                          AND model_id = :model_id
                          AND status = 'completed'
                        ORDER BY prediction_trade_date DESC, created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_id, "user_id": user_id, "model_id": model_id},
                )
            ).mappings().first()
        return dict(row) if row else None

    async def _load_latest_strategy_inference_run(
        self, *, tenant_id: str, user_id: str, strategy_id: str
    ) -> dict[str, Any] | None:
        async with get_session(read_only=True) as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT *
                        FROM qm_model_inference_runs
                        WHERE tenant_id = :tenant_id
                          AND user_id = :user_id
                          AND status = 'completed'
                          AND COALESCE(request_json ->> 'strategy_id', '') = :strategy_id
                        ORDER BY prediction_trade_date DESC, created_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "strategy_id": strategy_id,
                    },
                )
            ).mappings().first()
        return dict(row) if row else None

    def _resolve_hosted_execution_window(
        self,
        *,
        data_trade_date: date,
        target_horizon_days: int,
    ) -> tuple[date, date]:
        start_date = _shift_trading_sessions(data_trade_date, 1)
        deadline = _shift_trading_sessions(data_trade_date, max(1, target_horizon_days))
        return start_date, deadline

    async def _persist_task(
        self,
        *,
        prepared: PreparedManualExecution,
        task_id: str,
        request_payload: dict[str, Any],
        created_at: datetime,
        task_type: str,
        task_source: str,
        trigger_mode: str,
        trigger_context: dict[str, Any] | None = None,
        strategy_snapshot: dict[str, Any] | None = None,
        parent_runtime_id: str | None = None,
        initial_summary: dict[str, Any] | None = None,
        initial_line: str | None = None,
        status: str = "queued",
        stage: str = "queued",
        result_payload: dict[str, Any] | None = None,
        progress: int = 0,
    ) -> dict[str, Any]:
        await manual_execution_persistence.create_task(
            task_id=task_id,
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            strategy_id=prepared.strategy_id,
            strategy_name=prepared.strategy_name,
            run_id=prepared.run_id,
            model_id=prepared.model_id,
            prediction_trade_date=prepared.prediction_trade_date,
            trading_mode=prepared.trading_mode,
            request_payload=request_payload,
            created_at=created_at,
            task_type=task_type,
            task_source=task_source,
            trigger_mode=trigger_mode,
            trigger_context=trigger_context,
            strategy_snapshot=strategy_snapshot,
            parent_runtime_id=parent_runtime_id,
        )
        if status != "queued" or stage != "queued" or result_payload is not None:
            await manual_execution_persistence.update_task(
                task_id=task_id,
                status=status,
                stage=stage,
                progress=progress,
                signal_count=_to_int((initial_summary or {}).get("signal_count"), 0),
                order_count=_to_int(
                    (initial_summary or {}).get("sell_order_count"), 0
                )
                + _to_int((initial_summary or {}).get("buy_order_count"), 0),
                success_count=_to_int(result_payload.get("success_count") if isinstance(result_payload, dict) else 0, 0),
                failed_count=_to_int(result_payload.get("failed_count") if isinstance(result_payload, dict) else 0, 0),
                result_payload=result_payload,
            )
        manual_execution_log_stream.update_state(
            task_id=task_id,
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            stage=stage,
            status=status,
            progress=progress,
            signal_count=_to_int((initial_summary or {}).get("signal_count"), 0),
            order_count=_to_int((initial_summary or {}).get("sell_order_count"), 0)
            + _to_int((initial_summary or {}).get("buy_order_count"), 0),
            success_count=_to_int(
                result_payload.get("success_count") if isinstance(result_payload, dict) else 0,
                0,
            ),
            failed_count=_to_int(
                result_payload.get("failed_count") if isinstance(result_payload, dict) else 0,
                0,
            ),
            summary=initial_summary or {},
            last_line=initial_line,
            error_stage=result_payload.get("error_stage") if isinstance(result_payload, dict) else None,
            error_message=result_payload.get("error") if isinstance(result_payload, dict) else None,
        )
        if initial_line:
            manual_execution_log_stream.append_log(
                task_id=task_id,
                tenant_id=prepared.tenant_id,
                user_id=prepared.user_id,
                level="info" if status != "failed" else "warning",
                stage=stage,
                status=status,
                progress=progress,
                line=initial_line,
                summary=initial_summary or {},
            )
        task = await manual_execution_persistence.get_task(
            task_id,
            user_id=prepared.user_id,
            tenant_id=prepared.tenant_id,
        )
        return task or {}

    async def _load_inference_run(
        self, *, tenant_id: str, user_id: str, run_id: str
    ) -> dict[str, Any] | None:
        async with get_session(read_only=True) as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT *
                        FROM qm_model_inference_runs
                        WHERE run_id = :run_id
                          AND tenant_id = :tenant_id
                          AND user_id = :user_id
                        LIMIT 1
                        """
                        ),
                        {"run_id": run_id, "tenant_id": tenant_id, "user_id": user_id},
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    async def get_default_model_hosted_status(
        self, *, tenant_id: str, user_id: str
    ) -> dict[str, Any]:
        tenant = (tenant_id or "").strip() or "default"
        uid = str(user_id or "").strip()
        default_model = await self._load_user_default_model_record(
            tenant_id=tenant, user_id=uid
        )
        if not default_model:
            return {
                "available": False,
                "source": "missing",
                "reason_code": "missing_default_model",
                "message": "未找到当前用户的默认模型，请先设置可用的用户默认模型",
            }

        default_model_id = str(default_model.get("model_id") or "").strip()
        model_meta_raw = default_model.get("metadata_json")
        if isinstance(model_meta_raw, str):
            try:
                model_meta = json.loads(model_meta_raw)
            except Exception:
                model_meta = {}
        elif isinstance(model_meta_raw, dict):
            model_meta = model_meta_raw
        else:
            model_meta = {}
        target_horizon_days = _to_int(
            model_meta.get("target_horizon_days") if isinstance(model_meta, dict) else None,
            5,
        )
        if target_horizon_days <= 0:
            target_horizon_days = 5

        latest_run = await self._load_latest_default_model_inference_run(
            tenant_id=tenant, user_id=uid, model_id=default_model_id
        )
        if not latest_run:
            return {
                "available": False,
                "source": "missing",
                "reason_code": "missing_latest_run",
                "message": "未找到当前用户默认模型的最新完成推理数据",
                "latest_default_model_id": default_model_id,
                "target_horizon_days": target_horizon_days,
            }

        if bool(latest_run.get("fallback_used")):
            return {
                "available": False,
                "source": "fallback",
                "reason_code": "fallback_used",
                "message": "当前默认模型最新推理数据来自兜底结果，自动托管已禁止使用兜底数据",
                "latest_default_model_id": default_model_id,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "target_horizon_days": target_horizon_days,
                "data_trade_date": str(latest_run.get("data_trade_date") or ""),
                "prediction_trade_date": str(latest_run.get("prediction_trade_date") or ""),
            }
        latest_model_source = str(latest_run.get("model_source") or "").strip()
        allowed_sources = {"user_default", "explicit_system_model"}
        if latest_model_source not in allowed_sources:
            return {
                "available": False,
                "source": "mismatch",
                "reason_code": "source_mismatch",
                "message": "当前默认模型最新推理数据不是用户默认模型来源，自动托管已拒绝",
                "latest_default_model_id": default_model_id,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "target_horizon_days": target_horizon_days,
                "data_trade_date": str(latest_run.get("data_trade_date") or ""),
                "prediction_trade_date": str(latest_run.get("prediction_trade_date") or ""),
            }

        data_trade_date = _parse_iso_date(latest_run.get("data_trade_date"))
        prediction_trade_date = _parse_iso_date(latest_run.get("prediction_trade_date"))
        generation_start, execution_deadline = self._resolve_hosted_execution_window(
            data_trade_date=data_trade_date,
            target_horizon_days=target_horizon_days,
        )
        current_trade_date = datetime.now(_SH_TZ).date()
        if current_trade_date < generation_start:
            return {
                "available": False,
                "source": "window_pending",
                "reason_code": "window_pending",
                "message": (
                    "当前默认模型最新推理结果尚未进入可执行窗口，"
                    f"开始日期={generation_start.isoformat()}"
                ),
                "latest_default_model_id": default_model_id,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "target_horizon_days": target_horizon_days,
                "data_trade_date": data_trade_date.isoformat(),
                "prediction_trade_date": prediction_trade_date.isoformat(),
                "execution_window_start": generation_start.isoformat(),
                "execution_window_end": execution_deadline.isoformat(),
            }
        if current_trade_date > execution_deadline:
            return {
                "available": False,
                "source": "expired",
                "reason_code": "window_expired",
                "message": (
                    "当前默认模型最新推理结果已超过可执行窗口，"
                    f"截止日期={execution_deadline.isoformat()}"
                ),
                "latest_default_model_id": default_model_id,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "target_horizon_days": target_horizon_days,
                "data_trade_date": data_trade_date.isoformat(),
                "prediction_trade_date": prediction_trade_date.isoformat(),
                "execution_window_start": generation_start.isoformat(),
                "execution_window_end": execution_deadline.isoformat(),
            }

        return {
            "available": True,
            "source": latest_model_source or "user_default",
            "reason_code": "ready",
            "message": "当前默认模型最新推理结果可用于自动托管",
            "latest_default_model_id": default_model_id,
            "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
            "target_horizon_days": target_horizon_days,
            "data_trade_date": data_trade_date.isoformat(),
            "prediction_trade_date": prediction_trade_date.isoformat(),
            "execution_window_start": generation_start.isoformat(),
            "execution_window_end": execution_deadline.isoformat(),
            "fallback_used": bool(latest_run.get("fallback_used")),
            "model_source": latest_model_source or None,
        }

    async def get_strategy_hosted_status(
        self, *, tenant_id: str, user_id: str, strategy_id: str
    ) -> dict[str, Any]:
        tenant = (tenant_id or "").strip() or "default"
        uid = str(user_id or "").strip()
        sid = str(strategy_id or "").strip()
        if not sid:
            return {
                "available": False,
                "source": "missing",
                "reason_code": "missing_strategy_id",
                "message": "未提供策略 ID，无法定位当前策略的最新推理信号",
            }

        latest_run = await self._load_latest_strategy_inference_run(
            tenant_id=tenant,
            user_id=uid,
            strategy_id=sid,
        )
        if not latest_run:
            return {
                "available": False,
                "source": "missing",
                "reason_code": "missing_strategy_latest_run",
                "message": "未找到当前策略对应的最新完成推理信号，已拒绝自动托管执行",
                "strategy_id": sid,
            }

        if bool(latest_run.get("fallback_used")):
            return {
                "available": False,
                "source": "fallback",
                "reason_code": "fallback_used",
                "message": "当前策略最新推理数据来自兜底结果，已拒绝自动托管执行",
                "strategy_id": sid,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "data_trade_date": str(latest_run.get("data_trade_date") or ""),
                "prediction_trade_date": str(latest_run.get("prediction_trade_date") or ""),
            }

        target_horizon_days = _resolve_run_target_horizon_days(latest_run)
        data_trade_date = _parse_iso_date(latest_run.get("data_trade_date"))
        prediction_trade_date = _parse_iso_date(latest_run.get("prediction_trade_date"))
        generation_start, execution_deadline = self._resolve_hosted_execution_window(
            data_trade_date=data_trade_date,
            target_horizon_days=target_horizon_days,
        )
        current_trade_date = datetime.now(_SH_TZ).date()
        if current_trade_date < generation_start:
            return {
                "available": False,
                "source": "window_pending",
                "reason_code": "window_pending",
                "message": (
                    "当前策略最新推理结果尚未进入可执行窗口，"
                    f"开始日期={generation_start.isoformat()}"
                ),
                "strategy_id": sid,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "target_horizon_days": target_horizon_days,
                "data_trade_date": data_trade_date.isoformat(),
                "prediction_trade_date": prediction_trade_date.isoformat(),
                "execution_window_start": generation_start.isoformat(),
                "execution_window_end": execution_deadline.isoformat(),
            }
        if current_trade_date > execution_deadline:
            return {
                "available": False,
                "source": "expired",
                "reason_code": "window_expired",
                "message": (
                    "当前策略最新推理结果已超过可执行窗口，"
                    f"截止日期={execution_deadline.isoformat()}"
                ),
                "strategy_id": sid,
                "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
                "target_horizon_days": target_horizon_days,
                "data_trade_date": data_trade_date.isoformat(),
                "prediction_trade_date": prediction_trade_date.isoformat(),
                "execution_window_start": generation_start.isoformat(),
                "execution_window_end": execution_deadline.isoformat(),
            }

        effective_model_id = (
            str(latest_run.get("effective_model_id") or "").strip()
            or str(latest_run.get("active_model_id") or "").strip()
            or str(latest_run.get("model_id") or "").strip()
        )
        return {
            "available": True,
            "source": "strategy_latest_run",
            "reason_code": "ready",
            "message": "当前策略最新推理结果可用于自动托管",
            "strategy_id": sid,
            "latest_run_id": str(latest_run.get("run_id") or "").strip() or None,
            "latest_model_id": effective_model_id,
            "target_horizon_days": target_horizon_days,
            "data_trade_date": data_trade_date.isoformat(),
            "prediction_trade_date": prediction_trade_date.isoformat(),
            "execution_window_start": generation_start.isoformat(),
            "execution_window_end": execution_deadline.isoformat(),
            "fallback_used": bool(latest_run.get("fallback_used")),
            "model_source": str(latest_run.get("model_source") or "").strip() or None,
        }

    async def _load_signal_rows(
        self, *, tenant_id: str, user_id: str, run_id: str
    ) -> list[dict[str, Any]]:
        async with get_session(read_only=True) as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT symbol, fusion_score, light_score, tft_score, score_rank,
                               signal_side, expected_price, quality, created_at
                        FROM engine_signal_scores
                        WHERE run_id = :run_id
                          AND tenant_id = :tenant_id
                          AND user_id = :user_id
                        ORDER BY fusion_score DESC NULLS LAST, symbol ASC
                        """
                        ),
                        {"run_id": run_id, "tenant_id": tenant_id, "user_id": user_id},
                    )
                )
                .mappings()
                .all()
            )
        normalized: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row or {})
            if item.get("symbol"):
                item["symbol"] = _normalize_to_broker_symbol(item["symbol"])
            if item.get("created_at") is not None:
                item["created_at"] = item["created_at"].isoformat()
            normalized.append(item)
        return normalized

    async def _ensure_active_portfolio_exists(
        self, *, tenant_id: str, user_id: str, strategy_id: str
    ) -> dict[str, Any]:
        from backend.services.trade.routers.real_trading_utils import (
            _fetch_active_portfolio_snapshot,
        )

        async with get_session(read_only=True) as session:
            snapshot = await _fetch_active_portfolio_snapshot(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                mode="REAL",
            )
        if not snapshot:
            raise HTTPException(
                status_code=400,
                detail="当前未发现可用的实盘组合，请先启动实盘策略或完成组合初始化",
            )
        return snapshot

    async def _ensure_real_portfolio_for_task(
        self,
        db,
        *,
        tenant_id: str,
        user_id: str,
        strategy_id: str,
        strategy_name: str,
    ) -> Portfolio | None:
        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            return None

        conditions = [
            Portfolio.tenant_id == tenant_id,
            Portfolio.user_id == user_id_int,
            Portfolio.status == "active",
            Portfolio.is_deleted == False,
            Portfolio.trading_mode == "REAL",
        ]
        strategy_id_text = str(strategy_id or "").strip()
        if strategy_id_text.isdigit():
            conditions.append(Portfolio.strategy_id == int(strategy_id_text))

        stmt = (
            select(Portfolio)
            .where(and_(*conditions))
            .order_by(
                (Portfolio.run_status == "running").desc(),
                Portfolio.updated_at.desc(),
            )
            .limit(1)
        )
        portfolio = (await db.execute(stmt)).scalar_one_or_none()
        if portfolio:
            return portfolio

        latest_snapshot = await self._load_latest_account_snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            trading_mode="REAL",
        )
        if not latest_snapshot:
            return None

        total_asset = _to_float(latest_snapshot.get("total_asset"), 0.0)
        available_cash = _to_float(
            latest_snapshot.get("available_cash") or latest_snapshot.get("cash"),
            0.0,
        )
        market_value = _to_float(latest_snapshot.get("market_value"), 0.0)
        if total_asset <= 0:
            total_asset = max(available_cash + market_value, available_cash, 0.0)
        if total_asset <= 0:
            return None

        portfolio = Portfolio(
            tenant_id=tenant_id,
            user_id=user_id_int,
            name=f"{strategy_name or strategy_id_text or '默认策略'} 实盘组合",
            description="首次实盘手动执行自动初始化",
            initial_capital=total_asset,
            current_capital=total_asset,
            available_cash=max(available_cash, 0.0),
            frozen_cash=0,
            total_value=total_asset,
            total_pnl=0,
            total_return=0,
            daily_pnl=0,
            daily_return=0,
            yesterday_total_value=total_asset,
            status="active",
            trading_mode="REAL",
            strategy_id=int(strategy_id_text) if strategy_id_text.isdigit() else None,
            run_status="running",
            broker_type="QMT",
            broker_account_id=str(latest_snapshot.get("account_id") or "") or None,
            broker_params={"source": "manual_execution_auto_init"},
        )
        db.add(portfolio)
        await db.flush()
        await db.refresh(portfolio)
        logger.info(
            "Auto-initialized real portfolio for manual execution: tenant=%s user=%s strategy=%s portfolio=%s total_asset=%.2f",
            tenant_id,
            user_id,
            strategy_id,
            portfolio.id,
            total_asset,
        )
        return portfolio

    async def prepare_manual_execution(
        self,
        *,
        tenant_id: str,
        user_id: str,
        run_id: str,
        strategy_id: str,
        model_id: str | None = None,
        trading_mode: Any,
        note: str | None = None,
    ) -> PreparedManualExecution:
        tenant = (tenant_id or "").strip() or "default"
        uid = str(user_id or "").strip()
        rid = str(run_id or "").strip()
        sid = str(strategy_id or "").strip()
        mode = _normalize_trading_mode(trading_mode)

        if not rid:
            raise HTTPException(status_code=400, detail="run_id 不能为空")
        if not sid:
            raise HTTPException(status_code=400, detail="strategy_id 不能为空")

        run = await self._load_inference_run(tenant_id=tenant, user_id=uid, run_id=rid)
        if not run:
            raise HTTPException(status_code=404, detail="推理批次不存在")
        if str(run.get("status") or "").lower() != "completed":
            raise HTTPException(status_code=400, detail="仅允许执行已完成的推理批次")
        if model_id and str(run.get("model_id") or "").strip() != str(model_id).strip():
            raise HTTPException(status_code=400, detail="run_id 与当前选择模型不匹配")

        strategy = await self._strategy_storage.get(sid, uid)
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")
        if not bool(strategy.get("is_verified")):
            raise HTTPException(status_code=400, detail="仅允许执行已验证策略")

        strategy_name = (
            str(strategy.get("name") or f"strategy_{sid}").strip() or f"strategy_{sid}"
        )
        request_payload = {
            "tenant_id": tenant,
            "user_id": uid,
            "run_id": rid,
            "strategy_id": sid,
            "strategy_name": strategy_name,
            "trading_mode": mode,
            "note": note,
        }

        return PreparedManualExecution(
            task_id="",
            tenant_id=tenant,
            user_id=uid,
            strategy_id=sid,
            strategy_name=strategy_name,
            run_id=rid,
            model_id=str(run.get("model_id") or ""),
            prediction_trade_date=_parse_iso_date(run.get("prediction_trade_date")),
            trading_mode=mode,
            request_payload=request_payload,
            run=run,
            strategy=strategy,
        )

    async def build_execution_preview(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model_id: str,
        run_id: str,
        strategy_id: str,
        trading_mode: Any,
        note: str | None = None,
    ) -> dict[str, Any]:
        mode = _normalize_trading_mode(trading_mode)
        if mode != "REAL":
            raise HTTPException(
                status_code=400, detail="引导式手动任务首版仅支持 REAL 模式"
            )

        prepared = await self.prepare_manual_execution(
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            strategy_id=strategy_id,
            model_id=model_id,
            trading_mode=mode,
            note=note,
        )
        async with get_session(read_only=True) as session:
            from backend.services.trade.routers.real_trading_utils import (
                _fetch_latest_real_account_snapshot,
            )

            account_snapshot = await _fetch_latest_real_account_snapshot(
                session,
                tenant_id=prepared.tenant_id,
                user_id=prepared.user_id,
            )
        if not account_snapshot:
            raise HTTPException(
                status_code=400,
                detail="未检测到最新实盘账户快照，请先确认 QMT Agent 已上报账户数据",
            )

        signal_rows = await self._load_signal_rows(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            run_id=prepared.run_id,
        )
        if not signal_rows:
            raise HTTPException(status_code=400, detail="当前推理批次无可用信号明细")

        strategy_params = _normalize_strategy_params(prepared.strategy)
        plan = _build_execution_plan_from_signals(
            signal_rows=signal_rows,
            strategy_params=strategy_params,
            account_snapshot=account_snapshot,
            prediction_trade_date=prepared.prediction_trade_date,
        )
        if not plan["sell_orders"] and not plan["buy_orders"]:
            raise HTTPException(status_code=400, detail="策略计算后无可执行调仓动作")

        preview = {
            "account_snapshot": {
                "account_id": str(account_snapshot.get("account_id") or ""),
                "snapshot_at": account_snapshot.get("snapshot_at"),
                "total_asset": round(
                    _to_float(account_snapshot.get("total_asset"), 0.0), 2
                ),
                "available_cash": round(
                    _to_float(
                        account_snapshot.get("available_cash")
                        or account_snapshot.get("cash"),
                        0.0,
                    ),
                    2,
                ),
                "market_value": round(
                    _to_float(account_snapshot.get("market_value"), 0.0), 2
                ),
                "position_count": _to_int(
                    account_snapshot.get("position_count"),
                    len(_normalize_positions(account_snapshot.get("positions")).keys()),
                ),
            },
            "strategy_context": {
                "model_id": prepared.model_id,
                "run_id": prepared.run_id,
                "prediction_trade_date": prepared.prediction_trade_date.isoformat(),
                "strategy_id": prepared.strategy_id,
                "strategy_name": prepared.strategy_name,
                "trading_mode": prepared.trading_mode,
                "strategy_params": strategy_params,
                "note": note,
            },
            "sell_orders": plan["sell_orders"],
            "buy_orders": plan["buy_orders"],
            "skipped_items": plan["skipped_items"],
            "summary": plan["summary"],
        }
        preview["preview_hash"] = _build_preview_hash(preview)
        return preview

    async def _guard_active_manual_task(
        self,
        *,
        prepared: PreparedManualExecution,
        preview_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        active_task = await manual_execution_persistence.get_active_manual_task(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            trading_mode=prepared.trading_mode,
        )
        if not active_task:
            return None
        active_task_id = str(active_task.get("task_id") or "").strip()
        same_execution = (
            str(active_task.get("run_id") or "").strip() == prepared.run_id
            and str(active_task.get("strategy_id") or "").strip() == prepared.strategy_id
        )
        if same_execution:
            return {
                "task_id": active_task_id,
                "status": str(active_task.get("status") or "queued"),
                "task": active_task,
                "preview_summary": preview_summary or {},
                "duplicate": True,
                "noop": True,
            }
        raise HTTPException(
            status_code=409,
            detail=(
                "当前账户已有手动执行任务正在处理，"
                f"请等待完成后再提交；task_id={active_task_id} "
                f"status={active_task.get('status')} stage={active_task.get('stage')}"
            ),
        )

    async def create_manual_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model_id: str,
        run_id: str,
        strategy_id: str,
        trading_mode: Any,
        preview_hash: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        if preview_hash:
            return await self.submit_execution_plan(
                tenant_id=tenant_id,
                user_id=user_id,
                model_id=model_id,
                run_id=run_id,
                strategy_id=strategy_id,
                trading_mode=trading_mode,
                preview_hash=preview_hash,
                note=note,
            )

        prepared = await self.prepare_manual_execution(
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            strategy_id=strategy_id,
            model_id=model_id,
            trading_mode=trading_mode,
            note=note,
        )
        active_result = await self._guard_active_manual_task(prepared=prepared)
        if active_result:
            return active_result
        task_id = f"manual_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc)
        task = await self._persist_task(
            prepared=prepared,
            task_id=task_id,
            request_payload=prepared.request_payload,
            created_at=created_at,
            task_type="manual",
            task_source="manual_page",
            trigger_mode="manual",
            strategy_snapshot=self._build_strategy_snapshot(strategy=prepared.strategy),
            initial_summary={
                "run_id": prepared.run_id,
                "model_id": prepared.model_id,
                "strategy_id": prepared.strategy_id,
                "strategy_name": prepared.strategy_name,
                "prediction_trade_date": prepared.prediction_trade_date.isoformat(),
                "trading_mode": prepared.trading_mode,
                "signal_count": int(prepared.run.get("signals_count") or 0),
            },
            initial_line=(
                f"手动执行任务已创建: run_id={prepared.run_id} "
                f"strategy={prepared.strategy_name} mode={prepared.trading_mode}"
            ),
        )
        return {
            "task_id": task_id,
            "status": "queued",
            "task": task,
        }

    async def _cancel_previous_manual_tasks(
        self,
        *,
        user_id: str,
        tenant_id: str,
        run_id: str,
        strategy_id: str,
    ) -> None:
        """新任务提交前，取消同 run_id+strategy_id 的历史任务并删除其 pending 订单。
        只删除尚未提交到券商的订单（status=pending），已提交/成交的订单保留审计记录。
        """
        try:
            async with get_session() as db:
                # 1. 查询同 run_id + strategy_id 的历史任务（所有状态）
                rows = await db.execute(
                    text("""
                        SELECT task_id, status
                        FROM trade_manual_execution_tasks
                        WHERE user_id = :user_id
                          AND tenant_id = :tenant_id
                          AND run_id = :run_id
                          AND strategy_id = :strategy_id
                    """),
                    {
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                        "strategy_id": strategy_id,
                    },
                )
                prev_tasks = rows.fetchall()
                if not prev_tasks:
                    return

                prev_task_ids = [str(r[0]) for r in prev_tasks]
                non_terminal = [
                    str(r[0])
                    for r in prev_tasks
                    if str(r[1] or "") not in {"completed", "failed", "cancelled"}
                ]

                # 2. 取消非终态历史任务
                if non_terminal:
                    await db.execute(
                        text("""
                            UPDATE trade_manual_execution_tasks
                            SET status = 'cancelled', stage = 'cancelled',
                                error_stage = 'cancelled',
                                error_message = '已被新提交任务自动取消'
                            WHERE task_id = ANY(:ids)
                        """),
                        {"ids": non_terminal},
                    )

                # 3. 删除历史任务的 pending 订单（client_order_id 以 manual- 开头，确保只删手动任务单）
                # 保留已提交/成交订单的审计记录
                prefix_conditions = " OR ".join(
                    [
                        f"client_order_id LIKE :prefix_{i}"
                        for i in range(len(prev_task_ids))
                    ]
                )
                prefix_params = {
                    f"prefix_{i}": f"manual-{tid[-8:]}%"
                    for i, tid in enumerate(prev_task_ids)
                }
                await db.execute(
                    text(f"""
                        DELETE FROM orders
                        WHERE user_id = :user_id
                          AND tenant_id = :tenant_id
                          AND status = 'pending'
                          AND ({prefix_conditions})
                    """),
                    {"user_id": int(user_id), "tenant_id": tenant_id, **prefix_params},
                )

                await db.commit()
                logger.info(
                    "清理历史手动任务: user=%s run_id=%s strategy_id=%s "
                    "cancelled=%d total_prev=%d",
                    user_id,
                    run_id,
                    strategy_id,
                    len(non_terminal),
                    len(prev_task_ids),
                )
        except Exception as exc:
            # 清理失败不阻断新任务创建，只记录警告
            logger.warning("清理历史手动任务失败（不影响新任务）: %s", exc)

    async def submit_execution_plan(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model_id: str,
        run_id: str,
        strategy_id: str,
        trading_mode: Any,
        preview_hash: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        preview = await self.build_execution_preview(
            tenant_id=tenant_id,
            user_id=user_id,
            model_id=model_id,
            run_id=run_id,
            strategy_id=strategy_id,
            trading_mode=trading_mode,
            note=note,
        )
        if (
            str(preview.get("preview_hash") or "").strip()
            != str(preview_hash or "").strip()
        ):
            raise HTTPException(
                status_code=409, detail="预览结果已失效，请重新计算调仓预案后再提交"
            )

        prepared = await self.prepare_manual_execution(
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            strategy_id=strategy_id,
            model_id=model_id,
            trading_mode=trading_mode,
            note=note,
        )
        active_result = await self._guard_active_manual_task(
            prepared=prepared,
            preview_summary=preview.get("summary") or {},
        )
        if active_result:
            return active_result
        task_id = f"manual_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc)
        preview_summary = preview.get("summary") or {}
        request_payload = {
            **prepared.request_payload,
            "preview_hash": preview_hash,
            "execution_plan": {
                "sell_orders": preview.get("sell_orders") or [],
                "buy_orders": preview.get("buy_orders") or [],
                "skipped_items": preview.get("skipped_items") or [],
                "summary": preview_summary,
            },
        }

        # 新任务下达前清理同用户同 run_id+strategy_id 的历史任务及其 pending 订单
        await self._cancel_previous_manual_tasks(
            user_id=prepared.user_id,
            tenant_id=prepared.tenant_id,
            run_id=prepared.run_id,
            strategy_id=prepared.strategy_id,
        )

        task = await self._persist_task(
            prepared=prepared,
            task_id=task_id,
            request_payload=request_payload,
            created_at=created_at,
            task_type="manual",
            task_source="manual_page",
            trigger_mode="manual",
            strategy_snapshot=self._build_strategy_snapshot(strategy=prepared.strategy),
            initial_summary={
                "run_id": prepared.run_id,
                "model_id": prepared.model_id,
                "strategy_id": prepared.strategy_id,
                "strategy_name": prepared.strategy_name,
                "prediction_trade_date": prepared.prediction_trade_date.isoformat(),
                "trading_mode": prepared.trading_mode,
                "preview_summary": preview_summary,
                "signal_count": _to_int(
                    preview_summary.get("signal_count"),
                    int(prepared.run.get("signals_count") or 0),
                ),
                "buy_order_count": _to_int(preview_summary.get("buy_order_count"), 0),
                "sell_order_count": _to_int(preview_summary.get("sell_order_count"), 0),
            },
            initial_line=(
                f"调仓预案已确认并创建执行任务: run_id={prepared.run_id} "
                f"strategy={prepared.strategy_name} "
                f"buy={_to_int(preview_summary.get('buy_order_count'), 0)} "
                f"sell={_to_int(preview_summary.get('sell_order_count'), 0)}"
            ),
        )
        return {
            "task_id": task_id,
            "status": "queued",
            "task": task,
            "preview_summary": preview_summary,
        }

    async def list_tasks(
        self,
        *,
        tenant_id: str,
        user_id: str,
        limit: int = 20,
        task_type: str | None = None,
        task_source: str | None = None,
        active_runtime_id: str | None = None,
    ) -> dict[str, Any]:
        items = await manual_execution_persistence.list_tasks(
            tenant_id=tenant_id,
            user_id=user_id,
            limit=limit,
            task_type=task_type,
            task_source=task_source,
            parent_runtime_id=active_runtime_id,
        )
        return {
            "items": items,
            "total": len(items),
            "limit": limit,
        }

    async def get_latest_hosted_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        active_runtime_id: str | None = None,
    ) -> dict[str, Any] | None:
        items = await manual_execution_persistence.list_tasks(
            tenant_id=tenant_id,
            user_id=user_id,
            limit=1,
            task_type="hosted",
            parent_runtime_id=active_runtime_id,
        )
        if items:
            return items[0]
        if active_runtime_id:
            fallback = await manual_execution_persistence.list_tasks(
                tenant_id=tenant_id,
                user_id=user_id,
                limit=1,
                task_type="hosted",
            )
            return fallback[0] if fallback else None
        return None

    async def create_hosted_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        run_id: str | None = None,
        strategy_id: str,
        trading_mode: Any,
        execution_config: dict[str, Any] | None = None,
        live_trade_config: dict[str, Any] | None = None,
        trigger_context: dict[str, Any] | None = None,
        parent_runtime_id: str | None = None,
        note: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        tenant = (tenant_id or "").strip() or "default"
        uid = str(user_id or "").strip()
        sid = str(strategy_id or "").strip()
        mode = _normalize_trading_mode(trading_mode)
        provided_task_id = str(task_id or "").strip()
        if provided_task_id:
            existing_task = await manual_execution_persistence.get_task_any(provided_task_id)
            if existing_task:
                return {
                    "task_id": provided_task_id,
                    "status": str(existing_task.get("status") or "completed"),
                    "task": existing_task,
                    "noop": True,
                    "duplicate": True,
                }

        hosted_status = await self.get_strategy_hosted_status(
            tenant_id=tenant,
            user_id=uid,
            strategy_id=sid,
        )
        if (
            not bool(hosted_status.get("available"))
            and mode == "SIMULATION"
            and hosted_status.get("reason_code") == "missing_strategy_latest_run"
        ):
            hosted_status = await self.get_default_model_hosted_status(
                tenant_id=tenant,
                user_id=uid,
            )

        if not bool(hosted_status.get("available")):
            raise HTTPException(
                status_code=409,
                detail=str(hosted_status.get("message") or "当前策略最新推理不可用于自动托管"),
            )

        latest_model_id = str(hosted_status.get("latest_model_id") or "").strip()
        target_horizon_days = _to_int(hosted_status.get("target_horizon_days"), 5)
        data_trade_date = _parse_iso_date(hosted_status.get("data_trade_date"))
        prediction_trade_date = _parse_iso_date(hosted_status.get("prediction_trade_date"))
        generation_start = _parse_iso_date(hosted_status.get("execution_window_start"))
        execution_deadline = _parse_iso_date(hosted_status.get("execution_window_end"))
        latest_run_id = str(hosted_status.get("latest_run_id") or "").strip()
        task_id = provided_task_id or f"hosted_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"

        prepared = await self.prepare_manual_execution(
            tenant_id=tenant,
            user_id=uid,
            run_id=latest_run_id,
            strategy_id=sid,
            model_id=latest_model_id or None,
            trading_mode=mode,
            note=note,
        )
        latest_snapshot = await self._load_latest_account_snapshot(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            trading_mode=mode,
        )
        if not latest_snapshot:
            detail = (
                "未检测到最新模拟账户快照，请先确认模拟账户已初始化并有最新资金快照"
                if mode == "SIMULATION"
                else "未检测到最新实盘账户快照，请先确认 QMT Agent 已上报账户数据"
            )
            raise HTTPException(
                status_code=400,
                detail=detail,
            )
        normalized_signals = await self._load_signal_rows(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            run_id=prepared.run_id,
        )
        strategy_params = _normalize_strategy_params(prepared.strategy)
        _require_strict_hosted_signal_context(
            strategy_params=strategy_params,
            signal_rows=normalized_signals,
        )
        execution_plan = _build_execution_plan_from_signals(
            signal_rows=normalized_signals,
            strategy_params=strategy_params,
            account_snapshot=latest_snapshot,
            prediction_trade_date=prepared.prediction_trade_date,
        )
        created_at = datetime.now(timezone.utc)
        plan_summary = execution_plan.get("summary") or {}
        request_payload = {
            **prepared.request_payload,
            "signals": normalized_signals,
            "trigger_context": trigger_context or {},
            "execution_plan": execution_plan,
            "note": note,
            "source_run_id": prepared.run_id,
            "target_horizon_days": target_horizon_days,
            "execution_window": {
                "start": generation_start.isoformat(),
                "end": execution_deadline.isoformat(),
            },
        }
        strategy_snapshot = self._build_strategy_snapshot(
            strategy=prepared.strategy,
            execution_config=execution_config,
            live_trade_config=live_trade_config,
        )
        actionable_orders = list(execution_plan.get("sell_orders") or []) + list(
            execution_plan.get("buy_orders") or []
        )
        common_summary = {
            "task_type": "hosted",
            "task_source": "hosted_runner",
            "trigger_mode": "schedule",
            "run_id": prepared.run_id,
            "model_id": prepared.model_id,
            "strategy_id": prepared.strategy_id,
            "strategy_name": prepared.strategy_name,
            "prediction_trade_date": prepared.prediction_trade_date.isoformat(),
            "trading_mode": prepared.trading_mode,
            "trigger_context": trigger_context or {},
            "preview_summary": plan_summary,
            "signal_count": _to_int(plan_summary.get("signal_count"), len(normalized_signals)),
            "buy_order_count": _to_int(plan_summary.get("buy_order_count"), 0),
            "sell_order_count": _to_int(plan_summary.get("sell_order_count"), 0),
            "skipped_count": _to_int(plan_summary.get("skipped_count"), 0),
            "target_horizon_days": target_horizon_days,
            "execution_window_start": generation_start.isoformat(),
            "execution_window_end": execution_deadline.isoformat(),
            "latest_model_id": latest_model_id,
        }
        if not actionable_orders:
            result_payload = {
                "success": True,
                "task_id": task_id,
                "run_id": prepared.run_id,
                "model_id": prepared.model_id,
                "strategy_id": prepared.strategy_id,
                "strategy_name": prepared.strategy_name,
                "prediction_trade_date": prepared.prediction_trade_date.isoformat(),
                "trading_mode": prepared.trading_mode,
                "signal_count": _to_int(plan_summary.get("signal_count"), len(normalized_signals)),
                "order_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "noop": True,
                "preview_summary": plan_summary,
                "stage_label": _stage_label("completed"),
            }
            task = await self._persist_task(
                prepared=prepared,
                task_id=task_id,
                request_payload=request_payload,
                created_at=created_at,
                task_type="hosted",
                task_source="hosted_runner",
                trigger_mode="schedule",
                trigger_context=trigger_context,
                strategy_snapshot=strategy_snapshot,
                parent_runtime_id=parent_runtime_id,
                initial_summary=common_summary,
                initial_line=(
                    f"自动托管任务已创建但本轮无可执行委托: run_id={prepared.run_id} "
                    f"strategy={prepared.strategy_name}"
                ),
                status="completed",
                stage="completed",
                result_payload=result_payload,
                progress=100,
            )
            return {"task_id": task_id, "status": "completed", "task": task, "noop": True}

        task = await self._persist_task(
            prepared=prepared,
            task_id=task_id,
            request_payload=request_payload,
            created_at=created_at,
            task_type="hosted",
            task_source="hosted_runner",
            trigger_mode="schedule",
            trigger_context=trigger_context,
            strategy_snapshot=strategy_snapshot,
            parent_runtime_id=parent_runtime_id,
            initial_summary=common_summary,
            initial_line=(
                f"自动托管任务已创建: run_id={prepared.run_id} strategy={prepared.strategy_name} "
                f"buy={_to_int(plan_summary.get('buy_order_count'), 0)} "
                f"sell={_to_int(plan_summary.get('sell_order_count'), 0)}"
            ),
        )
        return {"task_id": task_id, "status": "queued", "task": task, "noop": False}

    async def clear_history(self, *, tenant_id: str, user_id: str) -> dict[str, Any]:
        """清除该用户的所有手动执行历史。"""
        count = await manual_execution_persistence.clear_tasks(
            tenant_id=tenant_id, user_id=user_id
        )
        logger.info(
            "[%s:%s] Cleared %d manual execution tasks", tenant_id, user_id, count
        )
        return {"cleared_count": count}

    async def get_task(
        self, *, tenant_id: str, user_id: str, task_id: str
    ) -> dict[str, Any] | None:
        return await manual_execution_persistence.get_task(
            task_id, user_id=user_id, tenant_id=tenant_id
        )

    async def get_logs(
        self,
        *,
        tenant_id: str,
        user_id: str,
        task_id: str,
        after_id: str = "0-0",
        limit: int = 200,
    ) -> dict[str, Any]:
        task = await manual_execution_persistence.get_task(
            task_id, user_id=user_id, tenant_id=tenant_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="手动执行任务不存在")
        data = manual_execution_log_stream.fetch_entries(
            task_id, after_id=after_id, limit=limit
        )
        data["task"] = task
        return data

    async def process_task(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("task_id") or "").strip()
        tenant_id = str(task.get("tenant_id") or "default").strip() or "default"
        user_id = str(task.get("user_id") or "").strip()
        if not task_id or not user_id:
            return

        status = str(task.get("status") or "")
        if status not in {"queued", "validating", "dispatching", "running"}:
            return

        request_json = task.get("request_json") or {}
        task_type = str(task.get("task_type") or "manual").strip().lower()
        task_label = self._build_task_label(task_type)
        run_id = str(task.get("run_id") or request_json.get("run_id") or "").strip()
        strategy_id = str(
            task.get("strategy_id") or request_json.get("strategy_id") or ""
        ).strip()
        trading_mode = _normalize_trading_mode(
            task.get("trading_mode") or request_json.get("trading_mode") or "REAL"
        )

        manual_execution_log_stream.update_state(
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            stage="validating",
            status="validating",
            progress=0,
            signal_count=int(task.get("signal_count") or 0),
            order_count=int(task.get("order_count") or 0),
            success_count=int(task.get("success_count") or 0),
            failed_count=int(task.get("failed_count") or 0),
            summary=request_json,
        )
        manual_execution_log_stream.append_log(
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            level="info",
            stage="validating",
            status="validating",
            line=f"开始验证{task_label}: run_id={run_id}, strategy_id={strategy_id}, mode={trading_mode}",
        )

        try:
            prepared = await self.prepare_manual_execution(
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                strategy_id=strategy_id,
                trading_mode=trading_mode,
                note=request_json.get("note"),
            )
        except HTTPException as exc:
            await manual_execution_persistence.update_task(
                task_id=task_id,
                status="failed",
                stage="validating",
                error_stage="validating",
                error_message=str(exc.detail or exc),
                result_payload={
                    "success": False,
                    "stage": "validating",
                    "stage_label": _stage_label("validating"),
                    "error_stage": "validating",
                    "error_stage_label": _error_stage_label("validating"),
                    "error": str(exc.detail or exc),
                },
            )
            manual_execution_log_stream.append_log(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                level="error",
                stage="validating",
                status="failed",
                line=f"任务验证失败: {exc.detail}",
            )
            manual_execution_log_stream.update_state(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                stage="validating",
                status="failed",
                error_stage="validating",
                error_message=str(exc.detail or exc),
            )
            return

        async with get_session() as db:
            if trading_mode == "SIMULATION":
                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="info",
                    stage="validating",
                    line="[链路诊断] 模拟盘模式：跳过实盘组合检查",
                )
            else:
                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="info",
                    stage="validating",
                    line="[链路诊断] 正在检查活跃实盘组合...",
                )

                portfolio = await self._ensure_real_portfolio_for_task(
                    db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    strategy_name=prepared.strategy_name,
                )
                if not portfolio:
                    error_msg = "当前未发现可用的实盘组合，请先启动实盘策略或完成组合初始化"
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="error",
                        stage="validating",
                        line=error_msg,
                    )
                    await manual_execution_persistence.update_task(
                        task_id=task_id,
                        status="failed",
                        stage="validating",
                        error_stage="portfolio_lookup",
                        error_message=error_msg,
                    )
                    return

                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="info",
                    stage="validating",
                    line=f"[链路诊断] 实盘组合就绪: {portfolio.name} (ID: {portfolio.id})",
                )

            execution_plan = (
                request_json.get("execution_plan")
                if isinstance(request_json.get("execution_plan"), dict)
                else None
            )
            if not execution_plan:
                latest_snapshot = await self._load_latest_account_snapshot(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    trading_mode=trading_mode,
                )
                if not latest_snapshot:
                    error_msg = (
                        "未检测到最新模拟账户快照，请先确认模拟账户已初始化并有最新资金快照"
                        if trading_mode == "SIMULATION"
                        else "未检测到最新实盘账户快照，请先确认 QMT Agent 已上报账户数据"
                    )
                    await manual_execution_persistence.update_task(
                        task_id=task_id,
                        status="failed",
                        stage="validating",
                        error_stage="portfolio_lookup",
                        error_message=error_msg,
                    )
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="error",
                        stage="validating",
                        line=error_msg,
                    )
                    return
                signal_rows = await self._load_signal_rows(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    run_id=run_id,
                )
                if not signal_rows:
                    error_msg = "推理结果无可执行信号"
                    await manual_execution_persistence.update_task(
                        task_id=task_id,
                        status="failed",
                        stage="signal_loading",
                        error_stage="signal_loading",
                        error_message=error_msg,
                    )
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="error",
                        stage="signal_loading",
                        status="failed",
                        line=error_msg,
                    )
                    return
                strategy_params = _normalize_strategy_params(prepared.strategy)
                execution_plan = _build_execution_plan_from_signals(
                    signal_rows=signal_rows,
                    strategy_params=strategy_params,
                    account_snapshot=latest_snapshot,
                    prediction_trade_date=prepared.prediction_trade_date,
                )

            sell_orders = list(execution_plan.get("sell_orders") or [])
            buy_orders = list(execution_plan.get("buy_orders") or [])
            skipped_items = list(execution_plan.get("skipped_items") or [])
            plan_summary = execution_plan.get("summary") or {}
            actionable_orders = sell_orders + buy_orders
            if not actionable_orders:
                error_msg = "调仓预案无可执行委托"
                await manual_execution_persistence.update_task(
                    task_id=task_id,
                    status="failed",
                    stage="signal_loading",
                    error_stage="signal_loading",
                    error_message=error_msg,
                )
                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="error",
                    stage="signal_loading",
                    status="failed",
                    line=error_msg,
                )
                return

            processed = 0
            success_count = 0
            failed_count = 0
            first_error = ""
            total = len(actionable_orders)

            await manual_execution_persistence.update_task(
                task_id=task_id,
                status="dispatching",
                stage="dispatching",
                signal_count=total,
                order_count=0,
                success_count=0,
                failed_count=0,
                progress=0,
            )
            manual_execution_log_stream.update_state(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                stage="dispatching",
                status="dispatching",
                progress=0,
                signal_count=total,
                order_count=0,
                success_count=0,
                failed_count=0,
            )

            # ─── 链路自检：Agent 连通性探测 (仅 REAL 模式必需) ──────────────────
            if trading_mode == "REAL":
                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="info",
                    stage="dispatching",
                    line="[链路诊断] 正在探测 QMT Agent 连通性...",
                )
                heartbeat_key = (
                    f"trade:agent:heartbeat:{tenant_id}:{str(user_id).zfill(8)}"
                )
                redis_client = get_redis().client

                hb_raw = redis_client.get(heartbeat_key)

                if not hb_raw:
                    error_msg = f"诊断失败: QMT Agent 离线 (未发现心跳: {heartbeat_key})，请检查 Windows 端服务是否启动"
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="error",
                        stage="dispatching",
                        line=error_msg,
                    )
                    await manual_execution_persistence.update_task(
                        task_id=task_id,
                        status="failed",
                        stage="dispatching",
                        error_stage="dispatching",
                        error_message=error_msg,
                    )
                    return

                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="info",
                    stage="dispatching",
                    line="[链路诊断] QMT Agent 在线，心跳正常",
                )
                async with get_session(read_only=True) as account_session:
                    from backend.services.trade.routers.real_trading_utils import (
                        _fetch_latest_real_account_snapshot,
                    )

                    latest_snapshot = await _fetch_latest_real_account_snapshot(
                        account_session,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                if not latest_snapshot:
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="warning",
                        stage="dispatching",
                        line="[注意] 未发现 PostgreSQL 账户快照，Agent 可能尚未完成柜台初始化",
                    )
                else:
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="info",
                        stage="dispatching",
                        line="[链路诊断] PostgreSQL 账户快照已就绪，准备派发指令",
                    )

            manual_execution_log_stream.append_log(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                level="info",
                stage="dispatching",
                status="dispatching",
                line=(
                    f"开始派发{task_label}的调仓预案，共 {total} 条委托 "
                    f"(sell={len(sell_orders)}, buy={len(buy_orders)}, skipped={len(skipped_items)})"
                ),
            )

            phase_orders: list[tuple[str, list[dict[str, Any]]]] = [
                ("SELL", sell_orders),
                ("BUY", buy_orders),
            ]
            wait_snapshot_timeout = _manual_task_wait_next_account_timeout_seconds()
            wait_snapshot_poll_interval = _manual_task_account_poll_interval_seconds()
            buy_cancel_timeout = _manual_task_buy_cancel_timeout_seconds()
            snapshot_wait_seconds = 0
            buy_budget_from_snapshot: float | None = None
            buy_cancel_requested_count = 0
            buy_cancel_targets: list[dict[str, Any]] = []
            buy_submitted_order_ids: list[str] = []
            baseline_snapshot = await self._load_latest_account_snapshot(
                tenant_id=tenant_id,
                user_id=user_id,
                trading_mode=trading_mode,
            )
            baseline_snapshot_at = _parse_snapshot_at(
                baseline_snapshot.get("snapshot_at")
                if isinstance(baseline_snapshot, dict)
                else None
            )

            for phase_name, raw_phase_rows in phase_orders:
                phase_rows = list(raw_phase_rows or [])
                if phase_name == "BUY" and buy_orders:
                    should_wait_next_snapshot = (
                        trading_mode == "REAL" and len(sell_orders) > 0
                    )
                    if should_wait_next_snapshot:
                        manual_execution_log_stream.append_log(
                            task_id=task_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            level="info",
                            stage="dispatching",
                            status="running",
                            progress=int((processed / total) * 100),
                            line=(
                                f"卖单已全部提交，开始等待下一次账户上报 "
                                f"(timeout={wait_snapshot_timeout}s, poll={wait_snapshot_poll_interval}s)"
                            ),
                        )
                        next_snapshot, snapshot_wait_seconds = (
                            await self._wait_for_next_account_snapshot(
                                tenant_id=tenant_id,
                                user_id=user_id,
                                trading_mode=trading_mode,
                                baseline_snapshot_at=baseline_snapshot_at,
                                timeout_seconds=wait_snapshot_timeout,
                                poll_interval_seconds=wait_snapshot_poll_interval,
                            )
                        )
                        if not next_snapshot:
                            error_msg = (
                                f"等待下一次账户上报超时({snapshot_wait_seconds}s)，"
                                "已终止买单提交"
                            )
                            await manual_execution_persistence.update_task(
                                task_id=task_id,
                                status="failed",
                                stage="dispatching",
                                error_stage="portfolio_lookup",
                                error_message=error_msg,
                                signal_count=total,
                                order_count=processed,
                                success_count=success_count,
                                failed_count=failed_count + 1,
                            )
                            manual_execution_log_stream.append_log(
                                task_id=task_id,
                                tenant_id=tenant_id,
                                user_id=user_id,
                                level="error",
                                stage="dispatching",
                                status="failed",
                                line=error_msg,
                            )
                            return
                    else:
                        next_snapshot = baseline_snapshot or await self._load_latest_account_snapshot(
                            tenant_id=tenant_id,
                            user_id=user_id,
                            trading_mode=trading_mode,
                        )
                        if trading_mode == "SIMULATION":
                            manual_execution_log_stream.append_log(
                                task_id=task_id,
                                tenant_id=tenant_id,
                                user_id=user_id,
                                level="info",
                                stage="dispatching",
                                status="running",
                                progress=int((processed / total) * 100),
                                line="模拟盘模式：使用当前模拟账户快照重算买单预算，不等待实盘账户上报",
                            )

                    buy_budget_from_snapshot = round(
                        _to_float(
                            (next_snapshot or {}).get("available_cash")
                            or (next_snapshot or {}).get("cash"),
                            0.0,
                        ),
                        2,
                    )
                    if trading_mode == "SIMULATION":
                        phase_rows, rebudget_skipped, remaining_cash = (
                            _rebuild_buy_orders_for_simulation_cash(
                                buy_orders,
                                available_cash=buy_budget_from_snapshot,
                            )
                        )
                    else:
                        phase_rows, rebudget_skipped, remaining_cash = (
                            _rebuild_buy_orders_by_available_cash(
                                buy_orders,
                                available_cash=buy_budget_from_snapshot,
                            )
                        )
                    skipped_items.extend(rebudget_skipped)
                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="info",
                        stage="dispatching",
                        status="running",
                        progress=int((processed / total) * 100),
                        line=(
                            f"检测到新账户快照并重算买单: available_cash={buy_budget_from_snapshot:.2f}, "
                            f"buy_orders={len(phase_rows)}, skipped={len(rebudget_skipped)}, "
                            f"remaining={remaining_cash:.2f}, mode={trading_mode}"
                        ),
                    )
                    for skipped in rebudget_skipped:
                        skip_symbol = str(skipped.get("symbol") or "").strip().upper()
                        skip_reason = str(skipped.get("reason") or "资金不足").strip()
                        manual_execution_log_stream.append_log(
                            task_id=task_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            level="warning",
                            stage="dispatching",
                            status="running",
                            progress=int((processed / total) * 100),
                            line=f"买单跳过: {skip_symbol} | 原因: {skip_reason}",
                        )

                if not phase_rows:
                    continue

                for row in phase_rows:
                    index = processed + 1
                    symbol = str(row.get("symbol") or "").strip().upper()
                    fusion_score = _to_float(row.get("fusion_score"), 0.0)
                    expected_price = _to_float(row.get("price"), 0.0)
                    reference_price = _to_float(row.get("reference_price"), 0.0)
                    preview_price = expected_price if expected_price > 0 else reference_price
                    side = str(row.get("side") or "").strip().upper()
                    trade_action = (
                        str(
                            row.get("trade_action")
                            or ("BUY_TO_OPEN" if side == "BUY" else "SELL_TO_CLOSE")
                        )
                        .strip()
                        .upper()
                    )
                    order_type = "MARKET"
                    quantity = _to_int(row.get("quantity"), 0)

                    order_payload = {
                        "symbol": symbol,
                        "side": side,
                        "quantity": quantity,
                        "price": 0.0,
                        "client_order_id": f"manual-{task_id[-8:]}-{index:04d}",
                        "order_type": order_type,
                        "trading_mode": trading_mode,
                        "remarks": (
                            f"manual_task={task_id} run_id={run_id} "
                            f"fusion_score={fusion_score:.6f} "
                            f"order_type=MARKET "
                            f"preview_price={preview_price:.4f} "
                            f"reason={str(row.get('reason') or '').strip()}"
                        ),
                        "strategy_id": strategy_id,
                        "trade_action": trade_action,
                        "position_side": "LONG",
                        "is_margin_trade": False,
                    }

                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="info",
                        stage="dispatching",
                        status="running",
                        progress=int((index - 1) * 100 / total),
                        line=(
                            f"[{index}/{total}] 正在提交委托: {side} {symbol} "
                            f"qty={quantity} preview={preview_price:.2f} order_type=MARKET"
                        ),
                    )

                    try:
                        # 策略计算与下单
                        from backend.services.trade.services.internal_strategy_dispatcher import (
                            dispatch_internal_strategy_order,
                        )

                        result = await dispatch_internal_strategy_order(
                            order_data=order_payload,
                            user_id=user_id,
                            tenant_id=tenant_id,
                            redis=get_redis(),
                            db=db,
                        )

                        # 严格的状态判断：必须 result["status"] == "success" 且其内部 result["success"] 也是 True
                        # 针对 internal_strategy_dispatcher 的结构进行优化
                        submit_inner_res = result.get("result", {})
                        is_success = (result.get("status") == "success") and (
                            submit_inner_res.get("success") is not False
                        )

                        execution = result.get("execution")
                        order_id = result.get("order_id", "-")

                        if is_success:
                            success_count += 1
                            if trading_mode == "REAL":
                                line = (
                                    f"  >> 已派发: {symbol} | 订单ID: {order_id} | "
                                    f"派发类型: {execution} | 等待QMT委托/成交回报"
                                )
                            else:
                                line = f"  >> 提交完成: {symbol} | 订单ID: {order_id} | 派发类型: {execution}"
                            level = "info"
                            if phase_name == "BUY":
                                try:
                                    buy_submitted_order_ids.append(str(uuid_lib.UUID(str(order_id))))
                                except Exception:
                                    pass
                        elif result.get("status") == "rejected":
                            failed_count += 1
                            violations = result.get("violations", [])
                            line = f"  >> [拦截] 风控拒绝: {symbol} | 原因: {violations}"
                            level = "warning"
                            if not first_error:
                                first_error = f"{symbol}: 风控拦截({violations})"
                        else:
                            failed_count += 1
                            error_detail = (
                                submit_inner_res.get("message")
                                or result.get("detail")
                                or "柜台拒绝或连接断开"
                            )
                            line = f"  >> [失败] 执行异常: {symbol} | 详情: {error_detail}"
                            level = "error"
                            if not first_error:
                                first_error = f"{symbol}: {error_detail}"

                        manual_execution_log_stream.append_log(
                            task_id=task_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            level=level,
                            stage="dispatching",
                            line=line,
                        )

                    except Exception as e:
                        failed_count += 1
                        error_msg = (
                            f"  >> [崩溃] 处理标的 {symbol} 时发生程序异常: {str(e)}"
                        )
                        manual_execution_log_stream.append_log(
                            task_id=task_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            level="error",
                            stage="dispatching",
                            line=error_msg,
                        )
                        if not first_error:
                            first_error = str(e)

                    processed = index
                    progress = int((processed / total) * 100)

                    # 实时更新进度
                    if index % 5 == 0 or index == total:
                        await manual_execution_persistence.update_task(
                            task_id=task_id,
                            status="running" if index < total else "completed",
                            progress=progress,
                            order_count=index,
                            success_count=success_count,
                            failed_count=failed_count,
                        )

                    # 给日志流一点喘息时间，避免瞬间冲刷
                    await asyncio.sleep(0.05)

            if buy_submitted_order_ids:
                manual_execution_log_stream.append_log(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    level="info",
                    stage="dispatching",
                    status="running",
                    progress=int((processed / total) * 100),
                    line=(
                        f"买单已全部提交，开始 {buy_cancel_timeout}s 成交观察窗，"
                        "超时将对未完全成交买单发起撤单"
                    ),
                )
                await asyncio.sleep(buy_cancel_timeout)
                from backend.services.trade.services.trading_engine import TradingEngine

                parsed_ids: list[uuid_lib.UUID] = []
                for order_id in buy_submitted_order_ids:
                    try:
                        parsed_ids.append(uuid_lib.UUID(str(order_id)))
                    except Exception:
                        continue

                if parsed_ids:
                    engine = TradingEngine(db, get_redis())
                    buy_orders_stmt = (
                        select(Order)
                        .where(
                            and_(
                                Order.tenant_id == tenant_id,
                                Order.user_id == int(user_id),
                                Order.order_id.in_(parsed_ids),
                            )
                        )
                    )
                    buy_order_rows = (
                        (await db.execute(buy_orders_stmt)).scalars().all()
                    )
                    for submitted_order in buy_order_rows:
                        current_status = str(
                            getattr(submitted_order.status, "value", submitted_order.status)
                            or ""
                        )
                        cancel_requested = False
                        if _is_cancelable_buy_status(submitted_order.status):
                            cancel_requested = bool(
                                await engine.cancel_order_execution(submitted_order)
                            )
                            if cancel_requested:
                                buy_cancel_requested_count += 1
                        buy_cancel_targets.append(
                            {
                                "order_id": str(submitted_order.order_id),
                                "symbol": str(submitted_order.symbol or ""),
                                "status": current_status,
                                "cancel_requested": cancel_requested,
                            }
                        )

                    manual_execution_log_stream.append_log(
                        task_id=task_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        level="info",
                        stage="dispatching",
                        status="running",
                        progress=int((processed / total) * 100),
                        line=(
                            f"买单超时撤单统计: submitted={len(buy_submitted_order_ids)}, "
                            f"cancel_requested={buy_cancel_requested_count}"
                        ),
                    )

            result_payload = {
                "success": failed_count == 0,
                "task_id": task_id,
                "task_type": task_type,
                "run_id": run_id,
                "model_id": prepared.model_id,
                "strategy_id": strategy_id,
                "strategy_name": prepared.strategy_name,
                "prediction_trade_date": prepared.prediction_trade_date.isoformat(),
                "trading_mode": trading_mode,
                "signal_count": total,
                "order_count": processed,
                "success_count": success_count,
                "failed_count": failed_count,
                "first_error": first_error or None,
                "preview_summary": plan_summary,
                "snapshot_wait_seconds": snapshot_wait_seconds,
                "buy_budget_from_snapshot": buy_budget_from_snapshot,
                "buy_cancel_requested_count": buy_cancel_requested_count,
                "buy_cancel_targets": buy_cancel_targets,
                "stage_label": _stage_label("completed"),
            }
            await manual_execution_persistence.update_task(
                task_id=task_id,
                status="completed",
                stage="completed",
                signal_count=total,
                order_count=processed,
                success_count=success_count,
                failed_count=failed_count,
                result_payload=result_payload,
                progress=100,
            )
            manual_execution_log_stream.append_log(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                level="info" if failed_count == 0 else "warning",
                stage="completed",
                status="completed",
                progress=100,
                line=(
                    f"{task_label}派单完成: signals={total}, orders={processed}, "
                    f"success={success_count}, failed={failed_count}"
                ),
                summary={
                    **result_payload,
                    "stage_label": _stage_label("completed"),
                },
            )
            manual_execution_log_stream.update_state(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                stage="completed",
                status="completed",
                progress=100,
                signal_count=total,
                order_count=processed,
                success_count=success_count,
                failed_count=failed_count,
                summary={
                    **result_payload,
                    "stage_label": _stage_label("completed"),
                },
                last_line=(
                    f"{task_label}派单完成: signals={total}, orders={processed}, "
                    f"success={success_count}, failed={failed_count}"
                ),
            )

    async def execute_task_by_id(self, task_id: str) -> None:
        task = await manual_execution_persistence.get_task_any(task_id)
        if task is None:
            return
        await self.process_task(task)


manual_execution_service = ManualExecutionService()
