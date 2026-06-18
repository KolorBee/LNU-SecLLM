from fastapi import APIRouter
import logging
import ast
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .real_trading_utils import *
from .real_trading_utils import (
    _active_strategy_key,
    _default_execution_config,
    _default_live_trade_config,
    _fetch_active_portfolio_snapshot,
    _normalize_execution_config,
    _normalize_identity,
    _normalize_live_trade_config,
    _parse_int_user_id,
    _schedule_status_writeback,
    _schedule_user_notification,
)
from backend.services.trade.services.manual_execution_service import (
    manual_execution_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)
_SH_TZ = ZoneInfo("Asia/Shanghai")
_SIMULATION_BOOTSTRAP_LOCK_TTL_SECONDS = 36 * 3600


def _is_native_strategy_config_without_on_tick(code_str: str) -> bool:
    code = str(code_str or "")
    if not code.strip():
        return False
    if "STRATEGY_CONFIG" not in code:
        return False
    try:
        tree = ast.parse(code)
    except Exception:
        # 语法异常由后续沙箱编译阶段给出更明确报错，这里不提前拦截
        return False

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "on_tick"
        ):
            return False
    return True


def _prepare_native_simulation_bootstrap(
    *,
    tenant_id: str,
    user_id: str,
    strategy_id: str,
    live_trade_config: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    trigger_context = {
        "source": "simulation_native_bootstrap",
        "reason": "native_strategy_config_without_on_tick",
    }
    local_now = (now or datetime.now(timezone.utc)).astimezone(_SH_TZ)
    try:
        from backend.services.trade.services.simulation_hosted_scheduler import (
            _lock_key,
            _should_trigger,
            _task_id,
        )

        decision = _should_trigger(
            now=local_now,
            live_trade_config=live_trade_config,
            started_day=local_now.date(),
        )
        if not decision.should_trigger:
            return {
                "task_id": None,
                "lock_key": None,
                "trigger_context": trigger_context,
            }
        trigger_context.update(
            {
                "phase": decision.phase,
                "runner_trade_date": decision.trade_date,
                "dedupe_scope": "simulation_scheduler_shared",
            }
        )
        return {
            "task_id": _task_id(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                trade_date=decision.trade_date,
                phase=decision.phase,
            ),
            "lock_key": _lock_key(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                trade_date=decision.trade_date,
                phase=decision.phase,
            ),
            "trigger_context": trigger_context,
        }
    except Exception:
        logger.debug(
            "failed to prepare native simulation bootstrap dedupe key",
            exc_info=True,
        )
        return {
            "task_id": None,
            "lock_key": None,
            "trigger_context": trigger_context,
        }


def _build_next_scheduled_execution(
    *,
    current_mode: str,
    active_data: dict[str, Any] | None,
    active_live_trade_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if str(current_mode or "").upper() != "SIMULATION":
        return None
    if not isinstance(active_live_trade_config, dict) or not active_live_trade_config:
        return None
    try:
        from backend.services.trade.services.simulation_hosted_scheduler import (
            _normalize_live_trade_config,
            _next_scheduled_trigger,
            _parse_started_at,
        )

        normalized_cfg = _normalize_live_trade_config(active_live_trade_config)
        started_day = _parse_started_at(
            (active_data or {}).get("started_at")
            if isinstance(active_data, dict)
            else None
        )
        next_trigger = _next_scheduled_trigger(
            now=datetime.now(timezone.utc),
            live_trade_config=normalized_cfg,
            started_day=started_day,
        )
        if next_trigger is None:
            return None
        return {
            "schedule_type": str(normalized_cfg.get("schedule_type") or "interval"),
            "phase": next_trigger.phase,
            "trade_date": next_trigger.trade_date,
            "target_at": next_trigger.target_at.isoformat(),
            "window_start_at": next_trigger.window_start_at.isoformat(),
            "window_end_at": next_trigger.window_end_at.isoformat(),
            "reason": next_trigger.reason,
        }
    except Exception:
        logger.warning(
            "failed to build next simulation scheduled execution",
            exc_info=True,
        )
        return None


async def _build_signal_source_status(
    _redis_client, tenant_id: str, user_id: str
) -> tuple[str | None, dict]:
    try:
        hosted_status = await manual_execution_service.get_default_model_hosted_status(
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except Exception as exc:
        return None, {
            "available": False,
            "source": "missing",
            "message": f"读取默认模型自动托管状态失败: {exc}",
        }

    latest_run_id = str(hosted_status.get("latest_run_id") or "").strip() or None
    if not bool(hosted_status.get("available")):
        return latest_run_id, hosted_status

    return latest_run_id, hosted_status


async def _resolve_strategy_detail(*, strategy_id: str, user_id: str) -> dict:
    """解析策略来源并返回标准化元数据。"""
    if strategy_id.startswith("sys_"):
        template_id = strategy_id.replace("sys_", "", 1)
        # 运行时导入，避免顶层导入 engine 模块触发 qlib 报错
        try:
            from backend.services.engine.qlib_app.services.strategy_templates import (
                get_template_by_id,
            )

            template = get_template_by_id(template_id)
        except (ImportError, ModuleNotFoundError):
            template = None

        if not template:
            raise HTTPException(status_code=404, detail="内置策略模板不存在")
        return {
            "strategy_name": template.name,
            "execution_config": getattr(template, "execution_defaults", None)
            or _default_execution_config(),
            "live_trade_config": getattr(template, "live_defaults", None)
            or _default_live_trade_config(),
            "live_config_tips": getattr(template, "live_config_tips", None) or [],
            "source": "template",
            "template_id": template_id,
            "code": template.code,
        }

    if not strategy_id.isdigit():
        raise HTTPException(status_code=400, detail="strategy_id 格式非法")

    storage_svc = get_strategy_storage_service()
    strategy = await storage_svc.get(strategy_id=int(strategy_id), user_id=user_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="用户策略不存在")
    return {
        "strategy_name": strategy.get("name") or f"strategy_{strategy_id}",
        "execution_config": strategy.get("execution_config")
        or _default_execution_config(),
        "live_trade_config": strategy.get("live_trade_config")
        or _default_live_trade_config(),
        "live_config_tips": strategy.get("live_config_tips") or [],
        "source": "user_strategy",
        "code": strategy.get("code") or "",
    }


@router.post("/start")
async def start_trading(
    user_id: Optional[str] = Form(None),
    strategy_id: Optional[str] = Form(None),
    strategy_file: Optional[UploadFile] = File(None),
    trading_mode: str = Form("REAL"),  # 默认 REAL，可传入 SHADOW/SIMULATION
    execution_config: Optional[str] = Form(None),
    live_trade_config: Optional[str] = Form(None),
    tenant_id: Optional[str] = Form(None),
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    resolved_user_id, resolved_tenant_id = _normalize_identity(
        auth, user_id=user_id, tenant_id=tenant_id
    )

    try:
        strategy_name = "unknown_strategy"
        mode = str(trading_mode or "REAL").strip().upper()
        if mode not in {"REAL", "SHADOW", "SIMULATION"}:
            raise HTTPException(
                status_code=400, detail=f"unsupported trading_mode: {mode}"
            )

        if not strategy_id and not strategy_file:
            raise HTTPException(
                status_code=400, detail="strategy_id 或 strategy_file 至少提供一个"
            )

        strategy_name = "uploaded_strategy.py"
        exec_config = _default_execution_config()
        live_config = _default_live_trade_config()
        if strategy_id:
            detail = await _resolve_strategy_detail(
                strategy_id=strategy_id, user_id=resolved_user_id
            )
            strategy_name = detail["strategy_name"]
            exec_config = detail["execution_config"]
            live_config = (
                detail.get("live_trade_config") or _default_live_trade_config()
            )
        elif strategy_file:
            strategy_name = strategy_file.filename or strategy_name

        exec_config = _normalize_execution_config({}, exec_config)
        ExecutionConfigSchema.model_validate(exec_config)
        live_config = _normalize_live_trade_config({}, live_config)

        # 前端可覆盖风控参数（以本次启动快照为准）
        if execution_config:
            try:
                user_exec_cfg = json.loads(execution_config)
            except Exception:
                raise HTTPException(
                    status_code=400, detail="execution_config 不是合法 JSON"
                )
            if not isinstance(user_exec_cfg, dict):
                raise HTTPException(
                    status_code=400, detail="execution_config 必须是对象"
                )
            exec_config = _normalize_execution_config(user_exec_cfg, exec_config)
            ExecutionConfigSchema.model_validate(exec_config)
        if live_trade_config:
            try:
                user_live_cfg = json.loads(live_trade_config)
            except Exception:
                raise HTTPException(
                    status_code=400, detail="live_trade_config 不是合法 JSON"
                )
            if not isinstance(user_live_cfg, dict):
                raise HTTPException(
                    status_code=400, detail="live_trade_config 必须是对象"
                )
            live_config = _normalize_live_trade_config(user_live_cfg, live_config)

        readiness = {
            "passed": True,
            "checked_at": datetime.now().isoformat(),
            "items": [],
        }
        if mode in {"REAL", "SHADOW", "SIMULATION"}:
            readiness = await run_trading_readiness_precheck(
                db,
                mode=mode,
                redis_client=redis.client,
                user_id=resolved_user_id,
                tenant_id=resolved_tenant_id,
            )
        if not readiness.get("passed"):
            failed_items = [
                item
                for item in readiness.get("items", [])
                if not bool(item.get("passed"))
            ]
            first_failed = failed_items[0] if failed_items else None
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "交易准备度检测未通过，请先确认模型、数据库、Kubernetes、实时行情与柜台上报状态",
                    "precheck_failed": True,
                    "checked_at": readiness.get("checked_at"),
                    "items": readiness.get("items", []),
                    "first_failed_reason": (first_failed or {}).get("detail")
                    or (first_failed or {}).get("label"),
                },
            )

        run_id = f"run_{int(time.time())}"
        strategy_dir = get_strategy_path(resolved_user_id)
        os.makedirs(strategy_dir, exist_ok=True)
        file_path = os.path.join(strategy_dir, f"{run_id}.py")
        if strategy_file:
            content = await strategy_file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            code_str = content.decode("utf-8")
        else:
            code_str = detail.get("code") or ""
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code_str if code_str else f"# strategy_ref={strategy_id}\n")

        # 3. K8s 调度 (仅针对 REAL 和 SHADOW 模式)
        result = {"status": "success", "mode": mode}
        if mode in ["REAL", "SHADOW"]:
            result = await run_in_threadpool(
                k8s_manager.create_deployment,
                resolved_user_id,
                file_path,
                run_id=run_id,
                exec_config={**exec_config, "trading_mode": mode},
                tenant_id=resolved_tenant_id,
                live_trade_config=live_config,
                strategy_id=strategy_id,
            )
            if result.get("status") == "error":
                raise HTTPException(status_code=500, detail=result.get("message"))
        else:
            # 纯模拟盘模式：无需 K8s，使用轻量级进程池沙箱执行策略
            from backend.services.trade.sandbox.manager import sandbox_manager

            is_native_cfg = _is_native_strategy_config_without_on_tick(code_str)

            try:
                sandbox_run_id = sandbox_manager.submit_strategy(
                    tenant_id=resolved_tenant_id,
                    user_id=resolved_user_id,
                    strategy_id=strategy_id or strategy_name,
                    code_str=code_str,
                    exec_config=exec_config,
                    live_trade_config=live_config,
                )
                logger.info(
                    f"[Sim] 用户 {resolved_user_id} 启动了沙箱模拟盘 {strategy_name} -> PID Task"
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"沙箱启动失败: {str(e)}")

            # 兼容原生 STRATEGY_CONFIG 策略（通常不定义 on_tick）：
            # 启动后立即触发一次自动托管任务，避免“运行中但无信号产出”的假活跃状态。
            if is_native_cfg and strategy_id:
                bootstrap_plan = _prepare_native_simulation_bootstrap(
                    tenant_id=resolved_tenant_id,
                    user_id=resolved_user_id,
                    strategy_id=str(strategy_id or ""),
                    live_trade_config=live_config,
                )
                bootstrap_task_id = str(bootstrap_plan.get("task_id") or "").strip() or None
                bootstrap_lock_key = str(bootstrap_plan.get("lock_key") or "").strip() or None
                bootstrap_lock_acquired = False

                if bootstrap_task_id and bootstrap_lock_key and redis.client:
                    try:
                        bootstrap_lock_acquired = bool(
                            redis.client.set(
                                bootstrap_lock_key,
                                bootstrap_task_id,
                                ex=_SIMULATION_BOOTSTRAP_LOCK_TTL_SECONDS,
                                nx=True,
                            )
                        )
                    except Exception:
                        logger.warning(
                            "[Sim] 原生策略 bootstrap 写入调度去重锁失败: tenant=%s user=%s strategy=%s key=%s",
                            resolved_tenant_id,
                            resolved_user_id,
                            strategy_id,
                            bootstrap_lock_key,
                            exc_info=True,
                        )

                if bootstrap_task_id and bootstrap_lock_key and not bootstrap_lock_acquired:
                    hosted_bootstrap = {
                        "task_id": bootstrap_task_id,
                        "status": "duplicate_skipped",
                        "noop": True,
                        "duplicate": True,
                    }
                    logger.info(
                        "[Sim] 原生策略 bootstrap 检测到同日调度任务已存在，跳过重复托管任务: user=%s strategy=%s task_id=%s",
                        resolved_user_id,
                        strategy_id,
                        bootstrap_task_id,
                    )
                else:
                    try:
                        hosted_bootstrap = await manual_execution_service.create_hosted_task(
                            tenant_id=resolved_tenant_id,
                            user_id=resolved_user_id,
                            strategy_id=str(strategy_id or ""),
                            trading_mode="SIMULATION",
                            execution_config=exec_config,
                            live_trade_config=live_config,
                            trigger_context=dict(bootstrap_plan.get("trigger_context") or {}),
                            parent_runtime_id=run_id,
                            note="auto bootstrap from simulation start",
                            task_id=bootstrap_task_id,
                        )
                    except Exception:
                        if bootstrap_lock_acquired and bootstrap_lock_key and redis.client:
                            try:
                                redis.client.delete(bootstrap_lock_key)
                            except Exception:
                                logger.debug(
                                    "[Sim] 清理 bootstrap 去重锁失败: key=%s",
                                    bootstrap_lock_key,
                                    exc_info=True,
                                )
                        raise
                result = {
                    **result,
                    "hosted_bootstrap": {
                        "task_id": hosted_bootstrap.get("task_id"),
                        "status": hosted_bootstrap.get("status"),
                        "noop": bool(hosted_bootstrap.get("noop")),
                    },
                }
                logger.info(
                    "[Sim] 已触发原生策略自动托管引导任务: user=%s strategy=%s task_id=%s status=%s",
                    resolved_user_id,
                    strategy_id,
                    hosted_bootstrap.get("task_id"),
                    hosted_bootstrap.get("status"),
                )

        # 4. 状态持久化
        redis.client.set(
            _active_strategy_key(resolved_tenant_id, resolved_user_id),
            json.dumps(
                {
                    "strategy_id": strategy_id,
                    "run_id": run_id,
                    "mode": mode,
                    "strategy_name": strategy_name,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "execution_config": exec_config,
                    "live_trade_config": live_config,
                    "launch_result": result,
                }
            ),
        )
        if mode in {"REAL", "SHADOW"}:
            _schedule_status_writeback(
                strategy_id=strategy_id,
                user_id=resolved_user_id,
                lifecycle_status="live_trading",
            )
        _schedule_user_notification(
            user_id=resolved_user_id,
            tenant_id=resolved_tenant_id,
            title="实盘策略已启动" if mode in {"REAL", "SHADOW"} else "模拟策略已启动",
            content=f"策略 {strategy_name} 启动成功，模式：{mode}",
            type="strategy",
            level="success",
            action_url="/trading",
        )

        return {
            "status": "success",
            "message": f"策略 {strategy_name} 已成功启动",
            "effective_execution_config": exec_config,
            "effective_live_trade_config": live_config,
            "k8s_result": result,
            "orchestration_mode": k8s_manager.mode,
        }
    except HTTPException:
        _schedule_user_notification(
            user_id=resolved_user_id,
            tenant_id=resolved_tenant_id,
            title="策略启动失败",
            content=f"启动失败：{strategy_name}",
            type="strategy",
            level="error",
            action_url="/trading",
        )
        raise
    except Exception as e:
        logger.error(
            f"Failed to start trading for {resolved_user_id}: {e}", exc_info=True
        )
        _schedule_user_notification(
            user_id=resolved_user_id,
            tenant_id=resolved_tenant_id,
            title="策略启动失败",
            content=f"启动异常：{str(e)}",
            type="strategy",
            level="error",
            action_url="/trading",
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_trading(
    user_id: Optional[str] = Form(None),
    tenant_id: Optional[str] = Form(None),
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    try:
        resolved_user_id, resolved_tenant_id = _normalize_identity(
            auth, user_id=user_id, tenant_id=tenant_id
        )

        active_strat_raw = redis.client.get(
            _active_strategy_key(resolved_tenant_id, resolved_user_id)
        )
        result = {"status": "success", "message": "Stopped"}
        stopped_strategy_id = None

        if active_strat_raw:
            data = json.loads(active_strat_raw)
            mode = data.get("mode", "REAL")
            strat_id = data.get("strategy_id", "unknown")
            stopped_strategy_id = strat_id
            if mode == "SIMULATION":
                from backend.services.trade.sandbox.manager import sandbox_manager

                sandbox_manager.stop_strategy(
                    resolved_tenant_id, resolved_user_id, strat_id
                )
                logger.info(f"[Sim] 用户 {resolved_user_id} 停止了沙箱模拟盘")
            elif mode in {"REAL", "SHADOW"}:
                result = await run_in_threadpool(
                    k8s_manager.delete_deployment, resolved_user_id, resolved_tenant_id
                )
                _schedule_status_writeback(
                    strategy_id=strat_id,
                    user_id=resolved_user_id,
                    lifecycle_status="repository",
                )

        # Clear active strategy in Redis
        redis.client.delete(_active_strategy_key(resolved_tenant_id, resolved_user_id))

        # 同步更新数据库中 portfolio 的 run_status
        try:
            user_id_int = int(resolved_user_id)
            stmt = (
                select(Portfolio)
                .where(
                    Portfolio.tenant_id == resolved_tenant_id,
                    Portfolio.user_id == user_id_int,
                    Portfolio.run_status == "running",
                    Portfolio.is_deleted.is_(False),
                )
                .order_by(desc(Portfolio.updated_at))
                .limit(1)
            )
            db_result = await db.execute(stmt)
            portfolio = db_result.scalars().first()

            if portfolio:
                old_status = portfolio.run_status
                portfolio.run_status = "stopped"
                portfolio.updated_at = datetime.utcnow()
                await db.commit()
                logger.info(
                    f"Updated portfolio %d run_status: %s -> stopped",
                    portfolio.id,
                    old_status,
                )
        except Exception as db_err:
            logger.warning("Failed to update portfolio run_status: %s", db_err)
            await db.rollback()

        _schedule_user_notification(
            user_id=resolved_user_id,
            tenant_id=resolved_tenant_id,
            title="策略已停止",
            content="当前实盘/模拟策略已停止运行",
            type="strategy",
            level="info",
            action_url="/trading",
        )
        return result
    except HTTPException:
        if "resolved_user_id" in locals():
            _schedule_user_notification(
                user_id=resolved_user_id,
                tenant_id=resolved_tenant_id,
                title="策略停止失败",
                content="停止请求失败，请稍后重试",
                type="strategy",
                level="error",
                action_url="/trading",
            )
        raise
    except Exception as e:
        if "resolved_user_id" in locals():
            _schedule_user_notification(
                user_id=resolved_user_id,
                tenant_id=resolved_tenant_id,
                title="策略停止失败",
                content=f"停止异常：{str(e)}",
                type="strategy",
                level="error",
                action_url="/trading",
            )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
@redis_cache(ttl=5)
async def get_status(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trading_mode: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    resolved_user_id, resolved_tenant_id = _normalize_identity(
        auth, user_id=user_id, tenant_id=tenant_id
    )
    status = await run_in_threadpool(
        k8s_manager.get_status, resolved_user_id, resolved_tenant_id
    )

    # Get active strategy info
    strategy_info = None
    active_strat_id = None
    active_strat_raw = redis.client.get(
        _active_strategy_key(resolved_tenant_id, resolved_user_id)
    )
    portfolio_snapshot = None
    latest_hosted_task = None
    latest_signal_run_id = None
    signal_source_status = {
        "available": False,
        "source": "missing",
        "message": "未检测到当前用户的最新推理信号版本",
    }

    current_mode = "REAL"
    active_exec_config = None
    active_live_trade_config = None
    active_data: dict[str, Any] = {}
    requested_mode = str(trading_mode or "").strip().upper()
    if requested_mode not in {"REAL", "SHADOW", "SIMULATION"}:
        requested_mode = ""
    if active_strat_raw:
        try:
            active_data = json.loads(active_strat_raw)
        except Exception as e:
            logger.warning(
                "Invalid active strategy payload for tenant=%s user=%s: %s",
                resolved_tenant_id,
                resolved_user_id,
                e,
            )
            active_data = {}
        if not isinstance(active_data, dict):
            logger.warning(
                "Unexpected active strategy payload type for tenant=%s user=%s: %s",
                resolved_tenant_id,
                resolved_user_id,
                type(active_data).__name__,
            )
            active_data = {}
        active_strat_id = active_data.get("strategy_id")
        current_mode = active_data.get("mode", "REAL")
        if isinstance(active_data.get("execution_config"), dict):
            active_exec_config = active_data.get("execution_config")
        if isinstance(active_data.get("live_trade_config"), dict):
            active_live_trade_config = active_data.get("live_trade_config")
        if active_data.get("strategy_name"):
            strategy_info = {
                "id": active_strat_id,
                "name": active_data.get("strategy_name"),
            }

        if requested_mode and current_mode != requested_mode:
            active_data = {}
            active_strat_id = None
            strategy_info = None
            active_exec_config = None
            active_live_trade_config = None
            current_mode = requested_mode

        # 兼容老数据：没有 strategy_name 时再按 strategy_id 回查
        if (
            strategy_info is None
            and isinstance(active_strat_id, str)
            and active_strat_id.startswith("sys_")
        ):
            template_id = active_strat_id.replace("sys_", "", 1)
            try:
                from backend.services.engine.qlib_app.services.strategy_templates import (
                    get_template_by_id,
                )

                template = get_template_by_id(template_id)
            except Exception:
                template = None
            if template:
                strategy_info = {
                    "id": active_strat_id,
                    "name": template.name,
                    "description": template.description,
                }
        elif (
            strategy_info is None
            and isinstance(active_strat_id, str)
            and active_strat_id.isdigit()
        ):
            try:
                storage_svc = get_strategy_storage_service()
                strat = await storage_svc.get(
                    strategy_id=int(active_strat_id), user_id=resolved_user_id
                )
                if strat:
                    strategy_info = {
                        "id": strat["id"],
                        "name": strat["name"],
                        "description": strat["description"],
                    }
            except Exception:
                pass

    latest_signal_run_id, signal_source_status = await _build_signal_source_status(
        redis.client,
        resolved_tenant_id,
        resolved_user_id,
    )
    next_scheduled_execution = _build_next_scheduled_execution(
        current_mode=current_mode,
        active_data=active_data,
        active_live_trade_config=active_live_trade_config,
    )
    latest_hosted_task = await manual_execution_service.get_latest_hosted_task(
        tenant_id=resolved_tenant_id,
        user_id=resolved_user_id,
        active_runtime_id=(
            active_data.get("run_id") if isinstance(active_data, dict) else None
        ),
    )

    # 获取投资组合快照，优先尊重请求的 trading_mode
    lookup_mode = trading_mode or current_mode
    portfolio_snapshot = await _fetch_active_portfolio_snapshot(
        db,
        tenant_id=resolved_tenant_id,
        user_id=resolved_user_id,
        strategy_id=(
            str(active_strat_id or "").strip() or None if not trading_mode else None
        ),
        mode=lookup_mode,
    )

    if requested_mode == "SIMULATION" and not strategy_info:
        return {
            "status": "not_running",
            "user_id": resolved_user_id,
            "mode": "SIMULATION",
            "orchestration_mode": k8s_manager.mode,
            "strategy": None,
            "execution_config": None,
            "live_trade_config": None,
            "daily_pnl": (
                portfolio_snapshot["daily_pnl"] if portfolio_snapshot else None
            ),
            "daily_return": (
                portfolio_snapshot["daily_return"] if portfolio_snapshot else None
            ),
            "portfolio": portfolio_snapshot,
            "latest_hosted_task": latest_hosted_task,
            "latest_signal_run_id": latest_signal_run_id,
            "signal_source_status": signal_source_status,
            "next_scheduled_execution": next_scheduled_execution,
        }

    if current_mode == "SIMULATION" and strategy_info:
        simulation_runtime_alive = False
        simulation_runtime_msg = None
        strategy_id_for_runtime = str(active_strat_id or "").strip()
        if strategy_id_for_runtime:
            try:
                from backend.services.trade.sandbox.manager import sandbox_manager

                simulation_runtime_alive = sandbox_manager.is_strategy_running(
                    resolved_tenant_id,
                    resolved_user_id,
                    strategy_id_for_runtime,
                )
            except Exception as exc:
                logger.warning(
                    "Simulation runtime health check failed: tenant=%s user=%s strategy=%s error=%s",
                    resolved_tenant_id,
                    resolved_user_id,
                    strategy_id_for_runtime,
                    exc,
                )
                simulation_runtime_msg = "模拟盘运行状态校验失败，请稍后重试"

        if not simulation_runtime_alive:
            try:
                from backend.services.trade.services.simulation_runtime_restorer import (
                    SimulationRuntimeRestorer,
                )

                restorer = SimulationRuntimeRestorer(redis)
                simulation_runtime_alive = await restorer.restore_active_payload(
                    tenant_id=resolved_tenant_id,
                    user_id=resolved_user_id,
                    active_data=active_data if isinstance(active_data, dict) else {},
                )
                if simulation_runtime_alive:
                    simulation_runtime_msg = "模拟盘沙箱已从持久状态恢复"
            except Exception as exc:
                logger.warning(
                    "Simulation runtime restore on status failed: tenant=%s user=%s strategy=%s error=%s",
                    resolved_tenant_id,
                    resolved_user_id,
                    strategy_id_for_runtime,
                    exc,
                )
                simulation_runtime_msg = (
                    simulation_runtime_msg or "模拟盘运行状态恢复失败"
                )

        if not simulation_runtime_alive:
            return {
                "status": "starting",
                "message": simulation_runtime_msg
                or "模拟盘正在从持久状态恢复，请稍后刷新",
                "user_id": resolved_user_id,
                "mode": "SIMULATION",
                "orchestration_mode": k8s_manager.mode,
                "strategy": strategy_info,
                "execution_config": active_exec_config,
                "live_trade_config": active_live_trade_config,
                "daily_pnl": (
                    portfolio_snapshot["daily_pnl"] if portfolio_snapshot else None
                ),
                "daily_return": (
                    portfolio_snapshot["daily_return"] if portfolio_snapshot else None
                ),
                "portfolio": portfolio_snapshot,
                "latest_hosted_task": latest_hosted_task,
                "latest_signal_run_id": latest_signal_run_id,
                "signal_source_status": signal_source_status,
                "next_scheduled_execution": next_scheduled_execution,
            }

        return {
            "status": "running",
            "user_id": resolved_user_id,
            "mode": "SIMULATION",
            "orchestration_mode": k8s_manager.mode,
            "strategy": strategy_info,
            "execution_config": active_exec_config,
            "live_trade_config": active_live_trade_config,
            "daily_pnl": (
                portfolio_snapshot["daily_pnl"] if portfolio_snapshot else None
            ),
            "daily_return": (
                portfolio_snapshot["daily_return"] if portfolio_snapshot else None
            ),
            "portfolio": portfolio_snapshot,
            "k8s_status": {
                "name": "batch-executor",
                "ready_replicas": 1,
                "replicas": 1,
            },
            "latest_hosted_task": latest_hosted_task,
            "latest_signal_run_id": latest_signal_run_id,
            "signal_source_status": signal_source_status,
            "next_scheduled_execution": next_scheduled_execution,
        }

    if status is None:
        return {
            "status": "not_running",
            "user_id": resolved_user_id,
            "mode": current_mode,
            "orchestration_mode": k8s_manager.mode,
            "strategy": strategy_info,
            "execution_config": active_exec_config,
            "live_trade_config": active_live_trade_config,
            "daily_pnl": (
                portfolio_snapshot["daily_pnl"] if portfolio_snapshot else None
            ),
            "daily_return": (
                portfolio_snapshot["daily_return"] if portfolio_snapshot else None
            ),
            "portfolio": portfolio_snapshot,
            "latest_hosted_task": latest_hosted_task,
            "latest_signal_run_id": latest_signal_run_id,
            "signal_source_status": signal_source_status,
            "next_scheduled_execution": next_scheduled_execution,
        }

    if "error" in status:
        return {
            "status": "error",
            "message": status["error"],
            "user_id": resolved_user_id,
            "mode": current_mode,
            "orchestration_mode": k8s_manager.mode,
            "strategy": strategy_info,
            "execution_config": active_exec_config,
            "live_trade_config": active_live_trade_config,
            "daily_pnl": (
                portfolio_snapshot["daily_pnl"] if portfolio_snapshot else None
            ),
            "daily_return": (
                portfolio_snapshot["daily_return"] if portfolio_snapshot else None
            ),
            "portfolio": portfolio_snapshot,
            "latest_hosted_task": latest_hosted_task,
            "latest_signal_run_id": latest_signal_run_id,
            "signal_source_status": signal_source_status,
            "next_scheduled_execution": next_scheduled_execution,
        }

    state = "running" if status.get("available_replicas", 0) > 0 else "starting"
    return {
        "status": state,
        "user_id": resolved_user_id,
        "mode": current_mode,
        "orchestration_mode": k8s_manager.mode,
        "k8s_status": status,
        "strategy": strategy_info,
        "execution_config": active_exec_config,
        "live_trade_config": active_live_trade_config,
        "daily_pnl": portfolio_snapshot["daily_pnl"] if portfolio_snapshot else None,
        "daily_return": (
            portfolio_snapshot["daily_return"] if portfolio_snapshot else None
        ),
        "portfolio": portfolio_snapshot,
        "latest_hosted_task": latest_hosted_task,
        "latest_signal_run_id": latest_signal_run_id,
        "signal_source_status": signal_source_status,
        "next_scheduled_execution": next_scheduled_execution,
    }


@router.get("/logs")
async def get_logs(
    tail: int = 100,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
):
    resolved_user_id, resolved_tenant_id = _normalize_identity(
        auth, user_id=user_id, tenant_id=tenant_id
    )
    logs = await run_in_threadpool(
        k8s_manager.get_logs, resolved_user_id, tail, resolved_tenant_id
    )
    return {"user_id": resolved_user_id, "logs": logs}


@router.get("/orders")
@redis_cache(ttl=10)
async def get_orders(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    获取订单记录
    """
    try:
        resolved_user_id, resolved_tenant_id = _normalize_identity(
            auth, user_id=user_id, tenant_id=tenant_id
        )
        uid_int = _parse_int_user_id(resolved_user_id)
        stmt = select(Order).where(
            Order.user_id == uid_int, Order.tenant_id == resolved_tenant_id
        )

        if status:
            stmt = stmt.where(Order.status == status)

        stmt = stmt.order_by(desc(Order.created_at)).limit(limit)

        result = await db.execute(stmt)
        orders = result.scalars().all()

        return orders
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_trade_history(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    获取成交历史
    """
    try:
        resolved_user_id, resolved_tenant_id = _normalize_identity(
            auth, user_id=user_id, tenant_id=tenant_id
        )
        uid_int = _parse_int_user_id(resolved_user_id)
        stmt = select(Trade).where(
            Trade.user_id == uid_int, Trade.tenant_id == resolved_tenant_id
        )
        stmt = stmt.order_by(desc(Trade.executed_at)).limit(limit)

        result = await db.execute(stmt)
        trades = result.scalars().all()

        return trades
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))
