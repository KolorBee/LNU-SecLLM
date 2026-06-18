"""
Synthetic execution engine for simulation orders.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.trade.simulation.models.order import (
    OrderStatus,
    OrderType,
)
from backend.services.trade.simulation.models.account import SimulationAccount
from backend.services.trade.simulation.models.order_v2 import SimulationOrderV2
from backend.services.trade.simulation.models.fill import SimulationFill
from backend.services.trade.simulation.services.ledger_service import (
    SimulationLedgerService,
)
from backend.services.trade.simulation.services.projection_service import (
    SimulationProjectionService,
)
from backend.services.trade.simulation.services.simulation_manager import (
    SimulationAccountManager,
)
from backend.services.trade.trade_config import settings
from backend.shared.auth import get_internal_call_secret
from backend.shared.trade_account_cache import write_json_cache, write_trade_account_cache
from backend.shared.trading_calendar import calendar_service
from sqlalchemy import select

logger = logging.getLogger(__name__)
_SHARED_HTTP_CLIENT: httpx.AsyncClient | None = None


class ExecutionResult:
    def __init__(
        self,
        *,
        success: bool,
        price: float = 0.0,
        quantity: float = 0.0,
        commission: float = 0.0,
        stamp_duty: float = 0.0,
        transfer_fee: float = 0.0,
        price_source: str | None = None,
        session_phase: str | None = None,
        message: str = "",
    ):
        self.success = success
        self.price = price
        self.quantity = quantity
        self.commission = commission
        self.stamp_duty = stamp_duty
        self.transfer_fee = transfer_fee
        self.price_source = price_source
        self.session_phase = session_phase
        self.message = message


@dataclass
class MarketSnapshot:
    price: float
    price_source: str
    limit_up: bool = False
    limit_down: bool = False
    suspended: bool = False


@dataclass
class ExecutionWindowDecision:
    can_execute: bool
    retryable: bool
    message: str = ""
    market_phase: str | None = None
    session_phase: str | None = None
    current_trade_date: date | None = None
    target_trade_date: date | None = None
    final_state: str | None = None


class SimulationExecutionEngine:
    def __init__(self, db: AsyncSession, manager: SimulationAccountManager):
        self.db = db
        self.manager = manager

    async def _http_client(self) -> httpx.AsyncClient:
        global _SHARED_HTTP_CLIENT
        if _SHARED_HTTP_CLIENT is None:
            _SHARED_HTTP_CLIENT = httpx.AsyncClient(timeout=5.0)
        return _SHARED_HTTP_CLIENT

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if not text:
            return False
        return text in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _is_price_near(
        price: float, limit_price: float | None, tolerance: float = 0.0015
    ) -> bool:
        if limit_price is None or limit_price <= 0 or price <= 0:
            return False
        return abs(price - limit_price) / max(limit_price, 1e-6) <= tolerance

    @staticmethod
    def _map_session_phase(matched_session: Any) -> str | None:
        text = str(matched_session or "").strip().upper()
        if not text:
            return None
        if text in {"AM", "CONTINUOUS_AM"}:
            return "CONTINUOUS_AM"
        if text in {"PM", "CONTINUOUS_PM"}:
            return "CONTINUOUS_PM"
        return text

    @staticmethod
    def _normalize_runtime_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone().replace(tzinfo=None)

    @staticmethod
    def _normalize_runtime_date(value: Any) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return None

    @staticmethod
    def _normalize_time_in_force(value: Any) -> str:
        return str(value or "DAY").strip().upper() or "DAY"

    @staticmethod
    def _market_now() -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    async def _resolve_next_session_trade_date(
        self,
        *,
        tenant_id: str,
        user_id: int,
        current_trade_date: date,
        market_phase: str | None,
        is_trading_day: bool,
    ) -> date:
        if is_trading_day and market_phase in {"PRE_OPEN", "LUNCH_BREAK"}:
            return current_trade_date
        return await calendar_service.next_trading_day(
            market="SSE",
            trade_date=current_trade_date,
            tenant_id=str(tenant_id or "default"),
            user_id=str(user_id),
        )

    async def assess_execution_window(self, order: Any) -> ExecutionWindowDecision:
        """Decide whether the order can execute now or should wait/expire/reject."""
        market_now = self._market_now()
        current_trade_date = market_now.date()
        tif = self._normalize_time_in_force(getattr(order, "time_in_force", None))
        target_trade_date = self._normalize_runtime_date(
            getattr(order, "trading_session_date", None)
        )
        is_trading_day = False
        try:
            is_trading_day = await calendar_service.is_trading_day(
                market="SSE",
                trade_date=current_trade_date,
                tenant_id=str(order.tenant_id or "default"),
                user_id=str(order.user_id),
            )
            trading_state = await calendar_service.is_trading_time(
                market="SSE",
                dt=market_now,
                tenant_id=str(order.tenant_id or "default"),
                user_id=str(order.user_id),
            )
        except Exception as exc:
            logger.warning(
                "Trading calendar lookup failed for simulation order %s: %s",
                getattr(order, "order_id", None),
                exc,
            )
            return ExecutionWindowDecision(
                can_execute=False,
                retryable=False,
                message="Trading session unavailable, order cannot be filled",
                current_trade_date=current_trade_date,
                target_trade_date=target_trade_date,
                final_state="rejected",
            )

        market_phase = str(trading_state.get("market_phase") or "").strip().upper() or None
        session_phase = self._map_session_phase(trading_state.get("matched_session"))
        if tif == "DAY" and target_trade_date is not None:
            if current_trade_date > target_trade_date:
                return ExecutionWindowDecision(
                    can_execute=False,
                    retryable=False,
                    message="DAY order expired after trading session date",
                    market_phase=market_phase,
                    session_phase=session_phase,
                    current_trade_date=current_trade_date,
                    target_trade_date=target_trade_date,
                    final_state="expired",
                )
            if current_trade_date == target_trade_date and market_phase == "AFTER_CLOSE":
                return ExecutionWindowDecision(
                    can_execute=False,
                    retryable=False,
                    message="DAY order expired after market close",
                    market_phase=market_phase,
                    session_phase=session_phase,
                    current_trade_date=current_trade_date,
                    target_trade_date=target_trade_date,
                    final_state="expired",
                )

        if bool(trading_state.get("is_trading_time")):
            return ExecutionWindowDecision(
                can_execute=True,
                retryable=False,
                market_phase=market_phase,
                session_phase=session_phase,
                current_trade_date=current_trade_date,
                target_trade_date=current_trade_date,
                final_state=None,
            )

        if tif == "IOC":
            return ExecutionWindowDecision(
                can_execute=False,
                retryable=False,
                message="IOC order expired outside active trading session",
                market_phase=market_phase,
                session_phase=session_phase,
                current_trade_date=current_trade_date,
                target_trade_date=current_trade_date,
                final_state="expired",
            )

        next_trade_date = await self._resolve_next_session_trade_date(
            tenant_id=str(order.tenant_id or "default"),
            user_id=int(order.user_id),
            current_trade_date=current_trade_date,
            market_phase=market_phase,
            is_trading_day=is_trading_day,
        )
        return ExecutionWindowDecision(
            can_execute=False,
            retryable=True,
            message="Outside A-share trading session, order queued for next valid session",
            market_phase=market_phase,
            session_phase=session_phase,
            current_trade_date=current_trade_date,
            target_trade_date=(
                target_trade_date if tif == "DAY" and target_trade_date is not None else next_trade_date
            ),
            final_state="queued",
        )

    async def _ensure_trading_session(self, order: Any) -> tuple[str | None, str | None]:
        """Backward-compatible wrapper for older tests/callers."""
        decision = await self.assess_execution_window(order)
        if not decision.can_execute:
            return decision.message, decision.session_phase
        return None, decision.session_phase

    async def _load_account_snapshot(self, order: Any) -> dict[str, Any]:
        account_id = SimulationProjectionService.build_account_id(
            order.tenant_id,
            order.user_id,
        )
        projection_account = await self.db.get(SimulationAccount, account_id)
        if projection_account is not None:
            return {
                "cash": float(projection_account.cash or 0.0),
                "available_cash": float(projection_account.available_cash or 0.0),
                "market_value": float(projection_account.long_market_value or 0.0),
                "short_market_value": float(projection_account.short_market_value or 0.0),
                "total_asset": float(projection_account.total_asset or 0.0),
                "liabilities": float(projection_account.liabilities or 0.0),
                "maintenance_margin_ratio": float(
                    projection_account.maintenance_margin_ratio or 0.0
                ),
                "initial_equity": float(projection_account.initial_equity or 0.0),
            }

        account = await self.manager.get_account(order.user_id, tenant_id=order.tenant_id)
        if account:
            return dict(account)

        settings_payload = await self.manager.get_settings(
            user_id=order.user_id,
            tenant_id=order.tenant_id,
            default_initial_cash=1_000_000.0,
        )
        initial_cash = float(settings_payload.get("initial_cash", 1_000_000.0) or 1_000_000.0)
        return {
            "cash": initial_cash,
            "available_cash": initial_cash,
            "total_asset": initial_cash,
            "initial_equity": initial_cash,
            "baseline": {"initial_equity": initial_cash},
        }

    async def _latest_price(
        self,
        symbol: str,
        *,
        user_id: int | None = None,
        tenant_id: str | None = None,
    ) -> MarketSnapshot:
        raw_symbol = str(symbol or "").strip().upper()
        prefix_symbol = raw_symbol
        suffix_symbol = raw_symbol
        if raw_symbol.endswith((".SH", ".SZ", ".BJ")) and len(raw_symbol) > 3:
            prefix_symbol = f"{raw_symbol[-2:]}{raw_symbol[:-3]}"
        elif raw_symbol.startswith(("SH", "SZ", "BJ")) and len(raw_symbol) > 2:
            suffix_symbol = f"{raw_symbol[2:]}.{raw_symbol[:2]}"

        market_url = settings.MARKET_DATA_SERVICE_URL.rstrip("/")

        # Level 1: 实时行情服务
        try:
            client = await self._http_client()
            headers = {"X-Internal-Call": get_internal_call_secret()}
            if user_id is not None:
                headers["X-User-Id"] = str(user_id)
                headers["X-Tenant-Id"] = str(tenant_id or "default")

            for candidate in [raw_symbol, prefix_symbol, suffix_symbol]:
                if not candidate:
                    continue
                endpoint = f"{market_url}/api/v1/quotes/{candidate}"
                resp = await client.get(endpoint, headers=headers)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                px = self._as_float(data.get("current_price") or data.get("last_price"))
                if px and px > 0:
                    limit_up = self._as_bool(data.get("is_limit_up"))
                    limit_down = self._as_bool(data.get("is_limit_down"))
                    suspended = self._as_bool(
                        data.get("suspended") or data.get("is_suspended")
                    )
                    limit_up_price = self._as_float(data.get("limit_up_today"))
                    limit_down_price = self._as_float(data.get("limit_down_today"))
                    if not limit_up and self._is_price_near(px, limit_up_price):
                        limit_up = True
                    if not limit_down and self._is_price_near(px, limit_down_price):
                        limit_down = True

                    pre_close = self._as_float(
                        data.get("pre_close") or data.get("close_price")
                    )
                    ask1_volume = self._as_int(data.get("ask1_volume"))
                    bid1_volume = self._as_int(data.get("bid1_volume"))
                    if pre_close and pre_close > 0:
                        change_ratio = (px - pre_close) / pre_close
                        # 行情源未直接给出涨跌停标签时，用盘口封单 + 涨跌幅做近似识别。
                        if (
                            not limit_up
                            and ask1_volume is not None
                            and ask1_volume <= 0
                            and change_ratio >= 0.095
                        ):
                            limit_up = True
                        if (
                            not limit_down
                            and bid1_volume is not None
                            and bid1_volume <= 0
                            and change_ratio <= -0.095
                        ):
                            limit_down = True

                    return MarketSnapshot(
                        price=px,
                        price_source="market_data_service",
                        limit_up=limit_up,
                        limit_down=limit_down,
                        suspended=suspended,
                    )
        except Exception as e:
            logger.warning("Failed to fetch market quote for %s: %s", raw_symbol, e)

        # Level 2: 数据库兜底 (L2 Fallback)
        try:
            from sqlalchemy import text

            query_with_limits = text("""
                SELECT close, adj_factor, limit_up_today, limit_down_today, volume
                FROM stock_daily_latest 
                WHERE symbol = :symbol 
                ORDER BY trade_date DESC LIMIT 1
            """)
            try:
                result = await self.db.execute(
                    query_with_limits, {"symbol": prefix_symbol}
                )
                row = result.fetchone()
                if not row and suffix_symbol != prefix_symbol:
                    result = await self.db.execute(
                        query_with_limits, {"symbol": suffix_symbol}
                    )
                    row = result.fetchone()
                if row:
                    hfq_close = float(row[0])
                    adj_factor = float(row[1] or 1.0)
                    price = hfq_close / adj_factor if adj_factor > 0 else hfq_close
                    logger.info(
                        "Fallback to DB nominal price for %s: %s", raw_symbol, price
                    )
                    return MarketSnapshot(
                        price=price,
                        price_source="db_fallback",
                        limit_up=self._is_price_near(price, self._as_float(row[2])),
                        limit_down=self._is_price_near(price, self._as_float(row[3])),
                        suspended=(self._as_float(row[4]) or 0.0) <= 0.0,
                    )
            except Exception:
                # 兼容少数字段尚未完成迁移的环境
                query_legacy = text("""
                    SELECT close, adj_factor
                    FROM stock_daily_latest 
                    WHERE symbol = :symbol 
                    ORDER BY trade_date DESC LIMIT 1
                """)
                legacy_result = await self.db.execute(
                    query_legacy, {"symbol": prefix_symbol}
                )
                legacy_row = legacy_result.fetchone()
                if not legacy_row and suffix_symbol != prefix_symbol:
                    legacy_result = await self.db.execute(
                        query_legacy, {"symbol": suffix_symbol}
                    )
                    legacy_row = legacy_result.fetchone()
                if legacy_row:
                    hfq_close = float(legacy_row[0])
                    adj_factor = float(legacy_row[1] or 1.0)
                    price = hfq_close / adj_factor if adj_factor > 0 else hfq_close
                    logger.info(
                        "Fallback to DB legacy nominal price for %s: %s",
                        raw_symbol,
                        price,
                    )
                    return MarketSnapshot(price=price, price_source="db_fallback")
        except Exception as e:
            logger.error(f"Database fallback failed for {raw_symbol}: {e}")

        # Level 3: 最终保底仅拒单，不再生成随机价格，避免伪成交污染账户。
        return MarketSnapshot(
            price=0.0,
            price_source="unavailable",
            suspended=True,
        )

    async def execute_order(self, order: Any) -> ExecutionResult:
        expires_at = self._normalize_runtime_datetime(getattr(order, "expires_at", None))
        if expires_at is not None and expires_at <= datetime.now():
            return ExecutionResult(
                success=False,
                message="Order expired before execution",
            )
        session_check = await self._ensure_trading_session(order)
        if isinstance(session_check, tuple):
            session_error, session_phase = session_check
        else:
            session_error = session_check
            session_phase = None
        if session_error:
            return ExecutionResult(success=False, message=session_error)

        snapshot = await self._latest_price(
            order.symbol,
            user_id=order.user_id,
            tenant_id=order.tenant_id,
        )
        base_price = snapshot.price
        fetched_source = snapshot.price_source
        slippage = settings.SIMULATION_SLIPPAGE_BPS / 10000

        side = str(order.side.value).lower()
        if snapshot.suspended:
            return ExecutionResult(
                success=False, message="Security is suspended, cannot trade"
            )
        if base_price <= 0:
            return ExecutionResult(
                success=False, message="No valid market price, cannot trade"
            )
        if order.quantity <= 0:
            return ExecutionResult(success=False, message="Quantity must be positive")
        if not float(order.quantity).is_integer() or int(order.quantity) % 100 != 0:
            return ExecutionResult(
                success=False,
                message="A-share simulation quantity must be an integral board lot of 100",
            )
        if side == "buy" and snapshot.limit_up:
            return ExecutionResult(
                success=False, message="Limit-up locked, buy order cannot be filled"
            )
        if side == "sell" and snapshot.limit_down:
            return ExecutionResult(
                success=False, message="Limit-down locked, sell order cannot be filled"
            )

        trade_action = str(getattr(order, "trade_action", None) or "").strip() or None
        position_side = (
            str(getattr(order, "position_side", None) or "long").strip() or "long"
        )
        is_margin_trade = bool(getattr(order, "is_margin_trade", False))
        if side == "sell" and position_side.lower() == "long":
            available_qty = await SimulationProjectionService(self.db).get_available_quantity(
                tenant_id=order.tenant_id,
                user_id=order.user_id,
                symbol=order.symbol,
                position_side="long",
            )
            if available_qty + 1e-6 < float(order.quantity or 0.0):
                return ExecutionResult(
                    success=False,
                    message="Insufficient available holdings for sell order (T+1 restriction)",
                )

        if order.order_type == OrderType.MARKET:
            direction = 1 if side == "buy" else -1
            exec_price = round(base_price * (1 + direction * slippage), 4)
            price_source = fetched_source
        elif order.order_type == OrderType.LIMIT:
            if order.price is None or order.price <= 0:
                return ExecutionResult(success=False, message="Limit price required")
            limit_price = float(order.price)
            direction = 1 if side == "buy" else -1
            simulated_price = round(base_price * (1 + direction * slippage), 4)
            if side == "buy":
                if limit_price < base_price:
                    return ExecutionResult(
                        success=False, message="Buy limit price is below market price"
                    )
                exec_price = min(simulated_price, round(limit_price, 4))
            else:
                if limit_price > base_price:
                    return ExecutionResult(
                        success=False, message="Sell limit price is above market price"
                    )
                exec_price = max(simulated_price, round(limit_price, 4))
            price_source = "limit_price"
        else:
            return ExecutionResult(
                success=False, message=f"Unsupported order type: {order.order_type}"
            )

        commission = round(
            order.quantity * exec_price * settings.SIMULATION_COMMISSION_RATE, 2
        )
        stamp_duty = (
            round(order.quantity * exec_price * settings.SIMULATION_STAMP_DUTY_RATE, 2)
            if side == "sell"
            else 0.0
        )
        transfer_fee = round(
            order.quantity * exec_price * settings.SIMULATION_TRANSFER_FEE_RATE, 2
        )
        total_fee = commission + stamp_duty + transfer_fee
        gross = order.quantity * exec_price
        account_snapshot = await self._load_account_snapshot(order)
        if side == "buy" and position_side.lower() != "short":
            available_cash = float(
                account_snapshot.get("available_cash")
                or account_snapshot.get("cash")
                or 0.0
            )
            if available_cash + 1e-6 < (gross + total_fee):
                return ExecutionResult(
                    success=False, message="Insufficient cash for buy order"
                )
        if position_side.lower() == "short" and str(trade_action or "").lower() == "buy_to_close":
            available_short = await SimulationProjectionService(self.db).get_available_quantity(
                tenant_id=order.tenant_id,
                user_id=order.user_id,
                symbol=order.symbol,
                position_side="short",
            )
            if available_short + 1e-6 < float(order.quantity or 0.0):
                return ExecutionResult(
                    success=False, message="Insufficient short holdings for buy-to-close order"
                )

        return ExecutionResult(
            success=True,
            price=exec_price,
            quantity=order.quantity,
            commission=commission,
            stamp_duty=stamp_duty,
            transfer_fee=transfer_fee,
            price_source=price_source,
            session_phase=session_phase,
        )

    async def apply_filled(self, order: Any, result: ExecutionResult):
        trade_value = result.quantity * result.price
        executed_at = datetime.now()
        account_id = SimulationProjectionService.build_account_id(
            order.tenant_id,
            order.user_id,
        )
        fill = SimulationFill(
            order_id=order.order_id,
            legacy_trade_id=None,
            tenant_id=order.tenant_id,
            user_id=str(order.user_id),
            account_id=account_id,
            strategy_id=str(order.strategy_id) if order.strategy_id is not None else None,
            portfolio_id=int(order.portfolio_id or 0),
            symbol=order.symbol,
            side=str(order.side.value),
            position_side=str(getattr(order, "position_side", None) or "long"),
            trade_action=getattr(order, "trade_action", None),
            fill_price=result.price,
            fill_quantity=result.quantity,
            gross_amount=trade_value,
            commission=result.commission,
            stamp_duty=result.stamp_duty,
            transfer_fee=result.transfer_fee,
            borrow_fee=0.0,
            executed_at=executed_at,
            price_source=result.price_source,
            session_phase=result.session_phase,
        )
        self.db.add(fill)
        await self.db.flush()

        order.status = OrderStatus.FILLED
        order.submitted_at = order.submitted_at or datetime.now()
        order.filled_at = executed_at
        order.filled_quantity = result.quantity
        order.average_price = result.price
        order.filled_value = trade_value
        order.commission = result.commission
        order.total_fee = result.commission + result.stamp_duty + result.transfer_fee
        order.order_value = order.quantity * (order.price or 0)
        order.execution_model = "synthetic_price"
        order.price_source = result.price_source

        account_snapshot = await self._load_account_snapshot(order)
        trade_event = SimpleNamespace(
            trade_id=fill.fill_id,
            trade_value=trade_value,
            commission=result.commission,
            stamp_duty=result.stamp_duty,
            transfer_fee=result.transfer_fee,
            total_fee=result.commission + result.stamp_duty + result.transfer_fee,
            executed_at=executed_at,
            quantity=result.quantity,
            price=result.price,
            side=order.side,
            trade_action=getattr(order, "trade_action", None),
            position_side=getattr(order, "position_side", None) or "long",
        )
        ledger_service = SimulationLedgerService(self.db)
        await ledger_service.record_trade(
            order=order,
            trade=trade_event,
            account_snapshot=account_snapshot,
        )

        projection_order = (
            await self.db.execute(
                select(SimulationOrderV2).where(SimulationOrderV2.order_id == order.order_id)
            )
        ).scalar_one_or_none()
        if projection_order is not None:
            projection_order.status = str(OrderStatus.FILLED.value)
            projection_order.rejected_reason = None
            projection_order.submitted_at = order.submitted_at

        await self.db.commit()
        await self._sync_trade_account(order.tenant_id, order.user_id)
        return SimpleNamespace(
            trade_id=fill.fill_id,
            fill_id=fill.fill_id,
            order_id=fill.order_id,
            symbol=fill.symbol,
            price=fill.fill_price,
            quantity=fill.fill_quantity,
        )

    async def mark_rejected(self, order: Any, message: str):
        order.status = OrderStatus.REJECTED
        order.submitted_at = order.submitted_at or datetime.now()
        order.remarks = f"Execution rejected: {message}"
        projection_order = (
            await self.db.execute(
                select(SimulationOrderV2).where(SimulationOrderV2.order_id == order.order_id)
            )
        ).scalar_one_or_none()
        if projection_order is not None:
            projection_order.status = str(OrderStatus.REJECTED.value)
            projection_order.rejected_reason = message
            projection_order.submitted_at = order.submitted_at
        await self.db.commit()

    async def mark_expired(self, order: Any, message: str):
        order.status = OrderStatus.EXPIRED
        order.submitted_at = order.submitted_at or datetime.now()
        order.remarks = f"Execution expired: {message}"
        projection_order = (
            await self.db.execute(
                select(SimulationOrderV2).where(SimulationOrderV2.order_id == order.order_id)
            )
        ).scalar_one_or_none()
        if projection_order is not None:
            projection_order.status = str(OrderStatus.EXPIRED.value)
            projection_order.rejected_reason = message
            projection_order.submitted_at = order.submitted_at
        await self.db.commit()

    async def _sync_trade_account(self, tenant_id: str, user_id: int):
        if not self.manager.redis.client:
            return
        projection = await SimulationProjectionService(self.db).load_projection(
            tenant_id=tenant_id,
            user_id=user_id,
            latest_price_loader=self._load_latest_price_value,
        )
        projection_account = projection.account
        if projection_account is None:
            return
        positions = projection.positions or {}
        payload = SimulationProjectionService.build_cache_payload(
            account=projection_account,
            positions=positions,
            source="simulation_execution_engine_projection",
        )
        payload.setdefault("timestamp", datetime.now().isoformat())
        write_json_cache(
            self.manager.redis,
            self.manager._get_key(user_id, tenant_id),
            payload,
        )
        write_trade_account_cache(self.manager.redis, tenant_id, user_id, payload)

    async def _load_latest_price_value(self, symbol: str) -> float:
        snapshot = await self._latest_price(symbol)
        return float(snapshot.price or 0.0)
