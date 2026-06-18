"""
Persist simulation account fund overview snapshots into PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.services.trade.redis_client import RedisClient
from backend.services.trade.simulation.models.fund_snapshot import (
    SimulationFundSnapshot,
)
from backend.services.trade.simulation.models.account_daily import (
    SimulationAccountDaily,
)
from backend.services.trade.simulation.services.daily_snapshot_service import (
    SimulationDailySnapshotService,
)
from backend.services.trade.simulation.services.projection_service import (
    SimulationProjectionService,
)
from backend.shared.database_manager_v2 import get_session
from backend.shared.trade_redis_keys import normalize_trade_user_id
from backend.shared.trade_account_cache import write_trade_account_cache

logger = logging.getLogger(__name__)


def _to_decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except Exception:
        return default


def _local_today() -> datetime.date:
    # Keep simple and deterministic; can be overridden by TZ env var.
    tz_name = os.getenv("SIM_FUND_SNAPSHOT_TZ", "Asia/Shanghai")
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return datetime.now().date()


async def _fetch_latest_price(symbol: str, market_url: str) -> float:
    """从行情服务获取最新价，失败时返回 0.0。"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{market_url}/api/v1/quotes/{symbol}")
            if resp.status_code == 200:
                data = resp.json()
                px = float(data.get("current_price") or data.get("last_price") or 0)
                if px > 0:
                    return px
    except Exception as exc:
        logger.debug("Snapshot price fetch failed for %s: %s", symbol, exc)
    return 0.0


async def _recalculate_account_market_value(account: dict) -> dict:
    """
    用最新行情重算持仓市值，更新 account 的 market_value 和 total_asset。
    只处理多头仓位（long）；空头仓位的 market_value 来自 short_market_value 字段。
    """
    market_url = os.getenv("MARKET_DATA_SERVICE_URL", "http://quantmind-stream:8003").rstrip("/")
    positions = dict(account.get("positions") or {})
    if not positions:
        return account

    new_market_value = 0.0
    for sym, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        volume = float(pos.get("volume") or 0.0)
        if volume <= 0:
            continue
        # 只获取非空头仓位的市价（空头仓位用 side 标记）
        side = str(pos.get("side") or "long").lower()
        if side == "short":
            # 空头市值已在 short_market_value 单独跟踪，此处跳过
            mv = float(pos.get("market_value") or 0.0)
            new_market_value -= mv  # 空头负贡献
            continue
        px = await _fetch_latest_price(sym, market_url)
        if px > 0:
            mv = volume * px
            pos["price"] = px
            pos["market_value"] = mv
        else:
            mv = float(pos.get("market_value") or 0.0)
        new_market_value += mv

    cash = float(account.get("cash") or 0.0)
    short_proceeds = float(account.get("short_proceeds") or 0.0)
    account["positions"] = positions
    account["market_value"] = round(new_market_value, 4)
    account["total_asset"] = round(cash + short_proceeds + new_market_value, 4)
    return account


def _parse_account_key(key: str) -> tuple[str, str, str] | None:
    # simulation:account:{tenant_id}:{user_id}
    parts = key.split(":")
    if len(parts) != 4:
        return None
    if parts[0] != "simulation" or parts[1] != "account":
        return None
    tenant_id = parts[2].strip() or "default"
    raw_user_id = parts[3].strip()
    if not raw_user_id:
        return None
    user_id = normalize_trade_user_id(raw_user_id) or raw_user_id
    return tenant_id, user_id, raw_user_id


def _score_account_payload(account: dict[str, object]) -> tuple[int, float, float]:
    positions = account.get("positions")
    valid_positions = 0
    if isinstance(positions, dict):
        for pos in positions.values():
            if not isinstance(pos, dict):
                continue
            volume = float(pos.get("volume") or 0.0)
            if volume > 0:
                valid_positions += 1
    market_value = abs(float(account.get("market_value") or 0.0))
    total_asset = abs(float(account.get("total_asset") or 0.0))
    return valid_positions, market_value, total_asset


@dataclass
class SnapshotUpsertResult:
    upserted_rows: int
    scanned_accounts: int


class SimulationFundSnapshotService:
    @staticmethod
    def _read_settings_initial_cash(
        redis: RedisClient,
        tenant_id: str,
        user_id: str,
        raw_user_id: str | None = None,
    ) -> Decimal:
        if not redis.client:
            return Decimal("0")
        keys = [f"simulation:settings:{tenant_id}:{user_id}"]
        if raw_user_id and raw_user_id != user_id:
            keys.append(f"simulation:settings:{tenant_id}:{raw_user_id}")
        for settings_key in tuple(dict.fromkeys(keys)):
            raw = redis.client.get(settings_key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            return _to_decimal(data.get("initial_cash"), Decimal("0"))
        return Decimal("0")

    @classmethod
    def _build_row(
        cls,
        tenant_id: str,
        user_id: str,
        account: dict[str, object],
        prev_total_asset: Decimal | None = None,
    ) -> dict[str, object]:
        total_asset = _to_decimal(account.get("total_asset"))
        available_balance = _to_decimal(account.get("cash") or account.get("available_balance"))
        frozen_balance = _to_decimal(account.get("frozen_balance"))
        market_value = _to_decimal(account.get("market_value"))
        initial_capital = _to_decimal(account.get("initial_capital"))
        # total_pnl = total_asset - initial_capital
        if initial_capital == 0:
            initial_capital = total_asset
        total_pnl = total_asset - initial_capital
        # today_pnl = total_asset - yesterday's total_asset (if available)
        if prev_total_asset is not None and prev_total_asset > 0:
            today_pnl = total_asset - prev_total_asset
        else:
            today_pnl = _to_decimal(account.get("today_pnl"))

        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "snapshot_date": _local_today(),
            "total_asset": total_asset,
            "available_balance": available_balance,
            "frozen_balance": frozen_balance,
            "market_value": market_value,
            "initial_capital": initial_capital,
            "total_pnl": total_pnl,
            "today_pnl": today_pnl,
            "source": "redis_simulation_account",
        }

    @classmethod
    async def capture_all(cls, redis: RedisClient) -> SnapshotUpsertResult:
        if not redis.client:
            return SnapshotUpsertResult(upserted_rows=0, scanned_accounts=0)

        keys = list(redis.client.scan_iter(match="simulation:account:*", count=500))
        rows: list[dict[str, object]] = []
        daily_payloads: dict[tuple[str, str], tuple[str, dict[str, object], dict[str, dict[str, float]]]] = {}
        deduped_accounts: dict[
            tuple[str, str],
            tuple[str, str, dict[str, object]],
        ] = {}
        for key in keys:
            parsed = _parse_account_key(str(key))
            if not parsed:
                continue
            tenant_id, user_id, raw_user_id = parsed
            raw = redis.client.get(key)
            if not raw:
                continue
            try:
                account = json.loads(raw)
            except Exception:
                continue
            if not isinstance(account, dict):
                continue

            dedupe_key = (tenant_id, user_id)
            existing = deduped_accounts.get(dedupe_key)
            if existing is None:
                deduped_accounts[dedupe_key] = (str(key), raw_user_id, account)
            else:
                _, _, existing_account = existing
                if _score_account_payload(account) > _score_account_payload(existing_account):
                    deduped_accounts[dedupe_key] = (str(key), raw_user_id, account)

        for (tenant_id, user_id), (source_key, raw_user_id, account) in deduped_accounts.items():
            canonical_key = f"simulation:account:{tenant_id}:{user_id}"
            if source_key != canonical_key:
                redis.client.set(canonical_key, json.dumps(account, ensure_ascii=False))
            for legacy_key in (
                f"simulation:account:{tenant_id}:{raw_user_id}",
                source_key,
            ):
                if legacy_key != canonical_key:
                    redis.client.delete(legacy_key)

            # 用最新行情重算市值（避免快照时价格陈旧）
            try:
                account = await _recalculate_account_market_value(account)
            except Exception as exc:
                logger.warning("Market value recalc failed for %s/%s: %s", tenant_id, user_id, exc)
            else:
                # 实时重算后立即回写 simulation 账户与交易账户缓存，供前端/交易链路统一消费。
                try:
                    redis.client.set(canonical_key, json.dumps(account, ensure_ascii=False))
                    write_trade_account_cache(redis, tenant_id, user_id, dict(account))
                except Exception as exc:
                    logger.warning("Simulation account cache writeback failed for %s/%s: %s", tenant_id, user_id, exc)

            # 查询昨日快照 total_asset 用于计算 today_pnl
            prev_total_asset: Decimal | None = None
            try:
                from datetime import date, timedelta
                yesterday = _local_today() - timedelta(days=1)
                async with get_session(read_only=True) as s:
                    q = await s.execute(
                        select(SimulationFundSnapshot.total_asset).where(
                            SimulationFundSnapshot.tenant_id == tenant_id,
                            SimulationFundSnapshot.user_id == user_id,
                            SimulationFundSnapshot.snapshot_date == yesterday,
                        )
                    )
                    prev_row = q.scalar_one_or_none()
                    if prev_row is not None:
                        prev_total_asset = _to_decimal(prev_row)
            except Exception as exc:
                logger.debug("Could not fetch yesterday snapshot for %s/%s: %s", tenant_id, user_id, exc)

            row = cls._build_row(tenant_id, user_id, account, prev_total_asset=prev_total_asset)
            if row["initial_capital"] == 0:
                row["initial_capital"] = cls._read_settings_initial_cash(
                    redis,
                    tenant_id,
                    user_id,
                    raw_user_id=raw_user_id,
                )
                if row["initial_capital"] == 0:
                    row["initial_capital"] = row["total_asset"]
                    row["total_pnl"] = Decimal("0")
                else:
                    row["total_pnl"] = row["total_asset"] - row["initial_capital"]
            rows.append(row)

            try:
                async with get_session(read_only=True) as projection_session:
                    projection = await SimulationProjectionService(
                        projection_session
                    ).load_projection(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        latest_price_loader=lambda symbol: _fetch_latest_price(symbol, market_url=os.getenv("MARKET_DATA_SERVICE_URL", "http://quantmind-stream:8003").rstrip("/")),
                    )
                projection_positions = projection.positions or {}
            except Exception as exc:
                logger.debug(
                    "Projection snapshot fallback to redis positions for %s/%s: %s",
                    tenant_id,
                    user_id,
                    exc,
                )
                projection_positions = {}

            account_id = SimulationProjectionService.build_account_id(tenant_id, user_id)
            combined_account = dict(account)
            combined_account.setdefault("initial_capital", float(row["initial_capital"] or 0.0))
            combined_account.setdefault("total_pnl", float(row["total_pnl"] or 0.0))
            combined_account.setdefault("today_pnl", float(row["today_pnl"] or 0.0))
            daily_payloads[(tenant_id, user_id)] = (
                account_id,
                combined_account,
                projection_positions or dict(account.get("positions") or {}),
            )

        if not rows:
            return SnapshotUpsertResult(upserted_rows=0, scanned_accounts=len(keys))

        async with get_session(read_only=False) as session:
            daily_snapshot_service = SimulationDailySnapshotService(session)
            for row in rows:
                stmt = (
                    pg_insert(SimulationFundSnapshot)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=["tenant_id", "user_id", "snapshot_date"],
                        set_={
                            "total_asset": row["total_asset"],
                            "available_balance": row["available_balance"],
                            "frozen_balance": row["frozen_balance"],
                            "market_value": row["market_value"],
                            "initial_capital": row["initial_capital"],
                            "total_pnl": row["total_pnl"],
                            "today_pnl": row["today_pnl"],
                            "source": row["source"],
                            "updated_at": datetime.now(),
                        },
                    )
                )
                await session.execute(stmt)
                payload = daily_payloads.get((str(row["tenant_id"]), str(row["user_id"])))
                if payload:
                    account_id, account_payload, positions_payload = payload
                    await daily_snapshot_service.replace_daily_snapshot(
                        tenant_id=str(row["tenant_id"]),
                        user_id=str(row["user_id"]),
                        account_id=account_id,
                        snapshot_date=row["snapshot_date"],
                        account_payload=account_payload,
                        positions=positions_payload,
                    )

        return SnapshotUpsertResult(upserted_rows=len(rows), scanned_accounts=len(keys))

    @staticmethod
    async def list_user_daily(
        tenant_id: str,
        user_id: str,
        days: int = 30,
    ) -> list[SimulationFundSnapshot]:
        normalized_user_id = normalize_trade_user_id(user_id) or str(user_id)
        async with get_session(read_only=True) as session:
            stmt = (
                select(SimulationFundSnapshot)
                .where(
                    SimulationFundSnapshot.tenant_id == tenant_id,
                    SimulationFundSnapshot.user_id == normalized_user_id,
                )
                .order_by(SimulationFundSnapshot.snapshot_date.desc())
                .limit(max(1, min(days, 3650)))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def list_user_daily_v2(
        tenant_id: str,
        user_id: str,
        days: int = 30,
    ) -> list[SimulationAccountDaily]:
        normalized_user_id = normalize_trade_user_id(user_id) or str(user_id)
        async with get_session(read_only=True) as session:
            stmt = (
                select(SimulationAccountDaily)
                .where(
                    SimulationAccountDaily.tenant_id == tenant_id,
                    SimulationAccountDaily.user_id == normalized_user_id,
                )
                .order_by(SimulationAccountDaily.snapshot_date.desc())
                .limit(max(1, min(days, 3650)))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())


class SimulationFundSnapshotWorker:
    def __init__(self, redis: RedisClient, interval_seconds: int):
        self.redis = redis
        self.interval_seconds = max(5, int(interval_seconds))
        self._stopped = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name="sim-fund-snapshot-worker")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                result = await SimulationFundSnapshotService.capture_all(self.redis)
                if result.scanned_accounts > 0:
                    logger.info(
                        "Simulation fund snapshot upserted: %s/%s",
                        result.upserted_rows,
                        result.scanned_accounts,
                    )
            except Exception as exc:
                logger.error("Simulation fund snapshot worker failed: %s", exc, exc_info=True)

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue
