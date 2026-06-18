import json
import time
from typing import Any, Dict, List


class SandboxContext:
    """
    提供给隔离执行沙箱 (Worker 进程) 的交易上下文 (Mock SDK)。
    在这里拦截所有真实的订单和查询动作，转为标准化的 JSON 结构放入内存队列中。
    """

    def __init__(
        self,
        tenant_id: str,
        user_id: str,
        strategy_id: str,
        run_id: str,
        exec_config: dict,
        live_trade_config: dict | None = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.strategy_id = strategy_id
        self.run_id = run_id
        self.exec_config = exec_config
        self.live_trade_config = live_trade_config or {}
        self.signals_queue: list[dict[str, Any]] = []
        self._current_time: float = time.time()

    def set_time(self, current_time: float):
        """由 Worker 事件循环驱动当前时间"""
        self._current_time = current_time

    def log(self, message: str):
        """收集策略日志并作为信号抛给引擎"""
        self.signals_queue.append({"type": "log", "timestamp": self._current_time, "message": str(message)})

    def _add_order_signal(self, symbol: str, quantity: int, price: float, side: str, order_type: str = "limit"):
        signal = {
            "type": "order",
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "strategy_id": self.strategy_id,
            "run_id": self.run_id,
            "timestamp": self._current_time,
            "data": {"symbol": symbol, "quantity": quantity, "price": price, "side": side, "order_type": order_type},
        }
        self.signals_queue.append(signal)

    def order(self, symbol: str, quantity: int, price: float, side: str, order_type: str = "limit"):
        """
        直接下单接口：发送订单信号到沙箱引擎。
        参数:
            symbol: 股票代码 (如 "SH600036")
            quantity: 数量 (正整数)
            price: 价格 (限价单必填)
            side: 方向 ("buy" 或 "sell")
            order_type: 订单类型 ("limit" 或 "market")
        """
        self._add_order_signal(symbol, quantity, price, side, order_type)

    def order_target_percent(self, symbol: str, target_percent: float):
        """
        常见交易API接口：设置目标持仓比例。
        沙箱在这里只产生一条 intent (意图信号)，不真实向柜台发单。
        """
        # 注意：这里我们简化的输出一个特殊信号，交给后端的中央引擎去解析当前仓位并转换成具体单量
        signal = {
            "type": "order_target_percent",
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "strategy_id": self.strategy_id,
            "run_id": self.run_id,
            "timestamp": self._current_time,
            "data": {"symbol": symbol, "target_percent": target_percent},
        }
        self.signals_queue.append(signal)

    def get_position(self, symbol: str):
        """由于隔离，暂时不支持在模拟沙箱中通过 SDK 实时同步读取 Redis 回来的资金。只支持粗粒度撮合意图"""
        return 0

    def get_cash(self):
        """获取当前现金（沙箱模式下返回 0）"""
        return 0

    def get_total_asset(self):
        """获取总资产（沙箱模式下返回 0）"""
        return 0

    def flush_signals(self) -> list[dict[str, Any]]:
        """Worker 每个 Tick 结束后，将收集到的信号抛出。"""
        signals = list(self.signals_queue)
        self.signals_queue.clear()
        return signals


def create_sandbox_context(
    tenant_id: str,
    user_id: str,
    strategy_id: str,
    run_id: str,
    exec_config: dict,
    live_trade_config: dict | None = None,
) -> SandboxContext:
    return SandboxContext(tenant_id, user_id, strategy_id, run_id, exec_config, live_trade_config)
