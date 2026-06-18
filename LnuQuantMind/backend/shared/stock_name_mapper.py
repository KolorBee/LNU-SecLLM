"""
股票名称映射服务 - 从 stocks_index.json 加载股票代码与名称映射
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 默认路径
DEFAULT_STOCKS_INDEX_PATH = Path("/app/data/stocks/stocks_index.json")
_FALLBACK_PATHS = [
    Path("/app/data/stocks/stocks_index.json"),
    Path("/workspace/data/stocks/stocks_index.json"),
    Path(__file__).parent.parent.parent.parent / "data" / "stocks" / "stocks_index.json",
]


class StockNameMapper:
    """股票代码到名称的映射器"""

    _instance: Optional["StockNameMapper"] = None
    _initialized: bool = False

    def __new__(cls) -> "StockNameMapper":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._mapping: dict[str, str] = {}
        self._load_mapping()
        StockNameMapper._initialized = True

    def _load_mapping(self) -> None:
        """加载股票代码名称映射"""
        for path in _FALLBACK_PATHS:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items = data.get("items", [])
                    for item in items:
                        symbol = item.get("symbol", "")
                        name = item.get("name", "")
                        if symbol and name:
                            self._mapping[symbol] = name
                    logger.info(
                        "Loaded %d stock name mappings from %s",
                        len(self._mapping),
                        path,
                    )
                    return
                except Exception as e:
                    logger.warning("Failed to load stock names from %s: %s", path, e)
                    continue

        logger.warning(
            "No stocks_index.json found, stock name mapping will be empty. "
            "Checked paths: %s",
            [str(p) for p in _FALLBACK_PATHS],
        )

    def get_name(self, symbol: str) -> str:
        """获取股票名称，未找到时返回原代码"""
        if not symbol:
            return symbol
        return self._mapping.get(symbol, symbol)

    def enrich_with_name(self, data: dict | list, symbol_key: str = "symbol") -> dict | list:
        """
        为数据添加 name 字段

        Args:
            data: 单个字典或字典列表
            symbol_key: 股票代码的键名

        Returns:
            添加了 name 字段的数据
        """
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and symbol_key in item:
                    item["name"] = self.get_name(item[symbol_key])
            return data
        elif isinstance(data, dict) and symbol_key in data:
            data["name"] = self.get_name(data[symbol_key])
            return data
        return data

    def refresh(self) -> None:
        """重新加载映射"""
        self._mapping.clear()
        self._load_mapping()


# 全局单例
_mapper: Optional[StockNameMapper] = None


def get_stock_name_mapper() -> StockNameMapper:
    """获取股票名称映射器单例"""
    global _mapper
    if _mapper is None:
        _mapper = StockNameMapper()
    return _mapper


def get_stock_name(symbol: str) -> str:
    """便捷函数：获取股票名称"""
    return get_stock_name_mapper().get_name(symbol)
