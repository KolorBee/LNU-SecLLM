"""
真实单笔交易统计工具。

统一基于 buy/sell 成交流水按 FIFO 闭环配对，产出单笔收益、持仓天数、
月度交易频率等指标，供回测预计算与高级分析查询复用。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np
import pandas as pd


def build_closed_trade_frame(trades: list[dict[str, Any]] | pd.DataFrame | None) -> pd.DataFrame:
    """将成交流水重建为已平仓闭环单笔记录。"""
    return summarize_trade_matching(trades)["closed_trades"]


def summarize_trade_matching(trades: list[dict[str, Any]] | pd.DataFrame | None) -> dict[str, Any]:
    """汇总真实成交配对结果，兼顾已平仓闭环与未平仓买入笔数。"""
    if trades is None:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    working = trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame(trades)
    if working.empty:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    date_col = next((column for column in ["trade_date", "date", "datetime", "created_at"] if column in working.columns), None)
    if date_col is None or "symbol" not in working.columns or "action" not in working.columns:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    price_col = "price" if "price" in working.columns else ("adj_price" if "adj_price" in working.columns else None)
    qty_col = "quantity" if "quantity" in working.columns else ("adj_quantity" if "adj_quantity" in working.columns else None)
    if price_col is None or qty_col is None:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    normalized = working.copy()
    normalized[date_col] = pd.to_datetime(normalized[date_col], errors="coerce")
    normalized = normalized.dropna(subset=[date_col, "symbol", "action"])
    if normalized.empty:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    normalized["action_norm"] = normalized["action"].astype(str).str.lower().str.strip()
    normalized = normalized[normalized["action_norm"].isin(["buy", "sell"])]
    if normalized.empty:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    normalized["qty"] = pd.to_numeric(normalized[qty_col], errors="coerce").abs()
    normalized["price_value"] = pd.to_numeric(normalized[price_col], errors="coerce")
    commission_source = normalized["commission"] if "commission" in normalized.columns else pd.Series(0.0, index=normalized.index)
    normalized["commission_value"] = pd.to_numeric(commission_source, errors="coerce").fillna(0.0).abs()
    normalized = normalized.replace([np.inf, -np.inf], np.nan)
    normalized = normalized.dropna(subset=["qty", "price_value"])
    normalized = normalized[normalized["qty"] > 0]
    if normalized.empty:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": 0}

    normalized = normalized.sort_values(by=[date_col], kind="mergesort")

    open_lots: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    closed_records: list[dict[str, Any]] = []

    for row in normalized.to_dict("records"):
        symbol = str(row["symbol"])
        action = str(row["action_norm"])
        trade_date = row[date_col]
        quantity = float(row["qty"])
        price = float(row["price_value"])
        commission = float(row.get("commission_value", 0.0))
        commission_per_share = commission / quantity if quantity > 0 else 0.0

        if action == "buy":
            open_lots[symbol].append(
                {
                    "remaining_qty": quantity,
                    "buy_date": trade_date,
                    "buy_price": price,
                    "buy_commission_per_share": commission_per_share,
                }
            )
            continue

        remaining = quantity
        while remaining > 1e-8 and open_lots[symbol]:
            lot = open_lots[symbol][0]
            lot_qty = float(lot["remaining_qty"])
            consume = min(remaining, lot_qty)

            entry_cost = consume * (float(lot["buy_price"]) + float(lot["buy_commission_per_share"]))
            exit_value = consume * (price - commission_per_share)
            pnl = exit_value - entry_cost
            return_pct = pnl / entry_cost if abs(entry_cost) > 1e-12 else 0.0
            holding_days = max((trade_date - lot["buy_date"]).days, 1)

            closed_records.append(
                {
                    "symbol": symbol,
                    "entry_date": lot["buy_date"],
                    "exit_date": trade_date,
                    "quantity": consume,
                    "entry_cost": entry_cost,
                    "exit_value": exit_value,
                    "pnl": pnl,
                    "return_pct": return_pct,
                    "holding_days": float(holding_days),
                }
            )

            remaining -= consume
            lot_qty -= consume
            if lot_qty <= 1e-8:
                open_lots[symbol].popleft()
            else:
                lot["remaining_qty"] = lot_qty

    open_buy_trades = sum(len(queue) for queue in open_lots.values())
    if not closed_records:
        return {"closed_trades": pd.DataFrame(), "open_buy_trades": int(open_buy_trades)}

    return {
        "closed_trades": pd.DataFrame(closed_records),
        "open_buy_trades": int(open_buy_trades),
    }


def calculate_closed_trade_metrics(
    closed_trades: pd.DataFrame,
    *,
    total_trade_events: int,
    open_buy_trades: int = 0,
    daily_returns: pd.Series | None = None,
    fallback_win_rate: float | None = None,
    fallback_profit_factor: float | None = None,
) -> dict[str, Any]:
    """基于闭环单笔或兼容回退口径计算高级分析指标。"""
    clean_returns = pd.Series(dtype=float)
    if daily_returns is not None:
        clean_returns = pd.to_numeric(pd.Series(daily_returns), errors="coerce")
        clean_returns = clean_returns.replace([np.inf, -np.inf], np.nan).dropna()

    result: dict[str, Any] = {
        "metric_basis": "summary_fallback",
        "total_trades": int(total_trade_events),
        "closed_trades": 0,
        "open_buy_trades": int(open_buy_trades),
        "winning_trades": 0,
        "losing_trades": 0,
        "flat_trades": 0,
        "real_win_rate": 0.0,
        "win_rate": float(fallback_win_rate or 0.0),
        "profit_loss_ratio": 0.0,
        "profit_factor": float(fallback_profit_factor or 0.0),
        "avg_win_return": 0.0,
        "avg_loss_return": 0.0,
        "avg_trade_return": 0.0,
        "median_trade_return": 0.0,
        "max_win_return": 0.0,
        "max_loss_return": 0.0,
        "avg_holding_days": 0.0,
        "trade_frequency": 0.0,
        "profit_loss_days_ratio": calculate_profit_loss_days_ratio(clean_returns),
    }

    if closed_trades.empty:
        if not clean_returns.empty:
            months = max(int(len(clean_returns) / 21), 1)
            result["trade_frequency"] = float(total_trade_events / months)
        return result

    pnl = pd.to_numeric(closed_trades["pnl"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    returns = pd.to_numeric(closed_trades["return_pct"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    holding_days = pd.to_numeric(closed_trades["holding_days"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()

    wins = returns[returns > 0]
    losses = returns[returns < 0]
    flats = returns[returns == 0]

    pnl_wins = pnl[pnl > 0]
    pnl_losses = pnl[pnl < 0]

    closed_count = int(len(returns))
    win_count = int(len(wins))
    loss_count = int(len(losses))
    flat_count = int(len(flats))

    avg_win_return = float(wins.mean()) if not wins.empty else 0.0
    avg_loss_return = abs(float(losses.mean())) if not losses.empty else 0.0
    profit_loss_ratio = float(avg_win_return / avg_loss_return) if avg_loss_return > 0 else 0.0

    total_win_pnl = float(pnl_wins.sum()) if not pnl_wins.empty else 0.0
    total_loss_pnl = abs(float(pnl_losses.sum())) if not pnl_losses.empty else 0.0
    profit_factor = float(total_win_pnl / total_loss_pnl) if total_loss_pnl > 0 else (float("inf") if total_win_pnl > 0 else 0.0)

    month_span = 1
    if "exit_date" in closed_trades.columns:
        exit_dates = pd.to_datetime(closed_trades["exit_date"], errors="coerce").dropna()
        if not exit_dates.empty:
            grouped = exit_dates.dt.to_period("M").value_counts()
            month_span = max(len(grouped.index), 1)
    elif not clean_returns.empty:
        month_span = max(int(len(clean_returns) / 21), 1)

    result.update(
        {
            "metric_basis": "closed_trade_fifo",
            "closed_trades": closed_count,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "flat_trades": flat_count,
            "real_win_rate": float(win_count / closed_count) if closed_count > 0 else 0.0,
            "win_rate": float(win_count / closed_count) if closed_count > 0 else 0.0,
            "profit_loss_ratio": profit_loss_ratio,
            "profit_factor": profit_factor,
            "avg_win_return": avg_win_return,
            "avg_loss_return": avg_loss_return,
            "avg_trade_return": float(returns.mean()) if not returns.empty else 0.0,
            "median_trade_return": float(returns.median()) if not returns.empty else 0.0,
            "max_win_return": float(returns.max()) if not returns.empty else 0.0,
            "max_loss_return": float(returns.min()) if not returns.empty else 0.0,
            "avg_holding_days": float(holding_days.mean()) if not holding_days.empty else 0.0,
            "trade_frequency": float(closed_count / month_span),
        }
    )
    return result


def calculate_profit_loss_days_ratio(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    win_days = int((returns > 0).sum())
    loss_days = int((returns < 0).sum())
    if loss_days == 0:
        return float(win_days) if win_days > 0 else 0.0
    return float(win_days / loss_days)


def build_trade_frequency_series_from_closed_trades(closed_trades: pd.DataFrame) -> dict[str, list[Any]]:
    series = {"dates": [], "values": []}
    if closed_trades.empty or "exit_date" not in closed_trades.columns:
        return series

    exit_dates = pd.to_datetime(closed_trades["exit_date"], errors="coerce")
    working = closed_trades.copy()
    working["_exit_month"] = exit_dates.dt.to_period("M")
    grouped = working.dropna(subset=["_exit_month"]).groupby("_exit_month").size()
    for period, count in grouped.items():
        series["dates"].append(period.to_timestamp().strftime("%Y-%m-%d"))
        series["values"].append(float(count))
    return series
