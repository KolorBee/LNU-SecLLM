"""KLine service"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from redis.asyncio import Redis
from sqlalchemy import and_, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..market_config import settings
from ..models import KLine
from ..schemas import KLineCreate, KLineResponse
from backend.shared.market_db_manager import get_market_session
from backend.shared.stock_utils import StockCodeUtil

logger = logging.getLogger(__name__)


class KLineService:
    """K线数据服务"""

    def __init__(self, db: AsyncSession, redis: Redis | None = None):
        self.db = db
        self.redis = redis

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        use_cache: bool = True,
    ) -> list[KLineResponse]:
        """获取K线数据 - 优先从远程 stock_daily_latest 读取"""

        if use_cache and self.redis:
            cached = await self._get_cached_klines(symbol, interval, limit)
            if cached:
                logger.debug(f"KLine cache hit for {symbol} {interval}")
                return cached

        if interval == "1d":
            klines = await self._fetch_from_stock_daily_latest(symbol, limit)
            if klines:
                if self.redis:
                    await self._cache_klines(symbol, interval, klines)
                return klines

        klines = await self.list_klines(symbol, interval, start_time, end_time, limit)
        if klines:
            return klines

        return []

    async def _fetch_from_stock_daily_latest(
        self, symbol: str, limit: int = 60
    ) -> list[KLineResponse]:
        """从远程 stock_daily_latest 表读取日线数据"""
        normalized = StockCodeUtil.to_prefix(symbol).lower()

        try:
            async with get_market_session() as session:
                stmt = text(
                    """
                    SELECT
                        symbol,
                        trade_date,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        amount,
                        pct_change,
                        turnover_rate
                    FROM stock_daily_latest
                    WHERE symbol = :symbol
                    ORDER BY trade_date DESC
                    LIMIT :limit
                    """
                )
                result = await session.execute(stmt, {"symbol": normalized, "limit": limit})
                rows = result.mappings().all()

                if not rows:
                    logger.debug(f"No data in stock_daily_latest for {normalized}")
                    return []

                klines = []
                for row in rows:
                    klines.append(
                        KLineResponse(
                            symbol=symbol,
                            interval="1d",
                            timestamp=datetime.combine(
                                row["trade_date"], datetime.min.time()
                            ),
                            open_price=float(row["open"] or 0),
                            high_price=float(row["high"] or 0),
                            low_price=float(row["low"] or 0),
                            close_price=float(row["close"] or 0),
                            volume=int(row["volume"] or 0),
                            amount=float(row["amount"] or 0),
                            change=None,
                            change_percent=float(row["pct_change"])
                            if row["pct_change"]
                            else None,
                            turnover_rate=float(row["turnover_rate"])
                            if row["turnover_rate"]
                            else None,
                        )
                    )

                logger.info(
                    f"Fetched {len(klines)} klines from stock_daily_latest for {normalized}"
                )
                return klines

        except Exception as e:
            logger.error(f"Failed to fetch from stock_daily_latest: {e}")
            return []

    async def create_kline(self, kline: KLineCreate) -> KLineResponse:
        """创建K线记录"""
        db_kline = KLine(**kline.model_dump())
        self.db.add(db_kline)
        await self.db.commit()
        await self.db.refresh(db_kline)
        return KLineResponse.model_validate(db_kline)

    async def list_klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KLineResponse]:
        """查询K线历史"""
        query = select(KLine).filter(and_(KLine.symbol == symbol, KLine.interval == interval))

        if start_time:
            query = query.filter(KLine.timestamp >= start_time)
        if end_time:
            query = query.filter(KLine.timestamp <= end_time)

        query = query.order_by(desc(KLine.timestamp)).limit(limit).offset(offset)

        result = await self.db.execute(query)
        klines = result.scalars().all()

        return [KLineResponse.model_validate(k) for k in klines]

    async def get_latest_kline(self, symbol: str, interval: str) -> KLineResponse | None:
        """获取最新K线"""
        query = (
            select(KLine)
            .filter(and_(KLine.symbol == symbol, KLine.interval == interval))
            .order_by(desc(KLine.timestamp))
            .limit(1)
        )

        result = await self.db.execute(query)
        kline = result.scalar_one_or_none()

        return KLineResponse.model_validate(kline) if kline else None

    async def _get_cached_klines(
        self, symbol: str, interval: str, limit: int
    ) -> list[KLineResponse] | None:
        """从缓存获取K线"""
        if not self.redis:
            return None

        try:
            cache_key = f"kline:{symbol}:{interval}:{limit}"
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                data_list = json.loads(cached_data)
                return [KLineResponse(**item) for item in data_list]
        except Exception as e:
            logger.error(f"Error getting cached klines: {e}")

        return None

    async def _cache_klines(
        self, symbol: str, interval: str, klines: list[KLineResponse]
    ) -> None:
        """缓存K线数据"""
        if not self.redis:
            return

        try:
            cache_key = f"kline:{symbol}:{interval}:{len(klines)}"
            cache_data = json.dumps([k.model_dump() for k in klines], default=str)
            await self.redis.setex(cache_key, settings.CACHE_TTL_KLINE, cache_data)
        except Exception as e:
            logger.error(f"Error caching klines: {e}")
