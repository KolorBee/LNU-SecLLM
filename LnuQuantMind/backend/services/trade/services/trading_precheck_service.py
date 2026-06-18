import json
import os
import time
from datetime import date, datetime, timedelta, timezone, time as time_obj
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

import redis as redis_lib
from backend.services.trade.services.k8s_manager import k8s_manager
from backend.shared.trade_redis_keys import (
    pick_first_matching_key,
    trade_agent_heartbeat_key_candidates,
)
from backend.shared.utils import normalize_user_id


def _build_check(key: str, label: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "passed": bool(passed),
        "detail": detail,
    }


def _collect_model_artifacts(production_dir: Path) -> list[str]:
    if not production_dir.exists() or not production_dir.is_dir():
        return []

    preferred_names = [
        "model.lgb",
        "model.pkl",
        "model.joblib",
        "model.bin",
        "model.txt",
    ]
    preferred_paths = [production_dir / name for name in preferred_names]
    found_paths = [path for path in preferred_paths if path.exists() and path.is_file()]

    if not found_paths:
        wildcard_patterns = ["*.lgb", "*.pkl", "*.joblib", "*.bin"]
        dedup: dict[str, Path] = {}
        for pattern in wildcard_patterns:
            for path in production_dir.glob(pattern):
                if path.is_file():
                    dedup[path.name] = path
        found_paths = [dedup[name] for name in sorted(dedup.keys())]

    return [str(path) for path in found_paths]


def _is_true_flag(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


async def _resolve_user_model_context(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    default_dir = Path(os.getenv("MODELS_PRODUCTION", "/app/models/production/model_qlib"))
    context: dict[str, Any] = {
        "model_dir": default_dir,
        "effective_model_id": "",
        "model_source": "env_default",
        "fallback_used": False,
        "fallback_reason": "",
    }

    if not _is_true_flag(os.getenv("TRADING_PRECHECK_RESOLVE_USER_MODEL", "true")):
        context["model_source"] = "env_default(disabled)"
        return context

    raw_user_id = str(user_id or "").strip()
    normalized_user_id = normalize_user_id(raw_user_id) if raw_user_id else ""
    if not normalized_user_id:
        context["model_source"] = "env_default(missing_user_id)"
        return context

    try:
        from backend.shared.model_registry import model_registry_service

        resolved = await model_registry_service.resolve_effective_model(
            tenant_id=str(tenant_id or "default").strip() or "default",
            user_id=normalized_user_id,
            strategy_id=None,
            model_id=None,
        )
        storage_path = str(getattr(resolved, "storage_path", "") or "").strip()
        if storage_path:
            context["model_dir"] = Path(storage_path)
        context["effective_model_id"] = str(getattr(resolved, "effective_model_id", "") or "").strip()
        context["model_source"] = str(getattr(resolved, "model_source", "") or "").strip() or "model_registry"
        context["fallback_used"] = bool(getattr(resolved, "fallback_used", False))
        context["fallback_reason"] = str(getattr(resolved, "fallback_reason", "") or "").strip()
    except Exception as exc:
        context["model_source"] = "env_default(model_registry_failed)"
        context["resolve_error"] = str(exc)
    return context


def _resolve_runner_image() -> tuple[str, str]:
    configured = str(os.getenv("STRATEGY_RUNNER_IMAGE", "")).strip()
    if configured:
        return configured, "configured"
    # 与 k8s_manager 的默认行为保持一致，避免“预检失败但实际可启动”的误报
    default_image = (
        "quantmind-ml-runtime:latest"
        if k8s_manager.mode == "docker"
        else "asia-east1-docker.pkg.dev/gen-lang-client-0953736716/quantmind-repo/quantmind-qlib-runner:latest"
    )
    return default_image, "default"


def _get_env_with_root_fallback(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is not None and str(value).strip() != "":
        return str(value).strip()

    try:
        root_env = Path(__file__).resolve().parents[4] / ".env"
        if root_env.exists():
            for line in root_env.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                env_key, env_value = raw.split("=", 1)
                if env_key.strip() == key:
                    return env_value.strip().strip("'").strip('"')
    except Exception:
        return default

    return default


def _get_stream_series_redis_client():
    host = _get_env_with_root_fallback("REMOTE_QUOTE_REDIS_HOST", "localhost")
    port = int(_get_env_with_root_fallback("REMOTE_QUOTE_REDIS_PORT", "36379") or "36379")
    password = _get_env_with_root_fallback("REMOTE_QUOTE_REDIS_PASSWORD", "") or None
    client = redis_lib.Redis(
        host=host,
        port=port,
        password=password,
        decode_responses=True,
        socket_timeout=3.0,
        socket_connect_timeout=3.0,
    )
    return client, host, port


def _resolve_probe_symbols() -> list[str]:
    # 优先使用 Prefix 格式符合项目标准 (AGENTS.md)
    raw = str(os.getenv("PREFLIGHT_STREAM_SYMBOLS", "SZ000001,SH600000")).strip()
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    return symbols or ["SZ000001", "SH600000"]


def _parse_bridge_report_ts(report: dict[str, Any]) -> float | None:
    candidates = (
        "timestamp",
        "ts",
        "last_seen",
        "updated_at",
        "report_ts",
        "report_time",
    )
    for key in candidates:
        raw = report.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            ts = float(raw)
            return ts / 1000.0 if ts > 1e12 else ts
        if isinstance(raw, str):
            text_raw = raw.strip()
            if not text_raw:
                continue
            try:
                ts = float(text_raw)
                return ts / 1000.0 if ts > 1e12 else ts
            except Exception:
                pass
            try:
                iso = text_raw.replace("Z", "+00:00")
                return datetime.fromisoformat(iso).timestamp()
            except Exception:
                continue
    return None


def _previous_trading_day(today: date) -> date:
    try:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar("XSHG")
        session = calendar.date_to_session(today, direction="previous")
        prev_session = calendar.previous_session(session)
        return prev_session.date()
    except Exception:
        candidate = today - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate


async def _query_market_data_readiness(db: AsyncSession, expected_trade_date: date) -> dict[str, Any]:
    feature_cols_count_row = (await db.execute(text("""
                SELECT COUNT(*) AS cnt
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'market_data_daily'
                  AND column_name ~ '^feature_[0-9]+$'
                """))).mappings().first()
    feature_cols_count = int((feature_cols_count_row or {}).get("cnt") or 0)
    has_48_feature_cols = feature_cols_count >= 48

    dim48_condition = "jsonb_typeof(features) = 'array' AND jsonb_array_length(features) = 48"
    if has_48_feature_cols:
        dim48_columns_condition = " AND ".join([f"feature_{i} IS NOT NULL" for i in range(48)])
        dim48_condition = f"(({dim48_condition}) OR ({dim48_columns_condition}))"

    row = (
        (
            await db.execute(
                text(f"""
                SELECT
                    MAX(date) AS latest_trade_date,
                    COUNT(*) FILTER (WHERE date = :expected_trade_date) AS expected_rows,
                    COUNT(*) FILTER (
                        WHERE date = :expected_trade_date
                          AND {dim48_condition}
                    ) AS expected_dim48_rows
                FROM market_data_daily
                """),
                {"expected_trade_date": expected_trade_date},
            )
        )
        .mappings()
        .first()
    )

    data_stats = dict(row or {})
    latest_trade_date = data_stats.get("latest_trade_date")
    expected_rows = int(data_stats.get("expected_rows") or 0)
    expected_dim48_rows = int(data_stats.get("expected_dim48_rows") or 0)
    passed = (
        str(latest_trade_date) >= expected_trade_date.isoformat()
        and expected_rows > 0
        and expected_dim48_rows == expected_rows
    )
    detail = (
        f"latest_trade_date={latest_trade_date}, expected_trade_date={expected_trade_date.isoformat()}, "
        f"rows={expected_rows}, dim48_rows={expected_dim48_rows}, feature_columns={feature_cols_count}"
    )
    return {
        "passed": passed,
        "detail": detail,
    }


def _check_inference_model_exists(production_dir: Path | None = None) -> tuple[bool, str]:
    """检查推理模型文件是否存在，不查询数据库。"""
    production_dir = production_dir or Path(os.getenv("MODELS_PRODUCTION", "/app/models/production/model_qlib"))
    if not production_dir.exists() or not production_dir.is_dir():
        return False, f"推理模型目录不存在: {production_dir}"
    try:
        artifacts = _collect_model_artifacts(production_dir)
    except Exception as exc:
        return False, f"推理模型目录读取失败: {exc}"
    if not artifacts:
        return False, (
            f"推理模型目录缺少可识别模型文件: {production_dir}; "
            "expected_patterns=model.lgb/model.pkl/model.joblib/model.bin/model.txt/*.lgb/*.pkl/*.joblib/*.bin"
        )
    return True, f"推理模型已存在 (model_dir={production_dir}, matched={', '.join(artifacts[:3])})"


def _build_model_context_hint(model_context: dict[str, Any]) -> str:
    hint = (
        f"effective_model_id={model_context.get('effective_model_id') or '-'}, "
        f"model_source={model_context.get('model_source') or '-'}"
    )
    if model_context.get("fallback_reason"):
        hint = f"{hint}, fallback_reason={model_context.get('fallback_reason')}"
    if model_context.get("resolve_error"):
        hint = f"{hint}, resolve_error={model_context.get('resolve_error')}"
    return hint


def _summarize_hosted_status(hosted_status: dict[str, Any]) -> str:
    latest_run_id = str(hosted_status.get("latest_run_id") or "").strip() or "-"
    prediction_trade_date = str(hosted_status.get("prediction_trade_date") or "").strip() or "-"
    reason_code = str(hosted_status.get("reason_code") or "").strip() or "-"
    message = str(hosted_status.get("message") or "").strip() or "-"
    return (
        f"hosted_status(reason={reason_code}, latest_run_id={latest_run_id}, "
        f"prediction_trade_date={prediction_trade_date}, message={message})"
    )


async def _check_simulation_model_ready(
    *,
    tenant_id: str,
    user_id: str,
    production_dir: Path,
    model_context: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    resolved_context = model_context or await _resolve_user_model_context(
        tenant_id=tenant_id,
        user_id=user_id,
    )
    model_context_hint = _build_model_context_hint(resolved_context)
    model_ok, model_detail = _check_inference_model_exists(production_dir)
    if model_ok:
        return True, f"{model_detail}; {model_context_hint}"

    try:
        from backend.services.trade.services.manual_execution_service import manual_execution_service

        hosted_status = await manual_execution_service.get_default_model_hosted_status(
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except Exception as exc:
        return False, (
            f"{model_detail}; {model_context_hint}; "
            f"hosted_status_error={exc}"
        )

    if bool(hosted_status.get("available")):
        return True, (
            f"{model_detail}; 本地模型目录未命中，但默认模型最新推理批次已可被自动托管消费; "
            f"{_summarize_hosted_status(hosted_status)}; {model_context_hint}"
        )

    return False, (
        f"{model_detail}; {model_context_hint}; "
        f"{_summarize_hosted_status(hosted_status)}"
    )


def _check_stream_series_freshness(redis_client) -> tuple[bool, str]:
    stream_symbols = _resolve_probe_symbols()
    series_threshold_sec = int(os.getenv("PREFLIGHT_SERIES_STALE_THRESHOLD_SEC", "180"))
    try:
        stream_redis, stream_redis_host, stream_redis_port = _get_stream_series_redis_client()
        # 物理连接测试
        try:
            stream_redis.ping()
        except Exception as ping_exc:
            return False, f"行情服务器连接失败: {ping_exc}"

        # 使用本地定义的 _is_trading_session_now，避免循环引用
        is_trading = _is_trading_session_now()

        # 第一阶段：尝试默认探针
        for symbol in stream_symbols:
            alt_symbol = symbol
            if "." in symbol:
                base, mkt = symbol.split(".", 1)
                alt_symbol = f"{mkt.upper()}{base}"
            elif len(symbol) == 8 and symbol[:2].isalpha():
                alt_symbol = f"{symbol[2:]}.{symbol[:2].upper()}"

            test_symbols = sorted(list(set([symbol, alt_symbol])))
            candidates = []
            for s in test_symbols:
                candidates.extend([f"market:series:{s}", f"market:snapshot:{s}", f"stock:{s}"])
            
            for key in candidates:
                ktype = str(stream_redis.type(key) or "none").lower()
                if ktype == "none": continue

                score = None
                if ktype == "zset":
                    latest = stream_redis.zrevrange(key, 0, 0, withscores=True)
                    if latest: _, score = latest[0]
                elif ktype == "hash":
                    score_raw = stream_redis.hget(key, "timestamp")
                    if score_raw:
                        try: score = float(score_raw)
                        except: pass

                if score is not None:
                    latest_age_sec = max(0, int(time.time() - float(score)))
                    ok = latest_age_sec <= series_threshold_sec
                    if ok:
                        return True, "实时行情连接正常" if is_trading else "非交易时段 (行情连接正常)"
                    if not is_trading:
                        return True, f"非交易时段 (最近行情距今 {latest_age_sec}s)"
                    else:
                        return False, f"行情数据延迟过高 ({latest_age_sec}s)"

        # 第二阶段：全自动搜索
        discovery_patterns = ["stock:*", "market:series:*"]
        for pattern in discovery_patterns:
            _, found_keys = stream_redis.scan(0, match=pattern, count=50)
            if not found_keys: continue
            for key in found_keys[:3]:
                ktype = str(stream_redis.type(key) or "none").lower()
                score = None
                if ktype == "zset":
                    latest = stream_redis.zrevrange(key, 0, 0, withscores=True)
                    if latest: _, score = latest[0]
                elif ktype == "hash":
                    score_raw = stream_redis.hget(key, "timestamp")
                    if score_raw:
                        try: score = float(score_raw)
                        except: pass
                
                if score is not None:
                    latest_age_sec = max(0, int(time.time() - float(score)))
                    if latest_age_sec <= series_threshold_sec:
                        return True, "实时行情自动发现成功" if is_trading else "非交易时段 (行情自动发现)"
                    if not is_trading:
                        return True, f"非交易时段 (自动发现最近行情距今 {latest_age_sec}s)"

        # 第三阶段：连接正常但未获取到数据
        if not is_trading:
            return True, "非交易时间 (Redis已连接，待行情启动)"
        
        return False, "未获取到实时行情数据，请确认行情推送已启动"

    except Exception as exc:
        return False, f"行情链路探测异常: {exc}"


def _parse_snapshot_at(snapshot: dict[str, Any]) -> float | None:
    raw = snapshot.get("snapshot_at") or snapshot.get("updated_at")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc).timestamp()
        return raw.timestamp()
    if isinstance(raw, (int, float)):
        ts = float(raw)
        return ts / 1000.0 if ts > 1e12 else ts
    if isinstance(raw, str):
        text_raw = raw.strip()
        if not text_raw:
            return None
        try:
            ts = float(text_raw)
            return ts / 1000.0 if ts > 1e12 else ts
        except Exception:
            pass
        try:
            parsed = datetime.fromisoformat(text_raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None


def _build_user_id_candidates(user_id: str) -> list[str]:
    raw = str(user_id or "").strip()
    if not raw:
        return []
    candidates = [raw]
    try:
        numeric = str(int(raw))
        if numeric not in candidates:
            candidates.append(numeric)
    except Exception:
        pass
    return candidates


async def _check_user_hosting_permission(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> tuple[bool, str]:
    user_id_candidates = _build_user_id_candidates(user_id)
    if not user_id_candidates:
        return False, "无法识别当前用户ID，未通过权限检测"

    stmt = text(
        """
        SELECT
            sp.code AS plan_code,
            sp.name AS plan_name
        FROM user_subscriptions us
        JOIN subscription_plans sp ON sp.id = us.plan_id
        WHERE us.tenant_id = :tenant_id
          AND us.user_id IN :user_ids
          AND us.status = 'active'
          AND COALESCE(sp.is_active, true) = true
        ORDER BY us.end_date DESC NULLS LAST, us.id DESC
        LIMIT 1
        """
    ).bindparams(bindparam("user_ids", expanding=True))
    row = (
        await db.execute(
            stmt,
            {
                "tenant_id": tenant_id,
                "user_ids": user_id_candidates,
            },
        )
    ).mappings().first()

    if not row:
        return False, "未检测到有效订阅，当前仅 Pro 版用户可托管"

    plan_code = str(row.get("plan_code") or "").strip().lower()
    plan_name = str(row.get("plan_name") or "").strip() or plan_code or "-"
    allowed_codes = {
        item.strip().lower()
        for item in str(
            os.getenv("TRADING_PRECHECK_PRO_PLAN_CODES", "pro_monthly")
        ).split(",")
        if item.strip()
    }
    if plan_code in allowed_codes:
        return True, f"用户权限通过（plan={plan_name}/{plan_code}）"
    return False, f"当前订阅为 {plan_name}（{plan_code}），仅 Pro 版用户可托管"


async def _check_qmt_agent_online(db: AsyncSession, redis_client, tenant_id: str, user_id: str) -> tuple[bool, str]:
    from backend.services.trade.routers.real_trading_utils import _fetch_latest_real_account_snapshot

    account_snapshot = await _fetch_latest_real_account_snapshot(db, tenant_id=tenant_id, user_id=user_id)
    heartbeat_key, heartbeat_raw = pick_first_matching_key(
        redis_client.get,
        trade_agent_heartbeat_key_candidates(tenant_id, user_id),
    )
    if not account_snapshot:
        return False, "未检测到 PostgreSQL 实盘账户快照，请先启动 QMT Agent 并等待上报落库"
    if not heartbeat_raw:
        return False, (
            f"未检测到 QMT Agent 心跳上报({trade_agent_heartbeat_key_candidates(tenant_id, user_id)[0]})"
        )

    try:
        heartbeat_report = json.loads(heartbeat_raw)
    except Exception:
        return False, "检测到 QMT Agent 心跳格式异常（非 JSON）"

    if not isinstance(heartbeat_report, dict):
        return False, "检测到 QMT Agent 心跳格式异常（非 JSON 对象）"

    account_ts = _parse_snapshot_at(account_snapshot)
    heartbeat_ts = _parse_bridge_report_ts(heartbeat_report)
    if account_ts is None or heartbeat_ts is None:
        return False, "QMT Agent 上报缺少有效时间戳（PG 账户快照或心跳）"

    account_age_sec = max(0, int(time.time() - account_ts))
    heartbeat_age_sec = max(0, int(time.time() - heartbeat_ts))
    account_threshold_sec = int(os.getenv("QMT_AGENT_ACCOUNT_STALE_THRESHOLD_SEC", "120"))
    heartbeat_threshold_sec = int(os.getenv("QMT_AGENT_HEARTBEAT_STALE_THRESHOLD_SEC", "60"))
    passed = account_age_sec <= account_threshold_sec and heartbeat_age_sec <= heartbeat_threshold_sec
    detail = (
        f"account_age_sec={account_age_sec}/{account_threshold_sec}, "
        f"heartbeat_age_sec={heartbeat_age_sec}/{heartbeat_threshold_sec}"
    )
    return passed, detail


def _is_trading_session_now() -> bool:
    """检查当前是否处于 A 股交易时段（09:15-11:30, 13:00-15:00）"""
    now = datetime.now()
    # 周六周日直接返回 False
    if now.weekday() >= 5:
        return False
    
    # 尝试确认是否为交易日
    try:
        import exchange_calendars as xcals
        calendar = xcals.get_calendar("XSHG")
        if not calendar.is_session(now.date()):
            return False
    except Exception:
        pass

    # 检查具体时间段
    curr = now.time()
    # 9:15 - 11:30
    if curr >= time_obj(9, 15) and curr <= time_obj(11, 30):
        return True
    # 13:00 - 15:00
    if curr >= time_obj(13, 0) and curr <= time_obj(15, 0):
        return True
    
    return False


async def run_trading_readiness_precheck(
    db: AsyncSession,
    *,
    mode: str,
    redis_client,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    normalized_mode = str(mode or "REAL").strip().upper()
    if normalized_mode not in {"REAL", "SHADOW", "SIMULATION"}:
        raise ValueError(f"unsupported trading mode: {mode}")

    checks: list[dict[str, Any]] = []

    expected_trade_date = _previous_trading_day(date.today())
    model_context = await _resolve_user_model_context(tenant_id=tenant_id, user_id=user_id)
    production_dir = model_context.get("model_dir")
    if not isinstance(production_dir, Path):
        production_dir = Path(str(production_dir or os.getenv("MODELS_PRODUCTION", "/app/models/production/model_qlib")))
    model_context_hint = _build_model_context_hint(model_context)

    try:
        redis_ok = bool(redis_client.ping())
        checks.append(_build_check("redis", "Redis", redis_ok, "Redis 已连接" if redis_ok else "Redis 不可达"))
    except Exception as exc:
        checks.append(_build_check("redis", "Redis", False, f"Redis 自检失败: {exc}"))

    try:
        await db.execute(text("SELECT 1"))
        checks.append(_build_check("db", "PostgreSQL", True, "数据库连接正常"))
    except Exception as exc:
        checks.append(_build_check("db", "PostgreSQL", False, f"数据库自检失败: {exc}"))

    internal_secret = str(os.getenv("INTERNAL_CALL_SECRET", "")).strip()
    checks.append(
        _build_check(
            "internal_secret",
            "内部密钥",
            bool(internal_secret),
            "INTERNAL_CALL_SECRET 已配置" if internal_secret else "缺少 INTERNAL_CALL_SECRET 配置",
        )
    )

    try:
        permission_ok, permission_detail = await _check_user_hosting_permission(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except Exception as exc:
        permission_ok, permission_detail = False, f"用户权限检测失败: {exc}"

    # 模拟盘不限制订阅资格
    if normalized_mode == "SIMULATION":
        permission_ok = True
        permission_detail = f"[SIMULATION] 自动放行订阅门禁; 原始检测结果: {permission_detail}"

    checks.append(_build_check("user_permission", "用户权限", permission_ok, permission_detail))

    signal_stream_publish_enabled = str(
        os.getenv("ENABLE_SIGNAL_STREAM_PUBLISH", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}
    vectorized_matcher_enabled = str(
        os.getenv("ENABLE_VECTORIZED_MATCHER", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}
    checks.append(
        _build_check(
            "signal_pipeline_enabled",
            "自动托管信号链路已启用",
            True,
            (
                "ENABLE_SIGNAL_STREAM_PUBLISH=true"
                if signal_stream_publish_enabled
                else (
                    "ENABLE_VECTORIZED_MATCHER=true (fallback)"
                    if vectorized_matcher_enabled
                    else "[WARNING] 未启用 signal stream publisher 或 vectorized matcher"
                )
            ),
        )
    )
    if normalized_mode == "SIMULATION":
        try:
            model_ok, model_detail = await _check_simulation_model_ready(
                tenant_id=tenant_id,
                user_id=user_id,
                production_dir=production_dir,
                model_context=model_context,
            )
            checks.append(
                _build_check(
                    "inference_database_ready",
                    "推理模型已就绪",
                    model_ok,
                    model_detail,
                )
            )
        except Exception as exc:
            checks.append(
                _build_check(
                    "inference_database_ready",
                    "推理模型已就绪",
                    False,
                    f"model_check_error={exc}; {model_context_hint}",
                )
            )

        try:
            from backend.services.trade.sandbox.manager import sandbox_manager

            workers = list(getattr(sandbox_manager, "_workers", {}).values())
            worker_total = len(workers)
            alive_total = sum(1 for proc in workers if bool(proc and proc.is_alive()))
            pool_ok = alive_total > 0
            checks.append(
                _build_check(
                    "simulation_sandbox_pool",
                    "模拟盘进程池",
                    pool_ok,
                    (
                        f"进程池可用（alive={alive_total}/{worker_total}）"
                        if pool_ok
                        else "进程池不可用（无存活 worker）"
                    ),
                )
            )
        except Exception as exc:
            checks.append(
                _build_check(
                    "simulation_sandbox_pool",
                    "模拟盘进程池",
                    False,
                    f"process_pool_error={exc}",
                )
            )

        try:
            stream_ok, stream_detail = _check_stream_series_freshness(redis_client)
            is_trading = _is_trading_session_now()
            # 模拟盘逻辑：非交易时间不因为行情不新鲜而阻断；交易时间必须打开行情检测。
            if not stream_ok:
                stream_detail = f"[SIMULATION] 行情数据不新鲜（阻断）: {stream_detail}"
            checks.append(
                _build_check(
                    "realtime_market_ready",
                    "实时行情服务已就绪",
                    stream_ok,
                    (f"已就绪: {stream_detail}"),
                )
            )
        except Exception as exc:
            is_trading = _is_trading_session_now()
            checks.append(
                _build_check(
                    "realtime_market_ready",
                    "实时行情服务已就绪",
                    False, # 探针异常直接阻断
                    f"[SIMULATION] 行情探针异常（阻断）: {exc}",
                )
            )
        return {
            "passed": all(bool(item.get("passed")) for item in checks),
            "checked_at": datetime.now().isoformat(),
            "items": checks,
        }

    model_artifacts = _collect_model_artifacts(production_dir)
    model_exists = bool(model_artifacts)
    model_detail = (
        f"model_dir={production_dir}; matched={', '.join(model_artifacts[:3])}; {model_context_hint}"
        if model_exists
        else (
            f"model_dir={production_dir}; expected_patterns="
            "model.lgb/model.pkl/model.joblib/model.bin/model.txt/*.lgb/*.pkl/*.joblib/*.bin"
            f"; {model_context_hint}"
        )
    )
    checks.append(
        _build_check(
            "production_model",
            "生产模型存在",
            model_exists,
            model_detail,
        )
    )

    try:
        model_ok, model_detail = _check_inference_model_exists(production_dir)
        checks.append(
            _build_check(
                "inference_database_ready",
                "推理模型已就绪",
                model_ok,
                f"{model_detail}; {model_context_hint}",
            )
        )
    except Exception as exc:
        checks.append(
            _build_check(
                "inference_database_ready",
                "推理模型已就绪",
                False,
                f"model_check_error={exc}; {model_context_hint}",
            )
        )

    resolved_image, image_source = _resolve_runner_image()
    # 容器编排就绪度检测 (支持 Docker 或 K8s)
    orchestration_ready = bool(k8s_manager.api and k8s_manager.core_api)
    orchestration_label = (
        "容器编排服务 (Docker) 与执行镜像已就绪" if k8s_manager.mode == "docker" else "Kubernetes 服务与执行镜像已就绪"
    )

    checks.append(
        _build_check(
            "k8s_and_runner_ready",
            orchestration_label,
            orchestration_ready and bool(resolved_image),
            (
                f"orchestration_mode={k8s_manager.mode}, "
                f"orchestration_ready={orchestration_ready}, "
                f"runner_image={resolved_image}, image_source={image_source}"
            ),
        )
    )

    stream_ok, stream_detail = _check_stream_series_freshness(redis_client)
    checks.append(
        _build_check(
            "realtime_market_ready",
            "实时行情服务已就绪",
            stream_ok,
            (f"已就绪: {stream_detail}" if stream_ok else f"行情不新鲜: {stream_detail}"),
        )
    )

    if normalized_mode == "REAL":
        qmt_ok, qmt_detail = await _check_qmt_agent_online(db, redis_client, tenant_id, user_id)
        checks.append(
            _build_check(
                "qmt_agent_online",
                "QMT Agent 在线且数据已上报",
                qmt_ok,
                qmt_detail,
            )
        )

    return {
        "passed": all(bool(item.get("passed")) for item in checks),
        "checked_at": datetime.now().isoformat(),
        "items": checks,
    }
