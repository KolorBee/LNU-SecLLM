import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class FundamentalAligner:
    """
    统一基本面对齐器 (Unified Fundamental Aligner)

    从统一的 Parquet 文件读取预计算基本面特征，确保回测与实盘执行口径一致。
    """

    DEFAULT_PATH = "db/custom/fundamental_aligned.parquet"

    def __init__(self, parquet_path: str | None = None):
        self.parquet_path = parquet_path or os.getenv(
            "FUNDAMENTAL_ALIGN_PATH", self.DEFAULT_PATH
        )
        self._data: pd.DataFrame | None = None
        self._project_root = self._find_project_root()

        if os.path.isabs(self.parquet_path):
            self.full_path = Path(self.parquet_path)
        else:
            self.full_path = self._project_root / self.parquet_path

    def _find_project_root(self) -> Path:
        curr = Path(__file__).resolve().parent
        for _ in range(10):
            if (curr / "requirements.txt").exists() or (curr / "AGENTS.md").exists():
                return curr
            if curr.parent == curr:
                break
            curr = curr.parent
        return Path(os.getcwd())

    def _load_data(self) -> pd.DataFrame:
        if self._data is not None:
            return self._data

        if not self.full_path.exists():
            logger.warning("FundamentalAligner: 找不到对齐文件 %s", self.full_path)
            self._data = pd.DataFrame()
            return self._data

        try:
            df = pd.read_parquet(self.full_path)
            if df.empty:
                self._data = pd.DataFrame()
                return self._data

            df["trade_date"] = pd.to_datetime(df["trade_date"])

            if os.getenv("MODE") == "production":
                last_date = df["trade_date"].max()
                days_diff = (pd.Timestamp.now().normalize() - last_date.normalize()).days
                if days_diff > 2:
                    logger.error(
                        "CRITICAL: 基本面对齐数据已过期，最后日期=%s，滞后=%s天",
                        last_date.date(),
                        days_diff,
                    )

            self._data = df.set_index(["trade_date", "symbol"]).sort_index()
            logger.info("FundamentalAligner: 成功加载数据，字段数=%s", len(df.columns))
        except Exception as exc:
            logger.error("FundamentalAligner: 加载失败: %s", exc)
            self._data = pd.DataFrame()
        return self._data

    def filter_instruments(
        self,
        current_date: Any,
        instruments: list[str],
        constraints: dict[str, Any] | None = None,
    ) -> list[str]:
        data = self._load_data()
        if data.empty:
            return instruments

        # 使用上一个交易日的数据，因为调仓时刻当天的基本面数据还未计算
        dt = pd.to_datetime(current_date).normalize()
        # 从缓存数据中找上一个交易日
        available_dates = data.index.get_level_values("trade_date").unique().sort_values()
        # 找到小于当前日期的最后一个交易日
        prev_dates = available_dates[available_dates < dt]
        if len(prev_dates) == 0:
            logger.warning("FundamentalAligner: 找不到 %s 之前的交易日数据", dt.date())
            return instruments
        prev_dt = prev_dates[-1]

        try:
            snapshot = data.loc[prev_dt]
        except KeyError:
            return instruments

        if not constraints:
            return instruments

        mask = pd.Series(True, index=snapshot.index)
        for key, target_val in constraints.items():
            if target_val is None:
                continue

            col = key
            op = "eq"
            if key.endswith("_max"):
                col, op = key[:-4], "le"
            elif key.endswith("_min"):
                col, op = key[:-4], "ge"
            elif key.endswith("_in"):
                col, op = key[:-3], "in"
            elif key.endswith("_not"):
                col, op = key[:-4], "ne"

            if col not in snapshot.columns:
                logger.debug("FundamentalAligner: 字段 %s 不存在，跳过", col)
                continue

            col_data = snapshot[col]

            # 鲁棒性检查：如果字段数据全部为空，或全部为 0 (代表未对齐/未初始化数据)，跳过过滤
            if col_data.dropna().empty:
                logger.warning(f"FundamentalAligner: 字段 {col} 全为空/NaN，跳过过滤。")
                continue

            import pandas.api.types as ptypes
            if ptypes.is_numeric_dtype(col_data) and (col_data == 0).all():
                logger.warning(f"FundamentalAligner: 字段 {col} 全为 0 (未对齐/未初始化)，跳过过滤。")
                continue
            if op == "le":
                mask &= col_data <= float(target_val)
            elif op == "ge":
                mask &= col_data >= float(target_val)
            elif op == "ne":
                mask &= col_data != target_val
            elif op == "in":
                if isinstance(target_val, (list, set, tuple)):
                    mask &= col_data.isin(target_val)
                else:
                    mask &= col_data == target_val
            else:
                mask &= col_data == target_val

        valid_symbols = set(snapshot[mask].index)
        # 统一大小写：将 valid_symbols 转为大写格式，与信号股票代码格式一致
        valid_symbols_upper = {s.upper() for s in valid_symbols}
        return [symbol for symbol in instruments if symbol.upper() in valid_symbols_upper]

    def get_snapshot(self, current_date: Any) -> pd.DataFrame:
        """
        返回指定交易日的基本面对齐截面。

        主要用于策略侧做行业集中度、流动性阈值和大盘状态等日内/盘后风控判断。
        注意：实际返回的是上一个交易日的数据，因为调仓时刻当天的数据还未计算。
        """
        data = self._load_data()
        if data.empty:
            return pd.DataFrame()

        # 使用上一个交易日的数据
        dt = pd.to_datetime(current_date).normalize()
        available_dates = data.index.get_level_values("trade_date").unique().sort_values()
        prev_dates = available_dates[available_dates < dt]
        if len(prev_dates) == 0:
            return pd.DataFrame()
        prev_dt = prev_dates[-1]

        try:
            snapshot = data.loc[prev_dt]
        except KeyError:
            return pd.DataFrame()

        if isinstance(snapshot, pd.Series):
            snapshot = snapshot.to_frame().T
        return snapshot.copy()


fundamental_aligner = FundamentalAligner()


