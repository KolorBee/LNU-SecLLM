"""
Simulation Account Manager - Manage paper trading accounts in Redis
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.trade.redis_client import RedisClient
from backend.services.trade.trade_config import settings
from backend.shared.trade_redis_keys import normalize_trade_user_id
from backend.shared.trade_account_cache import write_json_cache

logger = logging.getLogger(__name__)


class SimulationAccountManager:
    """
    Manage simulation accounts state in Redis.
    Key: simulation:account:{tenant_id}:{user_id}
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self._update_balance_lua = """
local key = KEYS[1]
local symbol = ARGV[1]
local delta_cash = tonumber(ARGV[2])
local delta_volume = tonumber(ARGV[3])
local price = tonumber(ARGV[4])

local raw = redis.call("GET", key)
if not raw then
    return cjson.encode({success=false, reason="ACCOUNT_NOT_FOUND"})
end

local account = cjson.decode(raw)
local cash = tonumber(account.cash or 0)
local positions = account.positions or {}

local pos = positions[symbol]
if not pos then
    pos = {volume=0, cost=0, market_value=0, price=0}
end

local old_volume = tonumber(pos.volume or 0)
local new_cash = cash + delta_cash
local new_volume = old_volume + delta_volume

if new_cash < -0.000001 then
    return cjson.encode({success=false, reason="INSUFFICIENT_CASH"})
end

if new_volume < -0.000001 then
    return cjson.encode({success=false, reason="INSUFFICIENT_HOLDINGS"})
end

if delta_volume > 0 then
    local current_cost_total = tonumber(pos.cost or 0) * old_volume
    if new_volume > 0 then
        pos.cost = (current_cost_total + (delta_volume * price)) / new_volume
    else
        pos.cost = 0
    end
end

pos.volume = new_volume
pos.price = price
pos.market_value = new_volume * price

if new_volume <= 0.0001 then
    positions[symbol] = nil
else
    positions[symbol] = pos
end

local total_market_value = 0
for _, p in pairs(positions) do
    total_market_value = total_market_value + (tonumber(p.volume or 0) * tonumber(p.price or 0))
end

account.cash = new_cash
account.positions = positions
account.market_value = total_market_value
account.total_asset = new_cash + total_market_value

redis.call("SET", key, cjson.encode(account))
return cjson.encode({success=true})
"""
        self._update_balance_margin_lua = """
local key = KEYS[1]
local pos_key = ARGV[1]
local price = tonumber(ARGV[2])
local action = string.lower(tostring(ARGV[3] or ""))
local quantity = tonumber(ARGV[4])
local borrow_rate_daily = tonumber(ARGV[5])
local closeout_ratio = tonumber(ARGV[6])
local warning_ratio = tonumber(ARGV[7])
local snapshot_at = tostring(ARGV[8] or "")

local raw = redis.call("GET", key)
if not raw then
    return cjson.encode({success=false, reason="ACCOUNT_NOT_FOUND"})
end

local account = cjson.decode(raw)
local positions = account.positions or {}
local cash = tonumber(account.cash or 0)
local liabilities = tonumber(account.liabilities or 0)
local short_proceeds = tonumber(account.short_proceeds or 0)
local account_version = tonumber(account.account_version or 0)
local pos = positions[pos_key]
if not pos then
    pos = {volume=0, cost=0, market_value=0, price=0, side="short", borrow_fee=0}
end

local old_qty = tonumber(pos.volume or 0)
local gross = quantity * price
local borrow_fee = gross * borrow_rate_daily

if action == "sell_to_open" then
    local new_qty = old_qty + quantity
    local total_cost = (tonumber(pos.cost or 0) * old_qty) + gross
    pos.volume = new_qty
    pos.cost = new_qty > 0 and (total_cost / new_qty) or 0
    pos.price = price
    pos.market_value = new_qty * price
    pos.side = "short"
    pos.borrow_fee = tonumber(pos.borrow_fee or 0) + borrow_fee
    positions[pos_key] = pos

    short_proceeds = short_proceeds + gross
    cash = cash - borrow_fee
    liabilities = liabilities + gross
elseif action == "buy_to_close" then
    if old_qty + 0.000001 < quantity then
        return cjson.encode({success=false, reason="INSUFFICIENT_SHORT_POSITION"})
    end

    local avg_cost = tonumber(pos.cost or 0)
    local short_entry_val = avg_cost * quantity
    local realized = short_entry_val - gross - borrow_fee

    cash = cash + realized
    short_proceeds = math.max(0, short_proceeds - short_entry_val)
    liabilities = math.max(0, liabilities - short_entry_val)

    local new_qty = old_qty - quantity
    if new_qty <= 0.000001 then
        positions[pos_key] = nil
    else
        pos.volume = new_qty
        pos.price = price
        pos.market_value = new_qty * price
        pos.side = "short"
        pos.borrow_fee = tonumber(pos.borrow_fee or 0) + borrow_fee
        pos.realized_pnl = tonumber(pos.realized_pnl or 0) + realized
        positions[pos_key] = pos
    end
else
    return cjson.encode({success=false, reason="UNSUPPORTED_TRADE_ACTION:" .. action})
end

local total_market_value = 0
local long_market_value = 0
local short_market_value = 0
for _, position in pairs(positions) do
    local qty = tonumber(position.volume or 0)
    local px = tonumber(position.price or 0)
    local side = string.lower(tostring(position.side or "long"))
    local mv = qty * px
    if side == "short" then
        total_market_value = total_market_value - mv
        short_market_value = short_market_value + mv
    else
        total_market_value = total_market_value + mv
        long_market_value = long_market_value + mv
    end
end

local equity = cash + short_proceeds + total_market_value
local maintenance_ratio = 0
local warning_level = "normal"
if liabilities > 0 then
    maintenance_ratio = equity / liabilities
    if maintenance_ratio <= closeout_ratio then
        warning_level = "closeout"
    elseif maintenance_ratio <= warning_ratio then
        warning_level = "warning"
    end
end

account.cash = cash
account.available_cash = cash
account.frozen_cash = short_proceeds
account.short_proceeds = short_proceeds
account.positions = positions
account.market_value = total_market_value
account.long_market_value = long_market_value
account.short_market_value = short_market_value
account.liabilities = liabilities
account.maintenance_margin_ratio = maintenance_ratio
account.warning_level = warning_level
account.total_asset = equity
account.equity = equity
account.account_version = account_version + 1
if snapshot_at ~= "" then
    account.snapshot_at = snapshot_at
    account.rebuilt_at = snapshot_at
end
account.rebuild_source = "simulation_margin_update"

redis.call("SET", key, cjson.encode(account))
return cjson.encode({success=true, reason="OK", account=account})
"""

    @staticmethod
    def _normalize_tenant(tenant_id: str | None) -> str:
        return (tenant_id or "").strip() or "default"

    @staticmethod
    def _normalize_user_id(user_id: str | int | None) -> str:
        normalized = normalize_trade_user_id(user_id)
        if normalized:
            return normalized
        return str(user_id or "").strip()

    def _get_key(self, user_id: str | int, tenant_id: str) -> str:
        return f"simulation:account:{tenant_id}:{self._normalize_user_id(user_id)}"

    def _get_settings_key(self, user_id: str | int, tenant_id: str) -> str:
        return f"simulation:settings:{tenant_id}:{self._normalize_user_id(user_id)}"

    def _account_key_candidates(self, user_id: str | int, tenant_id: str) -> tuple[str, ...]:
        normalized = self._normalize_user_id(user_id)
        raw = str(user_id or "").strip()
        keys = [f"simulation:account:{tenant_id}:{normalized}"]
        if raw and raw != normalized:
            keys.append(f"simulation:account:{tenant_id}:{raw}")
        if raw.isdigit():
            compact = str(int(raw))
            if compact and compact != normalized and compact != raw:
                keys.append(f"simulation:account:{tenant_id}:{compact}")
        return tuple(dict.fromkeys(keys))

    def _settings_key_candidates(self, user_id: str | int, tenant_id: str) -> tuple[str, ...]:
        normalized = self._normalize_user_id(user_id)
        raw = str(user_id or "").strip()
        keys = [f"simulation:settings:{tenant_id}:{normalized}"]
        if raw and raw != normalized:
            keys.append(f"simulation:settings:{tenant_id}:{raw}")
        if raw.isdigit():
            compact = str(int(raw))
            if compact and compact != normalized and compact != raw:
                keys.append(f"simulation:settings:{tenant_id}:{compact}")
        return tuple(dict.fromkeys(keys))

    @staticmethod
    def _payload_score(payload: dict[str, Any]) -> tuple[int, float, float]:
        positions = payload.get("positions")
        valid_positions = 0
        if isinstance(positions, dict):
            for pos in positions.values():
                if not isinstance(pos, dict):
                    continue
                volume = float(pos.get("volume") or 0.0)
                if volume > 0:
                    valid_positions += 1
        market_value = abs(float(payload.get("market_value") or 0.0))
        total_asset = abs(float(payload.get("total_asset") or 0.0))
        return valid_positions, market_value, total_asset

    @staticmethod
    def _parse_iso(raw: Any) -> datetime | None:
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    def _settings_score(self, payload: dict[str, Any]) -> tuple[int, float]:
        timestamp = self._parse_iso(payload.get("last_modified_at"))
        if timestamp is None:
            return 0, float("-inf")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return 1, timestamp.timestamp()

    def _load_candidate_payloads(self, candidates: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        if not self.redis.client:
            return {}
        payloads: dict[str, dict[str, Any]] = {}
        for key in candidates:
            raw = self.redis.client.get(key)
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, dict):
                payloads[key] = parsed
        return payloads

    def _reconcile_account_cache(
        self,
        *,
        user_id: str | int,
        tenant_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        normalized_key = self._get_key(user_id, tenant_id)
        payloads = self._load_candidate_payloads(self._account_key_candidates(user_id, tenant_id))
        if not payloads:
            return normalized_key, None

        preferred_key, preferred_payload = max(
            payloads.items(),
            key=lambda item: self._payload_score(item[1]),
        )
        if preferred_key != normalized_key:
            write_json_cache(self.redis, normalized_key, preferred_payload)
        for key in payloads:
            if key != normalized_key:
                self.redis.client.delete(key)
        return normalized_key, preferred_payload

    def _reconcile_settings_cache(
        self,
        *,
        user_id: str | int,
        tenant_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        normalized_key = self._get_settings_key(user_id, tenant_id)
        payloads = self._load_candidate_payloads(self._settings_key_candidates(user_id, tenant_id))
        if not payloads:
            return normalized_key, None

        preferred_key, preferred_payload = max(
            payloads.items(),
            key=lambda item: self._settings_score(item[1]),
        )
        if preferred_key != normalized_key:
            write_json_cache(self.redis, normalized_key, preferred_payload)
        for key in payloads:
            if key != normalized_key:
                self.redis.client.delete(key)
        return normalized_key, preferred_payload

    @staticmethod
    def _position_key(symbol: str, position_side: str) -> str:
        side = str(position_side or "long").strip().lower()
        return f"{symbol.upper()}::{side}"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _build_account_payload(initial_cash: float) -> dict[str, Any]:
        normalized_initial_cash = float(initial_cash or 0.0)
        snapshot_at = SimulationAccountManager._utc_now().isoformat()
        return {
            "account_version": 1,
            "snapshot_at": snapshot_at,
            "cash": normalized_initial_cash,
            "available_cash": normalized_initial_cash,
            "frozen_cash": 0.0,
            "total_asset": normalized_initial_cash,
            "market_value": 0.0,
            "long_market_value": 0.0,
            "short_market_value": 0.0,
            "equity": normalized_initial_cash,
            "liabilities": 0.0,
            "maintenance_margin_ratio": 0.0,
            "warning_level": "normal",
            "positions": {},
            "initial_equity": normalized_initial_cash,
            "day_open_equity": normalized_initial_cash,
            "month_open_equity": normalized_initial_cash,
            "baseline": {
                "initial_equity": normalized_initial_cash,
                "day_open_equity": normalized_initial_cash,
                "month_open_equity": normalized_initial_cash,
            },
            "rebuild_source": "simulation_account_init",
            "rebuilt_at": snapshot_at,
        }

    async def get_settings(
        self,
        user_id: str | int,
        tenant_id: str = "default",
        default_initial_cash: float = 1_000_000.0,
        cooldown_days: int = 30,
    ) -> dict[str, Any]:
        tenant_id = self._normalize_tenant(tenant_id)
        key, data = self._reconcile_settings_cache(user_id=user_id, tenant_id=tenant_id)

        initial_cash = float(default_initial_cash)
        last_modified_at: str | None = None
        next_allowed_modified_at: str | None = None
        can_modify = True

        if data:
            initial_cash = float(data.get("initial_cash", default_initial_cash))
            last_modified_at = data.get("last_modified_at")
            if last_modified_at:
                try:
                    last_dt = datetime.fromisoformat(last_modified_at.replace("Z", "+00:00"))
                    next_dt = last_dt + timedelta(days=cooldown_days)
                    next_allowed_modified_at = next_dt.isoformat()
                    can_modify = self._utc_now() >= next_dt
                except Exception:
                    logger.warning("Failed to parse simulation settings timestamp for key=%s", key)

        return {
            "initial_cash": initial_cash,
            "last_modified_at": last_modified_at,
            "next_allowed_modified_at": next_allowed_modified_at,
            "can_modify": can_modify,
            "cooldown_days": cooldown_days,
        }

    async def set_initial_cash(
        self,
        user_id: str | int,
        initial_cash: float,
        tenant_id: str = "default",
    ) -> None:
        """Update initial_cash in settings (used when syncing holdings)."""
        tenant_id = self._normalize_tenant(tenant_id)
        key, data = self._reconcile_settings_cache(user_id=user_id, tenant_id=tenant_id)

        # 读取现有 settings，保留其他字段
        data = data or {}
        data["initial_cash"] = float(initial_cash)
        data["last_modified_at"] = self._utc_now().isoformat()

        write_json_cache(self.redis, key, data)
        logger.info(
            "Updated simulation settings initial_cash for tenant=%s user=%s to %.2f",
            tenant_id,
            user_id,
            initial_cash,
        )

    # set_settings removed as initial cash modification is deprecated.


    async def init_account(
        self,
        user_id: str | int,
        initial_cash: float = 1_000_000.0,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Initialize or reset simulation account."""
        tenant_id = self._normalize_tenant(tenant_id)
        key = self._get_key(user_id, tenant_id)

        account_data = self._build_account_payload(initial_cash)

        write_json_cache(self.redis, key, account_data)
        for candidate in self._account_key_candidates(user_id, tenant_id):
            if candidate != key:
                self.redis.client.delete(candidate)
        logger.info(
            "Initialized simulation account for tenant=%s user=%s with %.2f",
            tenant_id,
            user_id,
            initial_cash,
        )

        return account_data

    async def get_account(self, user_id: str | int, tenant_id: str = "default") -> dict[str, Any] | None:
        """Get simulation account state. Returns None if account not initialized."""
        if not self.redis.client:
            return None

        tenant_id = self._normalize_tenant(tenant_id)
        _, data = self._reconcile_account_cache(user_id=user_id, tenant_id=tenant_id)

        # 不再自动初始化，返回 None 表示账户未创建
        return data

    async def update_balance(
        self,
        user_id: str | int,
        symbol: str,
        delta_cash: float,
        delta_volume: float,
        price: float,
        tenant_id: str = "default",
        trade_action: str | None = None,
        position_side: str = "long",
        is_margin_trade: bool = False,
    ) -> dict[str, Any]:
        """Update account balance after trade execution."""
        if not self.redis.client:
            return {"success": False, "reason": "REDIS_UNAVAILABLE"}

        tenant_id = self._normalize_tenant(tenant_id)
        key, account_data = self._reconcile_account_cache(user_id=user_id, tenant_id=tenant_id)

        # 如果账户不存在，先初始化（交易时需要账户存在）
        if account_data is None:
            settings = await self.get_settings(
                user_id=user_id,
                tenant_id=tenant_id,
                default_initial_cash=1_000_000.0,
            )
            key = self._get_key(user_id, tenant_id)
            await self.init_account(
                user_id,
                initial_cash=float(settings.get("initial_cash", 1_000_000.0) or 1_000_000.0),
                tenant_id=tenant_id,
            )

        if (
            is_margin_trade
            or str(position_side).lower() == "short"
            or (trade_action and trade_action.lower() in {"sell_to_open", "buy_to_close"})
        ):
            return await self._update_balance_margin(
                user_id=user_id,
                symbol=symbol,
                price=price,
                tenant_id=tenant_id,
                trade_action=trade_action,
                quantity=abs(delta_volume),
            )

        try:
            result = self.redis.client.eval(
                self._update_balance_lua,
                1,
                key,
                symbol,
                str(delta_cash),
                str(delta_volume),
                str(price),
            )
            payload = json.loads(result) if isinstance(result, str) else result
            if isinstance(payload, dict):
                return payload
            return {"success": False, "reason": "INVALID_SCRIPT_RESULT"}
        except Exception as e:
            logger.error("Failed to update simulation account atomically: %s", e)
            return {"success": False, "reason": "ATOMIC_UPDATE_FAILED"}

    async def _update_balance_margin(
        self,
        *,
        user_id: str | int,
        symbol: str,
        price: float,
        tenant_id: str,
        trade_action: str | None,
        quantity: float,
    ) -> dict[str, Any]:
        key = self._get_key(user_id, tenant_id)
        snapshot_at = self._utc_now().isoformat()
        action = str(trade_action or "").lower()
        pos_key = self._position_key(symbol, "short")
        try:
            result = self.redis.client.eval(
                self._update_balance_margin_lua,
                1,
                key,
                pos_key,
                str(float(price)),
                action,
                str(float(quantity)),
                str(float(settings.DEFAULT_BORROW_RATE) / 252.0),
                str(float(settings.MARGIN_CLOSEOUT_RATIO)),
                str(float(settings.MARGIN_WARNING_RATIO)),
                snapshot_at,
            )
            payload = json.loads(result) if isinstance(result, str) else result
            if isinstance(payload, dict):
                return payload
            return {"success": False, "reason": "INVALID_SCRIPT_RESULT"}
        except Exception as e:
            logger.error("Failed to update simulation margin account atomically: %s", e)
            return {"success": False, "reason": "ATOMIC_MARGIN_UPDATE_FAILED"}
