"""Qlib 回测导出工具"""

import numpy as np
from typing import Any


def _to_finite_float(value: Any) -> float | None:
    try:
        val = float(value)
    except Exception:
        return None
    if val != val or val in (float("inf"), float("-inf")):
        return None
    return val


def _normalize_display_quantity(symbol: str, quantity: float) -> int:
    qty_int = int(round(float(quantity)))
    symbol_upper = str(symbol or "").upper()
    if symbol_upper.startswith(("SH", "SZ", "BJ")) and qty_int >= 100:
        lot_rounded = int(round(qty_int / 100.0) * 100)
        if abs(qty_int - lot_rounded) <= 2:
            return lot_rounded
    return qty_int


def _build_quick_trade_rows(
    *,
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    initial_capital: float | None,
) -> list[dict[str, Any]]:
    """
    将 trades 列表转换为前端展示用的行数据，并为每行推算权益余额。

    权益推算策略（按优先级）：
    1. 若当天有 equity_after 快照（来自 recording_strategy），则用日末权益逆序回推各笔交易的中间权益：
       - 当天最后一笔：直接用 equity_after（日末快照）
       - 中间笔次：逐步加回手续费近似还原交易前的权益
    2. 若当天无 equity_after（历史数据兜底）：
       - 从 running_cash + 持仓市值 正向重建
       - 用 equity_curve 提供的日末权益修正偏差

    注意：本版本（开源版）cn_exchange.get_deal_price() 返回未复权价格，
    recording_strategy 写入的 price / quantity 已是真实显示口径，无需再次还原。
    """
    equity_by_date: dict[str, float] = {}
    for point in equity_curve:
        if not isinstance(point, dict):
            continue
        date_key = str(point.get("date", ""))[:10]
        value = _to_finite_float(point.get("value"))
        if date_key and value is not None:
            equity_by_date[date_key] = value

    # ─── 第一遍：提取每笔交易的核心字段 ────────────────────────────────────
    normalized_trades: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue

        factor = _to_finite_float(trade.get("factor"))
        has_valid_factor = factor is not None and factor > 0

        explicit_price = _to_finite_float(trade.get("price"))
        explicit_quantity = _to_finite_float(trade.get("quantity"))
        adj_price = _to_finite_float(trade.get("adj_price"))
        adj_quantity = _to_finite_float(trade.get("adj_quantity"))

        if adj_price is None:
            adj_price = explicit_price
        if adj_quantity is None:
            adj_quantity = explicit_quantity

        display_price = explicit_price if explicit_price is not None else 0.0
        display_quantity = explicit_quantity if explicit_quantity is not None else 0.0

        # 兼容性处理（旧数据 adj_price/adj_quantity 可能是复权口径）：
        quantity_is_integer_like = (
            explicit_quantity is not None and np.isfinite(explicit_quantity)
            and abs(explicit_quantity - round(explicit_quantity)) <= 1e-6
        )
        price_looks_adjusted = (
            explicit_price is not None and adj_price is not None and factor is not None and factor > 0
            and explicit_price < adj_price * 0.9
        )
        should_restore = (
            has_valid_factor and adj_price is not None and adj_quantity is not None
            and ((explicit_quantity is None or not quantity_is_integer_like) or price_looks_adjusted)
        )
        if should_restore:
            display_price = adj_price / factor
            display_quantity = adj_quantity * factor

        qty_int = _normalize_display_quantity(str(trade.get("symbol", "")), display_quantity)

        # 优先使用 totalAmount（recording_strategy 写的真实成交额）
        amount = _to_finite_float(trade.get("totalAmount", trade.get("total_amount")))
        if amount is None:
            amount = display_price * display_quantity

        commission = _to_finite_float(trade.get("commission"))
        if commission is None:
            commission = 0.0

        action_raw = str(trade.get("action", "")).strip().lower()
        is_buy = action_raw == "buy"
        is_sell = action_raw == "sell"

        equity_after = _to_finite_float(trade.get("equity_after"))
        cash_after = _to_finite_float(trade.get("cash_after"))
        position_value_after = _to_finite_float(trade.get("position_value_after"))
        legacy_balance = _to_finite_float(trade.get("balance"))

        # 日末权益快照（equity_after 优先，其次 cash+持仓，其次 balance）
        day_end_equity = (
            equity_after
            if equity_after is not None
            else (cash_after + position_value_after)
            if cash_after is not None and position_value_after is not None
            else legacy_balance
        )

        trade_date = str(trade.get("date", ""))
        trade_day = trade_date[:10]

        normalized_trades.append(
            {
                "trade_date": trade_date,
                "trade_day": trade_day,
                "symbol": str(trade.get("symbol", "")),
                "display_price": display_price,
                "display_quantity": display_quantity,
                "qty_int": qty_int,
                "amount": amount,
                "commission": commission,
                "is_buy": is_buy,
                "is_sell": is_sell,
                "day_end_equity": day_end_equity,
            }
        )

    # ─── 第二遍：收集每天的日末权益快照 ────────────────────────────────────
    # 关键认知：recording_strategy.log_executed_trades() 在同一步长内批量处理所有订单后
    # 立即快照账户状态，因此同一天所有交易的 equity_after 值相同（日末快照），这是正常现象。
    days_with_end_equity: dict[str, float] = {}
    for item in normalized_trades:
        eq = item["day_end_equity"]
        if eq is not None:
            days_with_end_equity[item["trade_day"]] = eq

    # 按日分组
    from collections import defaultdict
    day_trade_indices: dict[str, list[int]] = defaultdict(list)
    for idx, item in enumerate(normalized_trades):
        day_trade_indices[item["trade_day"]].append(idx)

    # ─── 第三遍：为有日末快照的天逆序回推，无快照天正向重建 ──────────────
    equity_balance_by_index: dict[int, float | None] = {}
    running_cash: float | None = initial_capital
    position_qty_by_symbol: dict[str, float] = {}
    last_price_by_symbol: dict[str, float] = {}

    for trade_day in sorted(day_trade_indices.keys()):
        indices = day_trade_indices[trade_day]
        day_end_equity = days_with_end_equity.get(trade_day)

        if day_end_equity is not None:
            # ── 有日末快照：先正向推进持仓状态，再逆序回推权益 ──────────
            for idx in indices:
                item = normalized_trades[idx]
                symbol = item["symbol"]
                display_price = item["display_price"]
                display_quantity = item["display_quantity"]
                amount = item["amount"]
                commission = item["commission"]
                is_buy = item["is_buy"]
                is_sell = item["is_sell"]

                if display_price:
                    last_price_by_symbol[symbol] = display_price
                if symbol:
                    current_qty = position_qty_by_symbol.get(symbol, 0.0)
                    if is_buy:
                        next_qty = current_qty + display_quantity
                    elif is_sell:
                        next_qty = current_qty - display_quantity
                    else:
                        next_qty = current_qty
                    if abs(next_qty) < 1e-9:
                        position_qty_by_symbol.pop(symbol, None)
                    else:
                        position_qty_by_symbol[symbol] = next_qty
                if running_cash is not None:
                    if is_buy:
                        running_cash -= amount + commission
                    elif is_sell:
                        running_cash += amount - commission

            # 逆序回推：从日末快照依次撤销后续交易（手续费近似）
            equity_at_end = day_end_equity
            for idx in reversed(indices):
                equity_balance_by_index[idx] = equity_at_end
                item = normalized_trades[idx]
                commission = item["commission"]
                # 每笔交易前的权益 ≈ 当前权益 + 本笔手续费（买卖都只差手续费损耗）
                equity_at_end = equity_at_end + commission

        else:
            # ── 无日末快照：正向重建 + equity_curve 锚点修正 ──────────
            reconstructed_values: list[float | None] = []
            for idx in indices:
                item = normalized_trades[idx]
                symbol = item["symbol"]
                display_price = item["display_price"]
                display_quantity = item["display_quantity"]
                amount = item["amount"]
                commission = item["commission"]
                is_buy = item["is_buy"]
                is_sell = item["is_sell"]

                if display_price:
                    last_price_by_symbol[symbol] = display_price
                if running_cash is not None:
                    if is_buy:
                        running_cash -= amount + commission
                    elif is_sell:
                        running_cash += amount - commission
                if symbol:
                    current_qty = position_qty_by_symbol.get(symbol, 0.0)
                    if is_buy:
                        next_qty = current_qty + display_quantity
                    elif is_sell:
                        next_qty = current_qty - display_quantity
                    else:
                        next_qty = current_qty
                    if abs(next_qty) < 1e-9:
                        position_qty_by_symbol.pop(symbol, None)
                    else:
                        position_qty_by_symbol[symbol] = next_qty

                pos_value = sum(
                    qty * last_price_by_symbol[s]
                    for s, qty in position_qty_by_symbol.items()
                    if s in last_price_by_symbol
                )
                reconstructed = running_cash + pos_value if running_cash is not None else None
                reconstructed_values.append(reconstructed)
                equity_balance_by_index[idx] = reconstructed

            # 用 equity_curve 锚点修正整体偏差
            anchor = equity_by_date.get(trade_day)
            if anchor is not None and reconstructed_values and reconstructed_values[-1] is not None:
                offset = anchor - reconstructed_values[-1]
                for idx in indices:
                    val = equity_balance_by_index.get(idx)
                    if val is not None:
                        equity_balance_by_index[idx] = val + offset

    # ─── 第四遍：组装最终输出行 ───────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(normalized_trades):
        trade_day = item["trade_day"]
        equity_balance = equity_balance_by_index.get(idx)
        if equity_balance is None:
            equity_balance = equity_by_date.get(trade_day)

        rows.append(
            {
                "date": item["trade_date"],
                "symbol": item["symbol"],
                "action": "买入" if item["is_buy"] else "卖出",
                "display_price": item["display_price"],
                "qty_int": item["qty_int"],
                "amount": item["amount"],
                "commission": item["commission"],
                "equity_balance": equity_balance,
            }
        )

    return rows
