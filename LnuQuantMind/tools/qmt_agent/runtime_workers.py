"""Background worker objects used by QMTAgent."""
from __future__ import annotations

import json
import logging
import math
import queue
import time
from typing import TYPE_CHECKING, Any

import websocket

if TYPE_CHECKING:
    from .agent import QMTAgent


logger = logging.getLogger("qmt_agent")


class SessionWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        while not self.agent.stop_event.is_set():
            try:
                refreshed = self.agent.auth.refresh_if_needed()
                if refreshed:
                    self.agent._close_ws()
            except Exception as exc:
                with self.agent._state_lock:
                    self.agent.last_error = f"session refresh failed: {exc}"
                logger.warning("session refresh failed: %s, attempting re-bootstrap", exc)
                try:
                    self.agent.auth.bootstrap()
                    logger.info("session re-bootstrap succeeded")
                except Exception as bootstrap_exc:
                    with self.agent._state_lock:
                        self.agent.last_error = f"session bootstrap failed: {bootstrap_exc}"
                    logger.warning("session re-bootstrap failed: %s", bootstrap_exc)
            self.agent.stop_event.wait(1)


class HeartbeatWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        base_interval = max(1, int(self.agent.cfg.heartbeat_interval_seconds or 15))
        while not self.agent.stop_event.is_set():
            self.agent._refresh_schedule_state()
            try:
                self.agent.reporter.report_heartbeat(
                    {
                        "account_id": self.agent.cfg.account_id,
                        "client_version": self.agent.cfg.client_version,
                        "hostname": self.agent.cfg.hostname,
                        "status": "running",
                        "qmt_connected": self.agent.qmt.is_connected(),
                        "latency_ms": 0,
                    }
                )
                with self.agent._state_lock:
                    self.agent.last_heartbeat_at = time.time()
            except Exception as exc:
                with self.agent._state_lock:
                    self.agent.last_error = f"heartbeat report failed: {exc}"
                logger.warning("heartbeat report failed: %s", exc)
            self.agent.stop_event.wait(self.agent._report_wait_seconds(base_interval))


class BridgeConnectionWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run_ping_loop(self) -> None:
        interval = max(10, int(self.agent.cfg.ws_ping_interval_seconds or 20))
        while not self.agent.stop_event.is_set():
            try:
                with self.agent._ws_lock:
                    ws = self.agent.ws
                if ws is not None:
                    ws.send(json.dumps({"type": "ping", "ts": time.time()}))
            except Exception:
                pass
            self.agent.stop_event.wait(interval)

    def run_ws_forever(self) -> None:
        while not self.agent.stop_event.is_set():
            try:
                headers = self.agent.auth.authorization_header()
                ws = websocket.WebSocketApp(
                    self.agent.cfg.server_url,
                    header=[f"{k}: {v}" for k, v in headers.items()],
                    on_open=self.agent.on_open,
                    on_message=self.agent.on_message,
                    on_error=self.agent.on_error,
                    on_close=self.agent.on_close,
                )
                with self.agent._ws_lock:
                    self.agent.ws = ws
                websocket.setdefaulttimeout(30)
                ws.run_forever()
            except Exception as exc:
                logger.warning("websocket loop failed: %s", exc)
            if self.agent.stop_event.is_set():
                break
            time.sleep(max(1, self.agent.cfg.reconnect_interval_seconds))


class AccountReporterWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        base_interval = max(1, int(getattr(self.agent.cfg, "account_report_interval_seconds", 30) or 30))
        settle_window = max(3, min(10, base_interval // 2))
        while not self.agent.stop_event.is_set():
            trading_session = self.agent._refresh_schedule_state()
            if trading_session:
                triggered = self.agent._dirty_event.wait(timeout=base_interval)
                self.agent._dirty_event.clear()
                max_settle_window = max(base_interval, settle_window * 3)
                if triggered and not self.agent._wait_for_snapshot_settle(settle_window, max_wait_seconds=max_settle_window):
                    continue
            else:
                if self.agent.stop_event.wait(self.agent._report_wait_seconds(base_interval)):
                    break

            try:
                snapshot = self.agent.qmt.snapshot(prefer_fresh=True)
                self.agent.reporter.report_account(snapshot)
                with self.agent._state_lock:
                    self.agent.last_account_report_at = time.time()
            except Exception as exc:
                with self.agent._state_lock:
                    self.agent.last_error = f"account report failed: {exc}"
                logger.warning("account report failed: %s", exc)
                if "QMT not connected" in str(exc):
                    self.agent.qmt.request_reconnect()


class OrderLifecycleMonitor:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run_timeout_loop(self) -> None:
        cancel_after_seconds = max(1, int(getattr(self.agent.cfg, "reconcile_cancel_after_seconds", 60) or 60))
        check_interval = min(10, max(3, cancel_after_seconds // 4))
        while not self.agent.stop_event.is_set():
            if not self.agent._refresh_schedule_state():
                self.agent.stop_event.wait(self.agent._schedule_wait_seconds(trading_session=False))
                continue
            now = time.time()
            stale_orders: list[dict[str, Any]] = []
            with self.agent._pending_orders_lock:
                pending_snapshot = list(self.agent._pending_orders.values())
            for order in pending_snapshot:
                client_order_id = str(order.get("client_order_id") or "").strip()
                exchange_order_id = str(order.get("exchange_order_id") or "").strip()
                submitted_at = float(order.get("submitted_at") or 0.0)
                if not client_order_id or not exchange_order_id or submitted_at <= 0:
                    continue
                if now - submitted_at < cancel_after_seconds:
                    continue
                if order.get("cancel_requested_at"):
                    continue
                stale_orders.append(order)

            for order in stale_orders:
                client_order_id = str(order.get("client_order_id") or "").strip()
                exchange_order_id = str(order.get("exchange_order_id") or "").strip()
                if not client_order_id or not exchange_order_id:
                    continue
                try:
                    logger.info(
                        "pending order timeout reached, issuing cancel client_order_id=%s exchange_order_id=%s age=%ss",
                        client_order_id,
                        exchange_order_id,
                        int(now - float(order.get("submitted_at") or now)),
                    )
                    cancel_result = self.agent.qmt.cancel_order(exchange_order_id)
                    if cancel_result.get("accepted"):
                        with self.agent._pending_orders_lock:
                            if client_order_id in self.agent._pending_orders:
                                self.agent._pending_orders[client_order_id]["cancel_requested_at"] = now
                                self.agent._pending_orders[client_order_id]["last_status"] = "CANCEL_PENDING"
                    else:
                        logger.warning(
                            "pending order cancel rejected client_order_id=%s exchange_order_id=%s code=%s",
                            client_order_id,
                            exchange_order_id,
                            cancel_result.get("code"),
                        )
                except Exception as exc:
                    logger.exception(
                        "pending order cancel failed client_order_id=%s exchange_order_id=%s: %s",
                        client_order_id,
                        exchange_order_id,
                        exc,
                    )
            self.agent.stop_event.wait(check_interval)


class SmartExecutionWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        while not self.agent.stop_event.is_set():
            if not self.agent._refresh_schedule_state():
                self.agent.stop_event.wait(self.agent._schedule_wait_seconds(trading_session=False))
                continue
            now = time.time()
            with self.agent._smart_orders_lock:
                snapshot = {k: dict(v) for k, v in self.agent._smart_orders.items()}

            for client_order_id, so in snapshot.items():
                if so["remaining_quantity"] <= 0:
                    with self.agent._smart_orders_lock:
                        self.agent._smart_orders.pop(client_order_id, None)
                    continue

                if so["state"] == "pending":
                    if so["retries"] >= int(self.agent.cfg.smart_max_retries):
                        logger.warning("smart execution max retries reached for %s", client_order_id)
                        original_qty = float(so.get("original_payload", {}).get("quantity") or 0)
                        filled_qty = max(0.0, original_qty - so["remaining_quantity"])
                        with self.agent._smart_orders_lock:
                            self.agent._smart_orders.pop(client_order_id, None)
                        try:
                            self.agent.reporter.report_execution({
                                "client_order_id": client_order_id,
                                "account_id": self.agent.cfg.account_id,
                                "symbol": so.get("original_payload", {}).get("symbol"),
                                "side": so.get("original_payload", {}).get("side"),
                                "status": "EXPIRED",
                                "message": "max smart retries reached",
                                "filled_quantity": filled_qty,
                            })
                        except Exception:
                            pass
                        continue

                    payload = so["original_payload"].copy()
                    symbol = payload.get("symbol")
                    side = payload.get("side")
                    price = self.agent.qmt.get_level1_price(symbol, side)
                    if price <= 0:
                        logger.warning("smart order got 0.0 price for %s, will retry next tick", client_order_id)
                        continue

                    new_retry = so["retries"] + 1
                    sub_client_id = f"{client_order_id}_{new_retry}"
                    payload["client_order_id"] = sub_client_id
                    payload["price"] = price
                    payload["order_type"] = "LIMIT"
                    payload["quantity"] = so["remaining_quantity"]

                    try:
                        logger.info("smart order %s submitting chunk %s at price %s", client_order_id, new_retry, price)
                        self.agent.qmt.submit_order_async(payload)
                        with self.agent._smart_orders_lock:
                            if client_order_id in self.agent._smart_orders:
                                self.agent._smart_orders[client_order_id]["retries"] = new_retry
                                self.agent._smart_orders[client_order_id]["current_sub_client_order_id"] = sub_client_id
                                self.agent._smart_orders[client_order_id]["state"] = "submitted"
                                self.agent._smart_orders[client_order_id]["last_action_ts"] = now
                    except Exception as e:
                        logger.error("smart order submit failed for %s: %s", client_order_id, e)

                elif so["state"] == "submitted":
                    timeout = int(self.agent.cfg.smart_timeout_seconds)
                    if now - so["last_action_ts"] > timeout:
                        exchange_order_id = self.agent.qmt.resolve_exchange_order_id("", so["current_sub_client_order_id"])
                        if exchange_order_id:
                            logger.info("smart order %s timeout, cancelling sub order: %s", client_order_id, exchange_order_id)
                            self.agent.qmt.cancel_order_async(exchange_order_id, so["current_sub_client_order_id"])
                            with self.agent._smart_orders_lock:
                                if client_order_id in self.agent._smart_orders:
                                    self.agent._smart_orders[client_order_id]["state"] = "cancelling"
                                    self.agent._smart_orders[client_order_id]["last_action_ts"] = now
                        else:
                            if now - so["last_action_ts"] > timeout + 5:
                                logger.warning("smart order %s sub order not found in QMT after timeout, resetting", client_order_id)
                                with self.agent._smart_orders_lock:
                                    if client_order_id in self.agent._smart_orders:
                                        self.agent._smart_orders[client_order_id]["state"] = "pending"

                elif so["state"] == "cancelling":
                    if now - so["last_action_ts"] > 15:
                        logger.warning("smart order %s stuck cancelling, forcing pending", client_order_id)
                        with self.agent._smart_orders_lock:
                            if client_order_id in self.agent._smart_orders:
                                self.agent._smart_orders[client_order_id]["state"] = "pending"

            self.agent.stop_event.wait(1.0)


class OrderDispatcher:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        dispatch_queue = self.agent._dispatch_queue
        submit_interval_seconds = float(self.agent._dispatch_submit_interval_ms) / 1000.0
        while not self.agent.stop_event.is_set():
            try:
                priority, seq, item = dispatch_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self.agent._dispatch_executor.submit(self.agent._dispatch_task_wrapper, priority, seq, item)
            if submit_interval_seconds > 0 and not self.agent.stop_event.is_set():
                self.agent.stop_event.wait(submit_interval_seconds)


class ReconnectWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self, stop_event: Any) -> None:
        self.agent.qmt.reconnect_if_needed(stop_event)


class ScheduleWorker:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        while not self.agent.stop_event.is_set():
            trading_session = self.agent._refresh_schedule_state()
            self.agent.stop_event.wait(self.agent._schedule_wait_seconds(trading_session=trading_session))


class RuntimeHealthMonitor:
    def __init__(self, agent: "QMTAgent") -> None:
        self.agent = agent

    def run(self) -> None:
        while not self.agent.stop_event.is_set():
            try:
                self.agent._ensure_background_threads()
                health = self.agent._runtime_health_snapshot()
                reason = str(health.get("health_reason") or "")
                if reason:
                    with self.agent._state_lock:
                        self.agent.runtime_state = "degraded" if health.get("health") != "healthy" else self.agent.runtime_state
                        self.agent.last_error = reason
                    logger.warning("runtime watchdog detected issue: %s", reason)
                    if ("heartbeat_stale" in reason or "account_stale" in reason) and not bool(health.get("in_startup_grace")):
                        self.agent.qmt.request_reconnect()
            except Exception as exc:
                with self.agent._state_lock:
                    self.agent.last_error = f"watchdog failed: {exc}"
                logger.exception("runtime watchdog failed")
            self.agent.stop_event.wait(self.agent._watchdog_interval_seconds)
