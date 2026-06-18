from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any

from backend.services.trade.redis_client import RedisClient

logger = logging.getLogger(__name__)


class SimulationRuntimeRestorer:
    """Restore simulation sandbox workers from active strategy state after trade restarts."""

    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def restore_all(self) -> int:
        if not self.redis.client:
            return 0

        restored = 0
        for raw_key in self.redis.client.scan_iter(
            match="trade:active_strategy:*", count=500
        ):
            try:
                restored += 1 if await self.restore_key(str(raw_key)) else 0
            except Exception as exc:
                logger.warning(
                    "simulation runtime restore skipped key=%s error=%s",
                    raw_key,
                    exc,
                    exc_info=True,
                )
        if restored > 0:
            logger.info("simulation runtime restored active sandboxes: %s", restored)
        return restored

    async def restore_key(self, key: str) -> bool:
        raw = self.redis.client.get(key)
        if not raw:
            return False
        try:
            active_data = json.loads(raw)
        except Exception:
            return False
        if not isinstance(active_data, dict):
            return False
        if str(active_data.get("mode") or "").upper() != "SIMULATION":
            return False

        parts = key.split(":")
        if len(parts) < 4:
            return False
        tenant_id = parts[-2].strip() or "default"
        user_id = parts[-1].strip()
        return await self.restore_active_payload(
            tenant_id=tenant_id,
            user_id=user_id,
            active_data=active_data,
        )

    async def restore_active_payload(
        self,
        *,
        tenant_id: str,
        user_id: str,
        active_data: dict[str, Any],
    ) -> bool:
        strategy_id = str(active_data.get("strategy_id") or "").strip()
        if not strategy_id:
            return False

        from backend.services.trade.sandbox.manager import sandbox_manager

        if sandbox_manager.is_strategy_running(tenant_id, user_id, strategy_id):
            return False

        code_str = await self._resolve_code(strategy_id=strategy_id, user_id=user_id)
        if not code_str.strip():
            logger.warning(
                "simulation runtime restore skipped missing code: tenant=%s user=%s strategy=%s",
                tenant_id,
                user_id,
                strategy_id,
            )
            return False

        exec_config = (
            dict(active_data.get("execution_config"))
            if isinstance(active_data.get("execution_config"), dict)
            else {}
        )
        live_trade_config = (
            dict(active_data.get("live_trade_config"))
            if isinstance(active_data.get("live_trade_config"), dict)
            else {}
        )
        sandbox_run_id = sandbox_manager.submit_strategy(
            tenant_id=tenant_id,
            user_id=user_id,
            strategy_id=strategy_id,
            code_str=code_str,
            exec_config=exec_config,
            live_trade_config=live_trade_config,
        )
        active_data["sandbox_restored_run_id"] = sandbox_run_id
        try:
            self.redis.client.set(
                f"trade:active_strategy:{tenant_id}:{str(user_id).zfill(8)}",
                json.dumps(active_data, ensure_ascii=False),
            )
        except Exception:
            pass
        logger.info(
            "simulation sandbox restored: tenant=%s user=%s strategy=%s run_id=%s",
            tenant_id,
            user_id,
            strategy_id,
            sandbox_run_id,
        )
        return True

    async def _resolve_code(self, *, strategy_id: str, user_id: str) -> str:
        if strategy_id.startswith("sys_"):
            template_id = strategy_id.replace("sys_", "", 1)
            try:
                from backend.services.engine.qlib_app.services.strategy_templates import (
                    get_template_by_id,
                )

                template = get_template_by_id(template_id)
                return str(getattr(template, "code", "") or "")
            except Exception:
                return ""

        if not strategy_id.isdigit():
            return ""

        try:
            from backend.shared.strategy_storage import get_strategy_storage_service

            storage_svc = get_strategy_storage_service()
            strategy = storage_svc.get(
                strategy_id=int(strategy_id),
                user_id=user_id,
            )
            if inspect.isawaitable(strategy):
                strategy = await strategy
            if isinstance(strategy, dict):
                return str(strategy.get("code") or "")
        except Exception as exc:
            logger.warning(
                "failed to resolve simulation strategy code for restore: strategy=%s error=%s",
                strategy_id,
                exc,
            )
        return ""
