"""Top-level QMT agent – WebSocket bridge and background loop orchestration."""
from __future__ import annotations

import concurrent.futures
import math
import json
import logging
import importlib.util
import queue
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import websocket

try:
    from .auth import AuthManager
    from .client import QMTClient
    from .config import AgentConfig
    from .reporter import BridgeReporter
    from .runtime_workers import (
        AccountReporterWorker,
        BridgeConnectionWorker,
        HeartbeatWorker,
        OrderDispatcher,
        OrderLifecycleMonitor,
        ReconnectWorker,
        RuntimeHealthMonitor,
        ScheduleWorker,
        SessionWorker,
        SmartExecutionWorker,
    )
    from .schedule_policy import SchedulePolicy
except ImportError:
    _MODULE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

    def _load_local_module(module_name: str):
        qualified_name = f"qmt_agent_local_{module_name}"
        module = sys.modules.get(qualified_name)
        if module is not None:
            return module
        module_path = _MODULE_DIR / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(qualified_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load local module {module_name} from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified_name] = module
        spec.loader.exec_module(module)
        return module

    AuthManager = _load_local_module("auth").AuthManager  # type: ignore[attr-defined]
    QMTClient = _load_local_module("client").QMTClient  # type: ignore[attr-defined]
    AgentConfig = _load_local_module("config").AgentConfig  # type: ignore[attr-defined]
    BridgeReporter = _load_local_module("reporter").BridgeReporter  # type: ignore[attr-defined]
    _runtime_workers_mod = _load_local_module("runtime_workers")
    SessionWorker = _runtime_workers_mod.SessionWorker  # type: ignore[attr-defined]
    HeartbeatWorker = _runtime_workers_mod.HeartbeatWorker  # type: ignore[attr-defined]
    BridgeConnectionWorker = _runtime_workers_mod.BridgeConnectionWorker  # type: ignore[attr-defined]
    AccountReporterWorker = _runtime_workers_mod.AccountReporterWorker  # type: ignore[attr-defined]
    OrderLifecycleMonitor = _runtime_workers_mod.OrderLifecycleMonitor  # type: ignore[attr-defined]
    SmartExecutionWorker = _runtime_workers_mod.SmartExecutionWorker  # type: ignore[attr-defined]
    OrderDispatcher = _runtime_workers_mod.OrderDispatcher  # type: ignore[attr-defined]
    ReconnectWorker = _runtime_workers_mod.ReconnectWorker  # type: ignore[attr-defined]
    ScheduleWorker = _runtime_workers_mod.ScheduleWorker  # type: ignore[attr-defined]
    RuntimeHealthMonitor = _runtime_workers_mod.RuntimeHealthMonitor  # type: ignore[attr-defined]
    SchedulePolicy = _load_local_module("schedule_policy").SchedulePolicy  # type: ignore[attr-defined]

logger = logging.getLogger("qmt_agent")

class QMTAgent:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.auth = AuthManager(cfg)
        self.reporter = BridgeReporter(cfg, self.auth)
        self.qmt = QMTClient(cfg, execution_callback=self._handle_qmt_event)
        self.stop_event = threading.Event()
        self.ws: Optional[websocket.WebSocketApp] = None
        self._ws_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self.runtime_state = "idle"
        self.last_error: Optional[str] = None
        self.last_heartbeat_at: Optional[float] = None
        self.last_account_report_at: Optional[float] = None
        self.last_bridge_connect_at: Optional[float] = None
        self.last_execution_at: Optional[float] = None
        self.last_start_at: Optional[float] = None
        self._dirty_event = threading.Event()
        self._threads: dict[str, threading.Thread] = {}
        self._pending_orders: dict[str, dict[str, Any]] = {}
        self._pending_orders_lock = threading.RLock()
        self._smart_orders: dict[str, dict[str, Any]] = {}
        self._smart_orders_lock = threading.RLock()
        self._dispatch_metrics_lock = threading.RLock()
        self._dispatch_seq = 0
        self._dispatch_queue_maxsize = max(10, int(getattr(self.cfg, "order_dispatch_queue_size", 500) or 500))
        self._dispatch_submit_interval_ms = max(0, int(getattr(self.cfg, "order_submit_interval_ms", 50) or 50))
        self._dispatch_queue: queue.PriorityQueue[tuple[int, int, dict[str, Any]]] = queue.PriorityQueue(
            maxsize=self._dispatch_queue_maxsize
        )
        self._dispatch_enqueued = 0
        self._dispatch_dropped = 0
        self._dispatch_processed = 0
        self._dispatch_max_queue_depth = 0
        self._dispatch_last_queue_wait_ms = 0
        self._dispatch_last_submit_at: Optional[float] = None
        self._dispatch_last_submit_kind = ""
        self._watchdog_interval_seconds = max(3, min(10, int(self.cfg.reconnect_interval_seconds or 5)))
        self._schedule_lock = threading.RLock()
        self.schedule_policy = SchedulePolicy()
        self._schedule_mode = "unknown"
        self._schedule_message = (
            f"当前为非交易时段，保持连接并按 30 分钟低频上报（交易时段：{self.schedule_policy.trading_session_label}）"
        )
        self._startup_grace_seconds = max(
            20,
            int(self.cfg.heartbeat_interval_seconds or 15) * 3,
            int(getattr(self.cfg, "account_report_interval_seconds", 30) or 30) * 2,
        )
        self._dispatch_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(5, int(getattr(self.cfg, "dispatch_workers", 10) or 10)),
            thread_name_prefix="dispatch-worker"
        )
        self._workers = {
            "session": SessionWorker(self),
            "heartbeat": HeartbeatWorker(self),
            "bridge": BridgeConnectionWorker(self),
            "account": AccountReporterWorker(self),
            "lifecycle": OrderLifecycleMonitor(self),
            "smart_execution": SmartExecutionWorker(self),
            "dispatch": OrderDispatcher(self),
            "reconnect": ReconnectWorker(self),
            "schedule": ScheduleWorker(self),
            "health": RuntimeHealthMonitor(self),
        }

    def _get_schedule_policy(self) -> SchedulePolicy:
        policy = getattr(self, "schedule_policy", None)
        if policy is None:
            policy = SchedulePolicy()
            self.schedule_policy = policy
        return policy

    def _is_trading_session(self, now: Optional[datetime] = None) -> bool:
        return self._get_schedule_policy().is_trading_session(now)

    def _current_reporting_mode(self, now: Optional[datetime] = None) -> str:
        return self._get_schedule_policy().current_reporting_mode(now)

    def _seconds_until_schedule_transition(self, now: Optional[datetime] = None) -> int:
        return self._get_schedule_policy().seconds_until_transition(now)

    def _schedule_wait_seconds(self, trading_session: bool) -> int:
        return self._get_schedule_policy().schedule_wait_seconds(trading_session)

    def _effective_report_interval_seconds(self, base_seconds: int) -> int:
        return self._get_schedule_policy().effective_report_interval_seconds(base_seconds)

    def _report_wait_seconds(self, base_seconds: int) -> int:
        return self._get_schedule_policy().report_wait_seconds(base_seconds)

    def _refresh_schedule_state(self) -> bool:
        mode = self._current_reporting_mode()
        with self._schedule_lock:
            previous_mode = self._schedule_mode
            self._schedule_mode = mode

        if mode == previous_mode:
            return mode == "trading"
        if mode == "trading":
            logger.info("进入交易时段，恢复高频账户/心跳上报: %s", self._get_schedule_policy().trading_session_label)
            if not self.qmt.is_connected():
                self.qmt.request_reconnect()
        else:
            logger.info("进入非交易时段，保持连接并切换为 30 分钟低频上报")
        return mode == "trading"

    def _build_schedule_rejection(self, payload: dict[str, Any], *, action: str) -> dict[str, Any]:
        message = f"{action}已拒绝：当前为非交易时段，仅允许 {self._get_schedule_policy().trading_session_label} 提交交易请求"
        return {
            "client_order_id": str(payload.get("client_order_id") or "").strip(),
            "exchange_order_id": None,
            "exchange_trade_id": None,
            "account_id": self.cfg.account_id,
            "symbol": payload.get("symbol"),
            "side": payload.get("side"),
            "status": "REJECTED",
            "filled_quantity": 0.0,
            "filled_price": None,
            "message": message,
        }

    def _next_dispatch_seq(self) -> int:
        with self._dispatch_metrics_lock:
            self._dispatch_seq += 1
            return self._dispatch_seq

    def _dispatch_metrics_snapshot(self) -> dict[str, Any]:
        dispatch_queue = getattr(self, "_dispatch_queue", None)
        queue_size = dispatch_queue.qsize() if dispatch_queue is not None else 0
        queue_maxsize = getattr(self, "_dispatch_queue_maxsize", 0)
        with getattr(self, "_dispatch_metrics_lock", self._state_lock):
            return {
                "queue_size": queue_size,
                "queue_maxsize": queue_maxsize,
                "enqueued": int(getattr(self, "_dispatch_enqueued", 0) or 0),
                "dropped": int(getattr(self, "_dispatch_dropped", 0) or 0),
                "processed": int(getattr(self, "_dispatch_processed", 0) or 0),
                "max_queue_depth": int(getattr(self, "_dispatch_max_queue_depth", 0) or 0),
                "last_queue_wait_ms": int(getattr(self, "_dispatch_last_queue_wait_ms", 0) or 0),
                "last_submit_at": getattr(self, "_dispatch_last_submit_at", None),
                "last_submit_kind": str(getattr(self, "_dispatch_last_submit_kind", "") or ""),
                "submit_interval_ms": int(getattr(self, "_dispatch_submit_interval_ms", 0) or 0),
            }

    def _enqueue_dispatch(self, kind: str, payload: dict[str, Any], priority: int) -> bool:
        item = {
            "kind": kind,
            "payload": dict(payload or {}),
            "enqueued_at": time.time(),
        }
        dispatch_queue = self._dispatch_queue
        try:
            dispatch_queue.put_nowait((priority, self._next_dispatch_seq(), item))
        except queue.Full:
            with self._dispatch_metrics_lock:
                self._dispatch_dropped += 1
            message = f"QMT Agent 派单队列已满({self._dispatch_queue_maxsize})，请稍后重试"
            logger.warning("%s kind=%s client_order_id=%s", message, kind, payload.get("client_order_id"))
            if kind == "order":
                try:
                    self.reporter.report_execution(
                        {
                            "client_order_id": payload.get("client_order_id"),
                            "exchange_order_id": None,
                            "exchange_trade_id": None,
                            "account_id": self.cfg.account_id,
                            "symbol": payload.get("symbol"),
                            "side": payload.get("side"),
                            "status": "REJECTED",
                            "filled_quantity": 0.0,
                            "filled_price": None,
                            "message": message,
                        }
                    )
                except Exception:
                    logger.exception("report queue-full rejection failed")
            return False

        with self._dispatch_metrics_lock:
            self._dispatch_enqueued += 1
            self._dispatch_max_queue_depth = max(self._dispatch_max_queue_depth, dispatch_queue.qsize())
        return True

    def _recover_pending_client_order_id(self, payload: dict[str, Any]) -> str:
        symbol = str(payload.get("symbol") or "").strip()
        side = str(payload.get("side") or "").strip().upper()
        if not symbol or side not in {"BUY", "SELL"}:
            return ""
        now = time.time()
        recent_candidates: list[tuple[str, dict[str, Any]]] = []
        max_age = max(30, int(getattr(self.cfg, "reconcile_cancel_after_seconds", 60) or 60) * 3)
        with self._pending_orders_lock:
            pending_snapshot = list(self._pending_orders.items())
        for client_order_id, order in pending_snapshot:
            submitted_at = float(order.get("submitted_at") or 0.0)
            if submitted_at <= 0 or now - submitted_at > max_age:
                continue
            if str(order.get("symbol") or "").strip() != symbol:
                continue
            if str(order.get("side") or "").strip().upper() != side:
                continue
            recent_candidates.append((client_order_id, order))

        if len(recent_candidates) != 1:
            return ""
        return str(recent_candidates[0][0] or "").strip()

    def _run_startup_reconcile(self) -> None:
        reconcile_timeout = max(5, min(30, int(getattr(self.cfg, "reconcile_timeout_seconds", 10) or 10)))
        events = None
        try:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="reconcile")
            future = executor.submit(self.qmt.reconcile_recent_activity)
            try:
                events = future.result(timeout=reconcile_timeout)
            except concurrent.futures.TimeoutError:
                logger.warning("startup reconcile timed out after %ss, skipping", reconcile_timeout)
                executor.shutdown(wait=False)
                return
            finally:
                executor.shutdown(wait=False)
        except Exception as exc:
            logger.warning("startup reconcile failed: %s", exc)
            return

        if not events:
            logger.info("startup reconcile: no historical order/trade events")
            return

        success = 0
        for event in events:
            try:
                self.reporter.report_execution(event)
                success += 1
            except Exception:
                logger.exception("startup reconcile report failed: %s", event.get("client_order_id"))
        with self._state_lock:
            if success > 0:
                self.last_execution_at = time.time()
        logger.info("startup reconcile reported %s/%s events", success, len(events))

    def _handle_qmt_event(self, payload: dict[str, Any]) -> None:
        event_type = payload.get("type", "execution")
        if event_type in {"asset_updated", "positions_updated"}:
            logger.debug("QMT state change detected: %s, triggering snapshot report", event_type)
            self._dirty_event.set()
            return

        if event_type == "cancel_error":
            logger.warning(
                "QMT cancel_error received: exchange_order_id=%s message=%s",
                payload.get("exchange_order_id", ""),
                payload.get("message", ""),
            )
            return

        exchange_order_id = str(payload.get("exchange_order_id") or "").strip()
        client_order_id = self.qmt.resolve_client_order_id(
            payload.get("client_order_id"),
            exchange_order_id,
            payload.get("seq"),
        )
        if not self.qmt.is_valid_client_order_id(client_order_id):
            client_order_id = self._recover_pending_client_order_id(payload)
            if self.qmt.is_valid_client_order_id(client_order_id):
                logger.info(
                    "recovered client_order_id from pending order: client_order_id=%s exchange_order_id=%s symbol=%s side=%s",
                    client_order_id,
                    exchange_order_id,
                    str(payload.get("symbol") or "").strip(),
                    str(payload.get("side") or "").strip(),
                )
        if not self.qmt.is_valid_client_order_id(client_order_id):
            if not self.qmt.is_valid_exchange_order_id(exchange_order_id):
                logger.warning("skip execution callback without resolvable ids: %s", payload)
                return
            payload["client_order_id"] = ""
        else:
            payload["client_order_id"] = client_order_id
            if self.qmt.is_valid_exchange_order_id(exchange_order_id):
                self.qmt.bind_exchange_order_id(client_order_id, exchange_order_id)
                with self._pending_orders_lock:
                    pending = self._pending_orders.get(client_order_id)
                    if pending is not None:
                        pending["exchange_order_id"] = exchange_order_id
        status = str(payload.get("status") or "").strip().upper()

        # Handle Sub-orders for Smart Execution
        main_client_order_id = client_order_id
        is_sub_order = False
        if client_order_id and "_" in client_order_id:
            potential_main = client_order_id.split("_")[0]
            with self._smart_orders_lock:
                if potential_main in self._smart_orders:
                    main_client_order_id = potential_main
                    is_sub_order = True

        if is_sub_order:
            with self._smart_orders_lock:
                so = self._smart_orders.get(main_client_order_id)
                if so and so.get("current_sub_client_order_id") == client_order_id:
                    if status in {"CANCELLED", "PARTIALLY_CANCELLED", "REJECTED"}:
                        filled = float(payload.get("filled_quantity") or 0.0)
                        so["remaining_quantity"] -= filled
                        so["remaining_quantity"] = max(0.0, so["remaining_quantity"])
                        if so["remaining_quantity"] <= 0:
                            self._smart_orders.pop(main_client_order_id, None)
                        else:
                            so["state"] = "pending"
                            so["last_action_ts"] = time.time()
                    elif status == "PARTIALLY_FILLED":
                        filled = float(payload.get("filled_quantity") or 0.0)
                        original_qty = float(so.get("original_payload", {}).get("quantity") or 0)
                        so["remaining_quantity"] = max(0.0, original_qty - filled)
                    elif status == "FILLED":
                        so["remaining_quantity"] = 0
                        self._smart_orders.pop(main_client_order_id, None)

            # Map the response back to parent id for reporter
            payload["client_order_id"] = main_client_order_id

        if self.qmt.is_valid_client_order_id(client_order_id) and status in {
            "FILLED",
            "REJECTED",
            "CANCELLED",
            "PARTIALLY_CANCELLED",
            "EXPIRED",
        }:
            with self._pending_orders_lock:
                self._pending_orders.pop(client_order_id, None)
                if is_sub_order:
                    self._pending_orders.pop(main_client_order_id, None)

        try:
            self.reporter.report_execution(payload)
            with self._state_lock:
                self.last_execution_at = time.time()
        except Exception:
            with self._state_lock:
                self.last_error = "execution callback report failed"
            logger.exception("execution callback report failed")

    def _wait_for_snapshot_settle(self, settle_seconds: int, max_wait_seconds: int | None = None) -> bool:
        settle_seconds = max(1, int(settle_seconds or 1))
        settle_deadline = time.time() + settle_seconds
        hard_deadline = None
        if max_wait_seconds is not None:
            hard_deadline = time.time() + max(1, int(max_wait_seconds))
        while not self.stop_event.is_set():
            now = time.time()
            if hard_deadline is not None and now >= hard_deadline:
                return True
            remaining = settle_deadline - now
            if remaining <= 0:
                return True
            if self._dirty_event.wait(timeout=remaining):
                self._dirty_event.clear()
                settle_deadline = time.time() + settle_seconds
        return False

    def on_open(self, _ws) -> None:
        logger.info("bridge websocket connected")
        with self._state_lock:
            self.runtime_state = "running"
            self.last_bridge_connect_at = time.time()
            self.last_error = None

    def _process_order_message(self, payload: dict[str, Any]) -> None:
        logger.debug("on_message received complete payload: %s", json.dumps(payload, ensure_ascii=False))
        logger.info("received order client_order_id=%s", payload.get("client_order_id"))
        if not self._refresh_schedule_state():
            self.reporter.report_execution(self._build_schedule_rejection(payload, action="下单"))
            return

        dispatch_mode = str(payload.get("dispatch_mode") or "").strip().lower()
        order_type_str = str(payload.get("order_type") or "").strip().upper()
        is_smart = dispatch_mode == "smart" or (
            order_type_str == "MARKET" and bool(self.cfg.enable_smart_for_market)
        )
        if is_smart and bool(self.cfg.enable_smart_execution):
            client_order_id = str(payload.get("client_order_id") or "").strip()
            if client_order_id:
                with self._smart_orders_lock:
                    self._smart_orders[client_order_id] = {
                        "original_payload": payload,
                        "remaining_quantity": float(payload.get("quantity") or 0),
                        "current_exchange_order_id": None,
                        "current_sub_client_order_id": None,
                        "state": "pending",
                        "retries": 0,
                        "last_action_ts": time.time(),
                    }
                logger.info("smart order accepted: %s", client_order_id)
                try:
                    self.reporter.report_execution({
                        "client_order_id": client_order_id,
                        "exchange_order_id": None,
                        "account_id": self.cfg.account_id,
                        "symbol": payload.get("symbol"),
                        "side": payload.get("side"),
                        "status": "ACCEPTED",
                        "filled_quantity": 0.0,
                        "message": "smart execution tracking engaged",
                    })
                except Exception:
                    pass
                return

        try:
            use_async = bool(payload.get("async")) or dispatch_mode == "async"
            result = self.qmt.submit_order_async(payload) if use_async else self.qmt.submit_order(payload)
            logger.debug("submit_order/submit_order_async returned: %s", json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            logger.exception("order execution failed: %s", exc)
            self.reporter.report_execution(
                {
                    "client_order_id": payload.get("client_order_id"),
                    "exchange_order_id": None,
                    "exchange_trade_id": None,
                    "account_id": self.cfg.account_id,
                    "symbol": payload.get("symbol"),
                    "side": payload.get("side"),
                    "status": "REJECTED",
                    "filled_quantity": 0.0,
                    "filled_price": None,
                    "message": str(exc),
                    "execution_meta": self.qmt.resolve_execution_meta(
                        client_order_id=payload.get("client_order_id"),
                    ),
                }
            )
            return
        execution_meta = result.get("execution_meta")
        if isinstance(execution_meta, dict):
            logger.info(
                "order execution meta client_order_id=%s mode=%s requested=%s effective=%s effective_price=%s",
                result.get("client_order_id"),
                execution_meta.get("execution_mode"),
                execution_meta.get("requested_order_type"),
                execution_meta.get("effective_order_type"),
                execution_meta.get("effective_price"),
            )
        try:
            logger.debug("about to report_execution with payload: %s", json.dumps(result, ensure_ascii=False))
            self.reporter.report_execution(result)
            logger.info("report_execution succeeded for client_order_id=%s", result.get("client_order_id"))
        except Exception as exc:
            logger.exception("report_execution failed: %s", exc)

        if str(result.get("status") or "").strip().upper() in {"SUBMITTED", "PARTIALLY_FILLED"}:
            client_order_id = str(result.get("client_order_id") or "").strip()
            exchange_order_id = str(result.get("exchange_order_id") or "").strip()
            if client_order_id:
                with self._pending_orders_lock:
                    self._pending_orders[client_order_id] = {
                        "client_order_id": client_order_id,
                        "exchange_order_id": exchange_order_id or "",
                        "symbol": str(result.get("symbol") or "").strip(),
                        "side": str(result.get("side") or "").strip(),
                        "submitted_at": time.time(),
                        "last_status": str(result.get("status") or "").strip().upper(),
                        "execution_meta": execution_meta if isinstance(execution_meta, dict) else None,
                    }

    def _process_cancel_message(self, payload: dict[str, Any]) -> None:
        if not self._refresh_schedule_state():
            logger.info("cancel skipped due to non-trading session: client_order_id=%s", payload.get("client_order_id"))
            return
        client_order_id = str(payload.get("client_order_id") or "").strip()
        provided_exchange_order_id = str(payload.get("exchange_order_id") or "").strip()
        exchange_order_id = self.qmt.resolve_exchange_order_id(
            provided_exchange_order_id,
            client_order_id=client_order_id,
        )
        logger.info("received cancel client_order_id=%s exchange_order_id=%s", client_order_id, exchange_order_id)
        try:
            if not exchange_order_id:
                raise ValueError("missing resolvable exchange_order_id for cancel request")
            use_async = bool(payload.get("async")) or str(payload.get("dispatch_mode") or "").strip().lower() == "async"
            cancel_result = (
                self.qmt.cancel_order_async(exchange_order_id, client_order_id=client_order_id)
                if use_async
                else self.qmt.cancel_order(exchange_order_id)
            )
            if cancel_result.get("accepted"):
                logger.info(
                    "cancel request accepted by qmt: client_order_id=%s exchange_order_id=%s",
                    client_order_id,
                    exchange_order_id,
                )
            else:
                logger.warning(
                    "cancel request rejected by qmt: client_order_id=%s exchange_order_id=%s code=%s",
                    client_order_id,
                    exchange_order_id,
                    cancel_result.get("code") or cancel_result.get("seq"),
                )
        except Exception as exc:
            logger.exception("cancel order failed: %s", exc)

    def on_message(self, _ws, message: str) -> None:
        data = json.loads(message)
        msg_type = data.get("type")
        if msg_type == "order":
            payload = data.get("payload", {}) or {}
            self._enqueue_dispatch("order", payload, priority=1)
        elif msg_type == "cancel":
            payload = data.get("payload", {}) or {}
            self._enqueue_dispatch("cancel", payload, priority=0)

    def on_error(self, _ws, error: Any) -> None:
        with self._state_lock:
            self.last_error = str(error)
        logger.warning("bridge websocket error: %s", error)

    def on_close(self, _ws, code: Any, msg: Any) -> None:
        with self._state_lock:
            if not self.stop_event.is_set():
                self.runtime_state = "reconnecting"
        logger.warning("bridge websocket closed: code=%s msg=%s", code, msg)

    def _refresh_loop(self) -> None:
        self._workers["session"].run()

    def _heartbeat_loop(self) -> None:
        self._workers["heartbeat"].run()

    def _ws_app_ping_loop(self) -> None:
        self._workers["bridge"].run_ping_loop()

    def _account_loop(self) -> None:
        self._workers["account"].run()

    def _order_timeout_loop(self) -> None:
        self._workers["lifecycle"].run_timeout_loop()

    def _smart_execution_loop(self) -> None:
        self._workers["smart_execution"].run()

    def _close_ws(self) -> None:
        with self._ws_lock:
            ws = self.ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run_ws_forever(self) -> None:
        self._workers["bridge"].run_ws_forever()

    def _thread_target_guard(self, name: str, target: Any) -> Any:
        def _runner(*args: Any, **kwargs: Any) -> Any:
            logger.info("background thread started: %s", name)
            try:
                return target(*args, **kwargs)
            except BaseException as exc:
                with self._state_lock:
                    self.last_error = f"{name} crashed: {exc}"
                logger.exception("background thread crashed: %s", name)
                raise
            finally:
                logger.info("background thread exited: %s", name)

        return _runner

    def _spawn_background_thread(self, name: str, target: Any, *args: Any) -> threading.Thread:
        thread = threading.Thread(
            target=self._thread_target_guard(name, target),
            name=name,
            args=args,
            daemon=True,
        )
        with self._state_lock:
            self._threads[name] = thread
        thread.start()
        return thread

    @staticmethod
    def _age_seconds(value: Optional[float]) -> float:
        if not value:
            return float("inf")
        return max(0.0, time.time() - float(value))

    @staticmethod
    def _format_age_reason(label: str, age_seconds: float) -> str:
        if not math.isfinite(age_seconds):
            return f"{label}(未上报)"
        return f"{label}({int(age_seconds)}s)"

    def _runtime_health_snapshot(self) -> dict[str, Any]:
        schedule_policy = self._get_schedule_policy()
        with self._schedule_lock:
            schedule_mode = self._schedule_mode if self._schedule_mode in {"trading", "offhours"} else self._current_reporting_mode()
        heartbeat_interval = max(1, int(self.cfg.heartbeat_interval_seconds or 15))
        account_interval = max(1, int(getattr(self.cfg, "account_report_interval_seconds", 30) or 30))
        if schedule_mode != "trading":
            heartbeat_interval = max(heartbeat_interval, int(schedule_policy.offhours_report_interval_seconds))
            account_interval = max(account_interval, int(schedule_policy.offhours_report_interval_seconds))
        heartbeat_age = self._age_seconds(self.last_heartbeat_at)
        account_age = self._age_seconds(self.last_account_report_at)
        startup_age = self._age_seconds(self.last_start_at)
        in_startup_grace = startup_age <= float(self._startup_grace_seconds)
        dispatch_metrics = self._dispatch_metrics_snapshot()
        with self._state_lock:
            thread_items = list(self._threads.items())
        thread_states = {name: thread.is_alive() for name, thread in thread_items}
        critical_threads = [
            "bridge-websocket",
            "bridge-refresh",
            "bridge-heartbeat",
            "bridge-account",
            "bridge-order-timeout",
            "bridge-order-dispatch",
            "bridge-smart-execution",
            "bridge-app-ping",
            "bridge-watchdog",
            "qmt-schedule",
        ]
        dead_threads = [name for name in critical_threads if not thread_states.get(name, False)]
        reasons: list[str] = []
        if (not in_startup_grace) and heartbeat_age > heartbeat_interval * 2:
            reasons.append(self._format_age_reason("heartbeat_stale", heartbeat_age))
        if (not in_startup_grace) and account_age > account_interval * 2:
            reasons.append(self._format_age_reason("account_stale", account_age))
        if dead_threads:
            reasons.append(f"thread_dead({','.join(dead_threads)})")
        queue_size = int(dispatch_metrics.get("queue_size") or 0)
        queue_maxsize = max(1, int(dispatch_metrics.get("queue_maxsize") or 1))
        if queue_size >= max(10, math.ceil(queue_maxsize * 0.8)):
            reasons.append(f"dispatch_queue_busy({queue_size}/{queue_maxsize})")
        if int(dispatch_metrics.get("dropped") or 0) > 0:
            reasons.append(f"dispatch_queue_dropped({int(dispatch_metrics.get('dropped') or 0)})")
        if not reasons:
            health = "healthy"
        elif dead_threads:
            health = "degraded"
        elif any(reason.startswith("dispatch_queue_") for reason in reasons):
            health = "degraded"
        else:
            health = "stale"
        return {
            "health": health,
            "health_reason": ";".join(reasons) if reasons else "",
            "heartbeat_interval_seconds": heartbeat_interval,
            "account_report_interval_seconds": account_interval,
            "heartbeat_age_seconds": None if not math.isfinite(heartbeat_age) else int(heartbeat_age),
            "account_age_seconds": None if not math.isfinite(account_age) else int(account_age),
            "startup_age_seconds": None if not math.isfinite(startup_age) else int(startup_age),
            "startup_grace_seconds": int(self._startup_grace_seconds),
            "in_startup_grace": bool(in_startup_grace),
            "schedule_mode": schedule_mode,
            "schedule_window_label": schedule_policy.trading_session_label,
            "offhours_report_interval_seconds": int(schedule_policy.offhours_report_interval_seconds),
            "worker_threads": thread_states,
            "dispatch_metrics": dispatch_metrics,
        }

    def _order_dispatch_loop(self) -> None:
        self._workers["dispatch"].run()

    def _dispatch_task_wrapper(self, priority: int, seq: int, item: dict[str, Any]) -> None:
        started_at = time.time()
        wait_ms = max(0, int((started_at - float(item.get("enqueued_at") or started_at)) * 1000))
        kind = str(item.get("kind") or "")
        payload = dict(item.get("payload") or {})
        try:
            if kind == "cancel":
                self._process_cancel_message(payload)
            else:
                self._process_order_message(payload)
        except Exception as exc:
            logger.exception("dispatch task crashed: kind=%s, error=%s", kind, exc)
        finally:
            with self._dispatch_metrics_lock:
                self._dispatch_processed += 1
                self._dispatch_last_queue_wait_ms = wait_ms
                self._dispatch_last_submit_at = started_at
                self._dispatch_last_submit_kind = kind
            self._dispatch_queue.task_done()

    def _ensure_background_threads(self) -> None:
        desired = {
            "bridge-refresh": self._refresh_loop,
            "bridge-heartbeat": self._heartbeat_loop,
            "bridge-account": self._account_loop,
            "bridge-order-timeout": self._order_timeout_loop,
            "bridge-order-dispatch": self._order_dispatch_loop,
            "bridge-smart-execution": self._smart_execution_loop,
            "bridge-app-ping": self._ws_app_ping_loop,
            "qmt-reconnect": self._qmt_reconnect_loop,
            "qmt-schedule": self._qmt_schedule_loop,
            "bridge-websocket": self._run_ws_forever,
            "bridge-watchdog": self._watchdog_loop,
        }
        with self._state_lock:
            existing_threads = dict(self._threads)
        for name, target in desired.items():
            existing = existing_threads.get(name)
            if existing is not None and existing.is_alive():
                continue
            if name == "qmt-reconnect":
                self._spawn_background_thread(name, target, self.stop_event)
            else:
                self._spawn_background_thread(name, target)

    def _qmt_reconnect_loop(self, stop_event: threading.Event) -> None:
        self._workers["reconnect"].run(stop_event)

    def _qmt_schedule_loop(self) -> None:
        self._workers["schedule"].run()

    def _watchdog_loop(self) -> None:
        self._workers["health"].run()

    def start(self) -> None:
        self.stop_event.clear()
        with self._state_lock:
            self._threads = {}
        with self._state_lock:
            self.last_error = None
            self.last_start_at = time.time()
        self.auth.bootstrap()
        self._refresh_schedule_state()
        if not self.qmt.connect():
            logger.warning("QMT initial connection failed, heartbeat will report disconnected state")
            with self._state_lock:
                self.runtime_state = "degraded"
                self.last_error = "QMT initial connection failed"
        else:
            with self._state_lock:
                self.runtime_state = "starting"

        bootstrap_snapshot = None
        try:
            bootstrap_snapshot = self.qmt.snapshot(prefer_fresh=True)
        except Exception as exc:
            logger.warning("initial account snapshot unavailable: %s", exc)
        if bootstrap_snapshot is not None:
            try:
                self.reporter.report_account(bootstrap_snapshot)
                with self._state_lock:
                    self.last_account_report_at = time.time()
            except Exception as exc:
                logger.warning("initial account report failed: %s", exc)
        try:
            self.reporter.report_heartbeat(
                {
                    "account_id": self.cfg.account_id,
                    "client_version": self.cfg.client_version,
                    "hostname": self.cfg.hostname,
                    "status": "running",
                    "qmt_connected": self.qmt.is_connected(),
                    "latency_ms": 0,
                }
            )
            with self._state_lock:
                self.last_heartbeat_at = time.time()
        except Exception as exc:
            logger.warning("initial heartbeat report failed: %s", exc)
        self._run_startup_reconcile()

        self._spawn_background_thread("bridge-refresh", self._refresh_loop)
        self._spawn_background_thread("bridge-heartbeat", self._heartbeat_loop)
        self._spawn_background_thread("bridge-account", self._account_loop)
        self._spawn_background_thread("bridge-order-timeout", self._order_timeout_loop)
        self._spawn_background_thread("bridge-order-dispatch", self._order_dispatch_loop)
        self._spawn_background_thread("bridge-smart-execution", self._smart_execution_loop)
        self._spawn_background_thread("bridge-app-ping", self._ws_app_ping_loop)
        self._spawn_background_thread("qmt-reconnect", self._qmt_reconnect_loop, self.stop_event)
        self._spawn_background_thread("qmt-schedule", self._qmt_schedule_loop)
        self._spawn_background_thread("bridge-websocket", self._run_ws_forever)
        self._spawn_background_thread("bridge-watchdog", self._watchdog_loop)

    def run_forever(
        self,
        external_stop_event: Optional[threading.Event] = None,
        poll_interval_seconds: float = 0.2,
    ) -> None:
        self.start()
        poll_interval = max(0.1, float(poll_interval_seconds or 0.2))
        while not self.stop_event.wait(poll_interval):
            if external_stop_event is not None and external_stop_event.is_set():
                break

    def stop(self) -> None:
        self.stop_event.set()
        self._close_ws()
        self.qmt.close()
        if hasattr(self, "_dispatch_executor"):
            self._dispatch_executor.shutdown(wait=False)
        with self._state_lock:
            self.runtime_state = "stopped"

    def get_runtime_status(self) -> dict[str, Any]:
        with self._state_lock:
            thread_states = {name: thread.is_alive() for name, thread in self._threads.items()}
        health = self._runtime_health_snapshot()
        with self._state_lock:
            return {
                "runtime_state": self.runtime_state,
                "runtime_health": health.get("health"),
                "runtime_health_reason": health.get("health_reason"),
                "qmt_connected": self.qmt.is_connected(),
                "last_error": self.last_error,
                "last_start_at": self.last_start_at,
                "last_heartbeat_at": self.last_heartbeat_at,
                "last_account_report_at": self.last_account_report_at,
                "heartbeat_age_seconds": health.get("heartbeat_age_seconds"),
                "account_age_seconds": health.get("account_age_seconds"),
                "last_bridge_connect_at": self.last_bridge_connect_at,
                "last_execution_at": self.last_execution_at,
                "hostname": self.cfg.hostname,
                "client_fingerprint": self.cfg.client_fingerprint,
                "client_version": self.cfg.client_version,
                "account_id": self.cfg.account_id,
                "qmt_schedule_active": health.get("schedule_mode") == "trading",
                "qmt_schedule_mode": health.get("schedule_mode"),
                "qmt_schedule_window": health.get("schedule_window_label"),
                "offhours_report_interval_seconds": health.get("offhours_report_interval_seconds"),
                "worker_threads": thread_states,
                "dispatch_metrics": health.get("dispatch_metrics"),
            }
