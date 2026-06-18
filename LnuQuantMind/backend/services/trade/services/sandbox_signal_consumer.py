import asyncio
import json
import logging
import time
from typing import Any, Optional

import redis as redis_lib
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.sentinel import Sentinel

from backend.services.trade.redis_client import RedisClient
from backend.services.trade.trade_config import settings
from backend.services.trade.simulation.models.order import OrderStatus
from backend.services.trade.simulation.schemas.order import SimOrderCreate
from backend.services.trade.simulation.services.execution_engine import SimulationExecutionEngine
from backend.services.trade.simulation.services.order_service import SimOrderService
from backend.services.trade.simulation.services.simulation_manager import SimulationAccountManager
from backend.shared.database_manager_v2 import get_db_manager

logger = logging.getLogger(__name__)


class SandboxSignalConsumer:
    """
    沙箱信号消费者：从 Redis 队列 trade:simulation:signals 中提取策略信号并执行。
    修复了 strategy_id 类型不匹配以及行情为 0 时的逻辑问题。
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.queue_name = "trade:simulation:signals"
        self._blpop_timeout_seconds = 5
        self._socket_timeout_margin_seconds = 2.0
        self._listener_client: redis_lib.Redis | None = None
        self._running = False
        self._retry_delay_seconds = 1.0
        self._max_retry_delay_seconds = 10.0
        self._consecutive_redis_errors = 0
        self._last_reconnect_at = 0.0

    async def start(self):
        """启动后台消费循环"""
        if not self.redis.client:
            logger.error("[SandboxSignalConsumer] Redis 客户端未连接，启动失败")
            return

        if not self._ensure_listener_client():
            logger.error("[SandboxSignalConsumer] 专用 Redis 监听连接未就绪，启动失败")
            return

        self._running = True
        logger.info("[SandboxSignalConsumer] 已启动，正在监听队列: %s", self.queue_name)

        while self._running:
            try:
                if not self._listener_client and not self._ensure_listener_client():
                    raise RedisConnectionError("listener redis client unavailable")

                # 使用专用连接做阻塞式获取，避免和共享 Redis socket_timeout 冲突。
                result = await asyncio.to_thread(
                    self._listener_client.blpop,
                    self.queue_name,
                    self._blpop_timeout_seconds,
                )
                if not result:
                    self._reset_retry_state()
                    continue

                _, data_raw = result
                signal = json.loads(data_raw)
                await self._process_signal(signal)
                self._reset_retry_state()

            except (RedisTimeoutError, RedisConnectionError, OSError) as e:
                await self._handle_redis_transport_error(e)
            except Exception as e:
                logger.error("[SandboxSignalConsumer] 循环处理出错: %s", e, exc_info=True)
                await asyncio.sleep(1)

    def stop(self):
        """停止消费"""
        self._running = False
        self._close_listener_client()

    def _reset_retry_state(self):
        self._consecutive_redis_errors = 0
        self._retry_delay_seconds = 1.0

    def _build_listener_client(self) -> redis_lib.Redis:
        socket_timeout = self._blpop_timeout_seconds + self._socket_timeout_margin_seconds
        if settings.REDIS_SENTINEL_ENABLED:
            sentinel_hosts = [tuple(host.split(":")) for host in settings.REDIS_SENTINEL_HOSTS.split(",")]
            sentinel = Sentinel(
                sentinel_hosts,
                socket_timeout=socket_timeout,
                password=settings.REDIS_PASSWORD,
            )
            return sentinel.master_for(
                settings.REDIS_MASTER_NAME,
                socket_timeout=socket_timeout,
                socket_connect_timeout=5.0,
                db=settings.REDIS_DB,
                decode_responses=True,
            )

        return redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            socket_timeout=socket_timeout,
            socket_connect_timeout=5.0,
        )

    def _ensure_listener_client(self) -> bool:
        if self._listener_client is not None:
            return True
        try:
            client = self._build_listener_client()
            client.ping()
            self._listener_client = client
            return True
        except Exception as exc:
            logger.warning("[SandboxSignalConsumer] 初始化专用 Redis 监听连接失败: %s", exc)
            self._listener_client = None
            return False

    def _close_listener_client(self):
        client = self._listener_client
        self._listener_client = None
        if client is None:
            return
        try:
            client.close()
        except Exception:
            logger.debug("[SandboxSignalConsumer] 关闭专用 Redis 监听连接时忽略异常", exc_info=True)

    async def _handle_redis_transport_error(self, error: Exception):
        """Redis 传输层异常时进行退避重连，避免日志刷屏。"""
        self._consecutive_redis_errors += 1

        if self._consecutive_redis_errors == 1 or self._consecutive_redis_errors % 5 == 0:
            logger.warning(
                "[SandboxSignalConsumer] Redis 监听异常(%s 次)，准备退避重连: %s",
                self._consecutive_redis_errors,
                error,
            )
        else:
            logger.debug(
                "[SandboxSignalConsumer] Redis 监听异常(%s 次): %s",
                self._consecutive_redis_errors,
                error,
            )

        await self._reconnect_redis_client()
        await asyncio.sleep(self._retry_delay_seconds)
        self._retry_delay_seconds = min(self._retry_delay_seconds * 2, self._max_retry_delay_seconds)

    async def _reconnect_redis_client(self):
        """重建专用监听 Redis 连接，避免长时间持有失效 socket。"""
        now = time.monotonic()
        if now - self._last_reconnect_at < 3:
            return

        self._last_reconnect_at = now
        try:
            self._close_listener_client()
            listener_ready = await asyncio.to_thread(self._ensure_listener_client)
            if listener_ready:
                logger.info("[SandboxSignalConsumer] Redis 监听连接已重建，继续监听队列: %s", self.queue_name)
            else:
                logger.warning("[SandboxSignalConsumer] Redis 监听重连后仍未就绪，稍后继续重试")
        except Exception as reconnect_error:
            logger.warning("[SandboxSignalConsumer] Redis 监听重连失败: %s", reconnect_error, exc_info=True)

    async def _process_signal(self, signal: dict):
        """处理单个信号"""
        sig_type = signal.get("type")
        if sig_type == "order":
            await self._handle_direct_order(signal)
        elif sig_type == "order_target_percent":
            await self._handle_order_target_percent(signal)
        elif sig_type == "log":
            # 简单的日志处理，目前仅打印
            logger.info("[Sandbox Log] %s: %s", signal.get("run_id"), signal.get("message"))
        else:
            logger.warning("[SandboxSignalConsumer] 收到未知信号类型: %s", sig_type)

    async def _handle_direct_order(self, signal: dict):
        """处理直接下单信号"""
        data = signal.get("data", {})
        tenant_id = signal.get("tenant_id", "default")
        user_id = self._to_int(signal.get("user_id"))
        strategy_id = self._to_int(signal.get("strategy_id"))
        
        if user_id is None:
            logger.error("[SandboxSignalConsumer] 信号缺失 user_id: %s", signal)
            return

        # 映射字段
        order_data = SimOrderCreate(
            symbol=data.get("symbol"),
            side=data.get("side"),
            order_type=data.get("order_type", "limit"),
            quantity=float(data.get("quantity", 0)),
            price=float(data.get("price")) if data.get("price") else None,
            strategy_id=strategy_id,
            remarks=f"Sandbox auto-order: {signal.get('run_id')}"
        )

        await self._create_and_execute_order(tenant_id, user_id, order_data)

    async def _handle_order_target_percent(self, signal: dict):
        """处理目标比例下单信号（目前简化为按照当前价格下单，真实逻辑应计算仓位差值）"""
        # 注意：此处为保持链路通畅，暂不支持复杂的仓位计算，仅记录意图。
        # 实际生产中应在此处查询 SimulationAccountManager 获取当前仓位。
        logger.info("[SandboxSignalConsumer] 收到 order_target_percent 信号，暂不支持实时调仓计算: %s", signal)

    async def _create_and_execute_order(self, tenant_id: str, user_id: int, data: SimOrderCreate):
        """创建并执行模拟订单"""
        db_manager = get_db_manager()
        async with db_manager.get_master_session() as session:
            try:
                order_service = SimOrderService(session)
                manager = SimulationAccountManager(self.redis)
                engine = SimulationExecutionEngine(session, manager)

                # 1. 创建订单记录
                order = await order_service.create_order(
                    tenant_id,
                    user_id,
                    data,
                    trigger_source="sandbox_signal",
                )
                order.status = OrderStatus.SUBMITTED
                await session.commit()

                # 2. 执行撮合
                result = await engine.execute_order(order)
                if not result.success:
                    await engine.mark_rejected(order, result.message)
                    logger.warning("[SandboxSignalConsumer] 模拟成交失败: %s, OrderID: %s", result.message, order.order_id)
                else:
                    await engine.apply_filled(order, result)
                    logger.info("[SandboxSignalConsumer] 模拟成交成功: %s %s @ %s", order.symbol, order.side, result.price)

            except Exception as e:
                logger.error("[SandboxSignalConsumer] 执行下单链路失败: %s", e, exc_info=True)

    @staticmethod
    def _to_int(val: Any) -> Optional[int]:
        """类型转换辅助"""
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
