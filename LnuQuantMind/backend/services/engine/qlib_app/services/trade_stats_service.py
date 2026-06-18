"""
交易统计分析服务。

提供基于真实成交流水 FIFO 闭环重建的单笔交易统计指标。
"""

import logging

import numpy as np
import pandas as pd

from backend.services.engine.qlib_app.schemas.analysis import (
    HistogramData,
    TimeSeriesData,
    TradeStatsMetrics,
    TradeStatsResponse,
)
from backend.services.engine.qlib_app.services.backtest_persistence import (
    BacktestPersistence,
)
from backend.services.engine.qlib_app.services.trade_metrics_utils import (
    build_closed_trade_frame,
    build_trade_frequency_series_from_closed_trades,
    calculate_closed_trade_metrics,
    calculate_profit_loss_days_ratio,
    summarize_trade_matching,
)
from backend.services.engine.qlib_app.utils.structured_logger import StructuredTaskLogger

logger = logging.getLogger(__name__)
task_logger = StructuredTaskLogger(logger, "TradeStatsService")


class TradeStatsService:
    """交易统计分析服务"""

    def __init__(self):
        self._persistence = BacktestPersistence()
        task_logger.info("init", "TradeStatsService initialized")

    async def analyze(self, backtest_id: str, user_id: str, tenant_id: str = "default") -> TradeStatsResponse:
        try:
            result = await self._persistence.get_result(
                backtest_id,
                tenant_id=tenant_id,
                include_fields=[
                    "trades",
                    "equity_curve",
                    "backtest_id",
                    "win_rate",
                    "profit_factor",
                    "total_trades",
                    "advanced_stats",
                    "avg_holding_period",
                ],
            )
            if not result:
                raise ValueError(f"回测结果不存在: {backtest_id}")

            returns = self._extract_returns(result)
            trade_events = list(getattr(result, "trades", None) or [])
            trade_matching = summarize_trade_matching(trade_events)
            closed_trades = trade_matching["closed_trades"]
            real_trade_metrics = calculate_closed_trade_metrics(
                closed_trades,
                total_trade_events=len(trade_events),
                open_buy_trades=int(trade_matching.get("open_buy_trades", 0)),
                daily_returns=returns,
                fallback_win_rate=getattr(result, "win_rate", None),
                fallback_profit_factor=getattr(result, "profit_factor", None),
            )

            adv = getattr(result, "advanced_stats", None)
            if adv and isinstance(adv, dict) and "pnl_distribution" in adv:
                task_logger.info("precomputed", "使用预计算的交易统计指标", backtest_id=backtest_id, tenant_id=tenant_id)
                hydrated_metrics = self._hydrate_precomputed_metrics(
                    result=result,
                    adv=adv,
                    returns=returns,
                    real_trade_metrics=real_trade_metrics,
                )
                return TradeStatsResponse(
                    metrics=self._build_metrics(hydrated_metrics),
                    pnl_distribution=self._coerce_histogram(adv.get("pnl_distribution")),
                    holding_days_distribution=self._coerce_histogram(adv.get("holding_days_distribution")),
                    trade_frequency_series=self._coerce_time_series(adv.get("trade_frequency_series")),
                )

            task_logger.info("recompute", "未找到预计算指标，开始实时计算", backtest_id=backtest_id, tenant_id=tenant_id)
            return self._build_recomputed_response(
                backtest_id=backtest_id,
                returns=returns,
                trade_events=trade_events,
                closed_trades=closed_trades,
                real_trade_metrics=real_trade_metrics,
            )
        except Exception as exc:
            task_logger.exception("failed", "交易统计分析失败", backtest_id=backtest_id, tenant_id=tenant_id, error=str(exc))
            raise

    def _build_recomputed_response(
        self,
        *,
        backtest_id: str,
        returns: pd.Series,
        trade_events: list[dict],
        closed_trades: pd.DataFrame,
        real_trade_metrics: dict[str, float | int | str],
    ) -> TradeStatsResponse:
        if trade_events:
            task_logger.info("use_trades", "使用真实交易记录", backtest_id=backtest_id, count=len(trade_events))
            trades = self._build_trades_frame(trade_events, returns, backtest_id=backtest_id, allow_mock=False)
        else:
            task_logger.info("mock_trades", "未找到真实交易记录，使用收益率曲线推导模拟数据", backtest_id=backtest_id)
            trades = self._build_trades_frame(None, returns, backtest_id=backtest_id, allow_mock=True)

        if trades.empty and closed_trades.empty:
            raise ValueError(f"交易数据不存在或为空: backtest_id={backtest_id}")

        holding_days_series = self._resolve_holding_days_series(closed_trades, trades)
        pnl_hist = self._build_histogram(self._resolve_pnl_series_for_histogram(closed_trades), bins=20)
        holding_hist = self._build_holding_period_histogram(holding_days_series)
        freq_series = self._build_trade_frequency_series(closed_trades, returns.index)

        payload = dict(real_trade_metrics)
        payload["avg_holding_days"] = (
            float(holding_days_series.mean()) if not holding_days_series.empty else float(real_trade_metrics.get("avg_holding_days", 0.0))
        )

        return TradeStatsResponse(
            metrics=self._build_metrics(payload),
            pnl_distribution=pnl_hist,
            holding_days_distribution=holding_hist,
            trade_frequency_series=freq_series,
        )

    def _hydrate_precomputed_metrics(
        self,
        *,
        result,
        adv: dict,
        returns: pd.Series,
        real_trade_metrics: dict[str, float | int | str],
    ) -> dict[str, float | int | str]:
        payload = dict(real_trade_metrics)

        profit_loss_days_ratio = self._to_finite_float(adv.get("profit_loss_days_ratio"))
        avg_holding_days = self._to_finite_float(adv.get("avg_holding_days"))
        trade_frequency = self._to_finite_float(adv.get("trade_frequency"))

        trades = pd.DataFrame()
        if avg_holding_days is None:
            trades = self._build_trades_frame(getattr(result, "trades", None), returns, backtest_id=str(getattr(result, "backtest_id", "")), allow_mock=False)

        if profit_loss_days_ratio is None:
            profit_loss_days_ratio = calculate_profit_loss_days_ratio(returns)

        if avg_holding_days is None:
            summary_holding = self._to_finite_float(getattr(result, "avg_holding_period", None))
            if summary_holding is not None:
                avg_holding_days = summary_holding
            elif not trades.empty:
                avg_holding_days = float(self._resolve_holding_days_series(pd.DataFrame(), trades).mean())
            else:
                avg_holding_days = float(payload.get("avg_holding_days", 0.0))

        if trade_frequency is None:
            trade_frequency = self._resolve_trade_frequency(
                total_trades=int(payload.get("closed_trades", 0)),
                returns=returns,
                trade_frequency_series=adv.get("trade_frequency_series"),
            )

        payload.update(
            {
                "profit_loss_days_ratio": float(profit_loss_days_ratio),
                "avg_holding_days": float(avg_holding_days),
                "trade_frequency": float(trade_frequency),
                "total_trades": int(payload.get("total_trades", int(result.total_trades or 0))),
            }
        )
        return payload

    def _build_metrics(self, payload: dict[str, float | int | str]) -> TradeStatsMetrics:
        return TradeStatsMetrics(
            win_rate=float(payload.get("win_rate", 0.0)),
            profit_loss_ratio=float(payload.get("profit_loss_ratio", 0.0)),
            profit_loss_days_ratio=float(payload.get("profit_loss_days_ratio", 0.0)),
            real_win_rate=float(payload.get("real_win_rate", 0.0)),
            avg_win_return=float(payload.get("avg_win_return", 0.0)),
            avg_loss_return=float(payload.get("avg_loss_return", 0.0)),
            avg_trade_return=float(payload.get("avg_trade_return", 0.0)),
            median_trade_return=float(payload.get("median_trade_return", 0.0)),
            max_win_return=float(payload.get("max_win_return", 0.0)),
            max_loss_return=float(payload.get("max_loss_return", 0.0)),
            avg_holding_days=float(payload.get("avg_holding_days", 0.0)),
            trade_frequency=float(payload.get("trade_frequency", 0.0)),
            total_trades=int(payload.get("total_trades", 0)),
            closed_trades=int(payload.get("closed_trades", 0)),
            open_buy_trades=int(payload.get("open_buy_trades", 0)),
            winning_trades=int(payload.get("winning_trades", 0)),
            losing_trades=int(payload.get("losing_trades", 0)),
            flat_trades=int(payload.get("flat_trades", 0)),
            profit_factor=float(payload.get("profit_factor", 0.0)),
            metric_basis=str(payload.get("metric_basis", "summary_fallback")),
        )

    def _build_trades_frame(
        self,
        trades_payload,
        returns: pd.Series,
        *,
        backtest_id: str,
        allow_mock: bool,
    ) -> pd.DataFrame:
        if trades_payload:
            trades = pd.DataFrame(trades_payload)
            if not trades.empty:
                return self._normalize_trade_dates(trades, returns)
        if allow_mock:
            return self._generate_mock_trades_from_returns(returns, backtest_id)
        return pd.DataFrame()

    def _normalize_trade_dates(self, trades: pd.DataFrame, returns: pd.Series) -> pd.DataFrame:
        normalized = trades.copy()
        if "trade_date" not in normalized.columns:
            if "date" in normalized.columns:
                normalized["trade_date"] = normalized["date"]
            elif "datetime" in normalized.columns:
                normalized["trade_date"] = normalized["datetime"]
            elif "created_at" in normalized.columns:
                normalized["trade_date"] = normalized["created_at"]
            elif returns.empty:
                normalized["trade_date"] = pd.Timestamp.now().normalize()
            else:
                fallback_dates = returns.index
                normalized["trade_date"] = [fallback_dates[i % len(fallback_dates)] for i in range(len(normalized))]

        normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
        if normalized["trade_date"].isna().all():
            if not returns.empty:
                fallback_dates = returns.index
                normalized["trade_date"] = [fallback_dates[i % len(fallback_dates)] for i in range(len(normalized))]
            else:
                normalized["trade_date"] = pd.Timestamp.now().normalize()
        else:
            normalized["trade_date"] = normalized["trade_date"].ffill().bfill()
        return normalized

    def _resolve_trade_frequency(
        self,
        *,
        total_trades: int,
        returns: pd.Series,
        trade_frequency_series,
    ) -> float:
        clean_returns = pd.to_numeric(pd.Series(returns), errors="coerce")
        clean_returns = clean_returns.replace([np.inf, -np.inf], np.nan).dropna()
        if not clean_returns.empty:
            months = max(int(len(clean_returns) / 21), 1)
            return float(total_trades / months)

        if isinstance(trade_frequency_series, dict):
            values = trade_frequency_series.get("values") or []
            numeric_values = [float(v) for v in values if self._to_finite_float(v) is not None]
            if numeric_values:
                return float(sum(numeric_values) / len(numeric_values))

        return 0.0

    def _to_finite_float(self, value) -> float | None:
        try:
            if value is None:
                return None
            numeric = float(value)
            if np.isnan(numeric) or np.isinf(numeric):
                return None
            return numeric
        except Exception:
            return None

    def _resolve_pnl_series_for_histogram(self, closed_trades: pd.DataFrame) -> pd.Series:
        if closed_trades.empty or "return_pct" not in closed_trades.columns:
            return pd.Series([0.0], dtype=float)
        returns = pd.to_numeric(closed_trades["return_pct"], errors="coerce")
        returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
        if returns.empty:
            return pd.Series([0.0], dtype=float)
        return returns

    def _resolve_holding_days_series(self, closed_trades: pd.DataFrame, trades: pd.DataFrame) -> pd.Series:
        if not closed_trades.empty and "holding_days" in closed_trades.columns:
            holding = pd.to_numeric(closed_trades["holding_days"], errors="coerce")
            holding = holding.replace([np.inf, -np.inf], np.nan).dropna()
            if not holding.empty:
                return holding.clip(lower=1.0)

        if "holding_days" in trades.columns:
            holding = pd.to_numeric(trades["holding_days"], errors="coerce")
            holding = holding.replace([np.inf, -np.inf], np.nan).dropna()
            if not holding.empty:
                return holding.clip(lower=1.0)

        return pd.Series([1.0], dtype=float)

    def _extract_returns(self, result) -> pd.Series:
        if not result.equity_curve:
            return pd.Series(dtype=float)
        df = pd.DataFrame(result.equity_curve)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df["value"].pct_change().fillna(0)

    def _generate_mock_trades_from_returns(self, returns: pd.Series, backtest_id: str) -> pd.DataFrame:
        if returns.empty:
            return pd.DataFrame()

        np.random.seed(self._seed_from_backtest(backtest_id) + 7)
        significant_days = returns[abs(returns) > 0.0001].index
        if len(significant_days) < 5:
            significant_days = returns.index

        total_trades = min(len(significant_days), 100)
        if total_trades == 0:
            return pd.DataFrame()

        trade_days = np.random.choice(significant_days, size=total_trades, replace=False)
        trade_days = pd.to_datetime(sorted(trade_days))
        real_pnl = returns.loc[trade_days].values
        pnl = real_pnl * np.random.uniform(0.8, 1.2, size=total_trades)
        holding_days = np.random.randint(1, 11, size=total_trades)

        return pd.DataFrame({"trade_date": trade_days, "pnl": pnl, "holding_days": holding_days})

    def _build_histogram(self, series: pd.Series, bins: int) -> HistogramData:
        clean = pd.to_numeric(series, errors="coerce")
        clean = clean.replace([np.inf, -np.inf], np.nan).dropna()
        if clean.empty:
            clean = pd.Series([0.0], dtype=float)
        counts, bin_edges = np.histogram(clean, bins=bins)
        return HistogramData(bins=bin_edges.tolist(), counts=counts.tolist())

    def _build_holding_period_histogram(self, series: pd.Series) -> HistogramData:
        clean = pd.to_numeric(series, errors="coerce")
        clean = clean.replace([np.inf, -np.inf], np.nan).dropna()
        if clean.empty:
            clean = pd.Series([1.0], dtype=float)

        clipped = clean.clip(lower=1.0, upper=365.0)
        bin_edges = [1.0, 7.0, 30.0, 90.0, 180.0, 365.0]
        counts, _ = np.histogram(clipped, bins=bin_edges)
        return HistogramData(bins=bin_edges, counts=counts.tolist())

    def _build_trade_frequency_series(self, closed_trades: pd.DataFrame, dates: pd.Index) -> TimeSeriesData:
        if not closed_trades.empty:
            series = build_trade_frequency_series_from_closed_trades(closed_trades)
            if series["dates"]:
                return TimeSeriesData(
                    dates=[str(label) for label in series["dates"]],
                    values=[float(value) for value in series["values"]],
                )

        if len(dates) == 0:
            return TimeSeriesData(dates=[], values=[])

        labels = sorted({pd.Timestamp(value).to_period("M").to_timestamp().strftime("%Y-%m-%d") for value in dates})
        return TimeSeriesData(dates=labels, values=[0.0 for _ in labels])

    def _coerce_histogram(self, raw) -> HistogramData:
        if isinstance(raw, HistogramData):
            return raw
        if isinstance(raw, dict):
            return HistogramData(
                bins=[float(value) for value in (raw.get("bins") or [])],
                counts=[int(value) for value in (raw.get("counts") or [])],
            )
        return HistogramData(bins=[], counts=[])

    def _coerce_time_series(self, raw) -> TimeSeriesData:
        if isinstance(raw, TimeSeriesData):
            return raw
        if isinstance(raw, dict):
            return TimeSeriesData(
                dates=[str(value) for value in (raw.get("dates") or [])],
                values=[float(value) for value in (raw.get("values") or [])],
            )
        return TimeSeriesData(dates=[], values=[])

    def _seed_from_backtest(self, backtest_id: str) -> int:
        return abs(hash(backtest_id)) % (2**32)
