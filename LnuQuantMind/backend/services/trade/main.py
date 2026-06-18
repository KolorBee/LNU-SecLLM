import asyncio
import multiprocessing as mp
import os
from contextlib import asynccontextmanager

try:
    mp.set_start_method("spawn", force=True)
except RuntimeError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.services.trade.routers import (
    internal_strategy,
    portfolios,
    positions,
    real_trading,
    simulation,
    simulation_batch,
    simulation_history,
    simulation_orders,
    trading_history,
    trading_orders,
)
from backend.shared.config_manager import init_unified_config
from backend.shared.cors import resolve_cors_origins
from backend.shared.error_contract import install_error_contract_handlers
from backend.shared.logging_config import get_logger
from backend.shared.openapi_utils import quantmind_generate_unique_id
from backend.shared.request_id import install_request_id_middleware
from backend.shared.request_logging import install_access_log_middleware
from backend.shared.schema_registry import create_registered_tables
from backend.shared.service_health_metrics import (
    build_metrics_response,
    set_service_health,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.startup_healthy = True
    app.state.db_connected = False
    app.state.redis_connected = False
    app.state.execution_stream_consumer = None

    scanner_task = None
    margin_task = None
    snapshot_task = None
    ledger_settlement_task = None
    manual_execution_task = None
    vectorized_matcher_task = None
    sim_fund_snapshot_worker = None
    simulation_hosted_scheduler = None
    simulation_runtime_restorer = None
    sandbox_signal_consumer_task = None
    simulation_corporate_action_task = None
    simulation_pending_order_task = None
    simulation_margin_monitor_task = None
    simulation_eod_task = None
    sandbox_pool_started = False

    try:
        await init_unified_config(service_name="quantmind-trade")
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade unified config init failed: %s", e, exc_info=True)

    from backend.shared.database_manager_v2 import close_database, init_database

    try:
        await init_database()
        from backend.shared.database_manager_v2 import get_db_manager

        await create_registered_tables(
            get_db_manager()._master_engine,
            schema_keys=("trade.core", "trade.portfolio", "trade.simulation"),
        )
        from backend.services.trade.services.manual_execution_persistence import (
            manual_execution_persistence,
        )

        await manual_execution_persistence.ensure_tables()
        app.state.db_connected = True
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade database init failed: %s", e, exc_info=True)

    from backend.services.trade.redis_client import redis_client

    try:
        redis_client.connect()
        app.state.redis_connected = True
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade redis init failed: %s", e, exc_info=True)

    try:
        from backend.services.trade.utils.stock_lookup import warmup_stock_cache

        warmup_stock_cache()
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade stock cache warmup failed: %s", e, exc_info=True)

    try:
        from backend.services.trade.services.execution_stream_consumer import (
            ExecutionStreamConsumer,
        )

        exec_consumer = ExecutionStreamConsumer()
        await exec_consumer.start()
        app.state.execution_stream_consumer = exec_consumer
    except Exception as e:
        app.state.startup_healthy = False
        logger.error(
            "trade execution stream consumer start failed: %s", e, exc_info=True
        )

    try:
        from backend.services.trade.services.margin_interest_scanner import (
            run_margin_interest_scanner,
        )
        from backend.services.trade.services.order_timeout_scanner import (
            run_order_timeout_scanner,
        )
        from backend.services.trade.services.portfolio_snapshot_task import (
            run_portfolio_snapshot_task,
        )
        from backend.services.trade.services.real_account_ledger_settlement_task import (
            run_real_account_ledger_settlement_task,
        )
        from backend.services.trade.services.manual_execution_worker import (
            run_manual_execution_worker,
        )
        from backend.services.trade.simulation.services.corporate_action_service import (
            run_simulation_corporate_action_worker,
        )
        from backend.services.trade.simulation.services.pending_order_worker import (
            run_simulation_pending_order_worker,
        )
        from backend.services.trade.simulation.services.margin_monitor_service import (
            run_simulation_margin_monitor_worker,
        )
        from backend.services.trade.simulation.services.eod_service import (
            run_simulation_eod_worker,
        )

        scanner_task = asyncio.create_task(run_order_timeout_scanner())
        margin_task = asyncio.create_task(run_margin_interest_scanner())
        snapshot_task = asyncio.create_task(run_portfolio_snapshot_task())
        ledger_settlement_task = asyncio.create_task(
            run_real_account_ledger_settlement_task()
        )
        manual_execution_task = asyncio.create_task(
            run_manual_execution_worker(), name="manual-execution-worker"
        )
        simulation_corporate_action_task = asyncio.create_task(
            run_simulation_corporate_action_worker(),
            name="simulation-corporate-action-worker",
        )
        simulation_pending_order_task = asyncio.create_task(
            run_simulation_pending_order_worker(),
            name="simulation-pending-order-worker",
        )
        margin_monitor_enabled = (
            str(os.getenv("SIM_MARGIN_MONITOR_ENABLED", "true")).strip().lower()
            != "false"
        )
        if margin_monitor_enabled:
            simulation_margin_monitor_task = asyncio.create_task(
                run_simulation_margin_monitor_worker(),
                name="simulation-margin-monitor-worker",
            )
        eod_enabled = (
            str(os.getenv("SIM_EOD_ENABLED", "true")).strip().lower()
            != "false"
        )
        if eod_enabled:
            simulation_eod_task = asyncio.create_task(
                run_simulation_eod_worker(),
                name="simulation-eod-worker",
            )
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade background scanners start failed: %s", e, exc_info=True)

    # VectorizedMatcher 生命周期接入（含 sandbox signals 消费）
    try:
        from backend.services.trade.services.vectorized_matcher import (
            vectorized_matcher,
        )

        vectorized_matcher_task = asyncio.create_task(
            vectorized_matcher.start(),
            name="vectorized-matcher",
        )
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade vectorized matcher start failed: %s", e, exc_info=True)

    # 模拟盘资金快照后台任务
    try:
        snapshot_enabled = (
            str(os.getenv("SIM_FUND_SNAPSHOT_ENABLED", "true")).strip().lower()
            != "false"
        )
        interval_raw = str(
            os.getenv("SIM_FUND_SNAPSHOT_INTERVAL_SECONDS", "30")
        ).strip()
        interval = int(interval_raw or "30")
        if snapshot_enabled and interval > 0:
            from backend.services.trade.redis_client import redis_client
            from backend.services.trade.simulation.services.fund_snapshot_service import (
                SimulationFundSnapshotWorker,
            )

            sim_fund_snapshot_worker = SimulationFundSnapshotWorker(
                redis_client, interval_seconds=interval
            )
            await sim_fund_snapshot_worker.start()
    except Exception as e:
        app.state.startup_healthy = False
        logger.error(
            "trade simulation fund snapshot worker start failed: %s", e, exc_info=True
        )

    # 模拟盘托管调度后台任务：按 live_trade_config 到点创建自动托管执行任务
    try:
        scheduler_enabled = (
            str(os.getenv("SIM_HOSTED_SCHEDULER_ENABLED", "true")).strip().lower()
            != "false"
        )
        interval_raw = str(
            os.getenv("SIM_HOSTED_SCHEDULER_INTERVAL_SECONDS", "30")
        ).strip()
        interval = int(interval_raw or "30")
        if scheduler_enabled and interval > 0:
            from backend.services.trade.redis_client import redis_client
            from backend.services.trade.services.simulation_hosted_scheduler import (
                SimulationHostedScheduler,
            )

            simulation_hosted_scheduler = SimulationHostedScheduler(
                redis_client,
                interval_seconds=interval,
            )
            await simulation_hosted_scheduler.start()
    except Exception as e:
        app.state.startup_healthy = False
        logger.error(
            "trade simulation hosted scheduler start failed: %s", e, exc_info=True
        )

    # SIMULATION 沙箱进程池（用于策略沙箱执行）
    try:
        from backend.services.trade.sandbox.manager import sandbox_manager

        sandbox_manager.start_pool()
        sandbox_pool_started = True
    except Exception as e:
        app.state.startup_healthy = False
        logger.error("trade sandbox worker pool start failed: %s", e, exc_info=True)

    # 容器重启后从 Redis active strategy 状态恢复模拟盘沙箱进程
    try:
        restore_enabled = (
            str(os.getenv("SIM_RUNTIME_RESTORE_ENABLED", "true")).strip().lower()
            != "false"
        )
        if restore_enabled:
            from backend.services.trade.redis_client import redis_client
            from backend.services.trade.services.simulation_runtime_restorer import (
                SimulationRuntimeRestorer,
            )

            simulation_runtime_restorer = SimulationRuntimeRestorer(redis_client)
            await simulation_runtime_restorer.restore_all()
            app.state.simulation_runtime_restorer = simulation_runtime_restorer
    except Exception as e:
        logger.error("trade simulation runtime restore failed: %s", e, exc_info=True)

    # 启动沙箱信号消费者 (修复链路断裂)
    try:
        from backend.services.trade.services.sandbox_signal_consumer import (
            SandboxSignalConsumer,
        )
        from backend.services.trade.redis_client import redis_client

        sim_consumer = SandboxSignalConsumer(redis_client)
        sandbox_signal_consumer_task = asyncio.create_task(
            sim_consumer.start(),
            name="sandbox-signal-consumer",
        )
        app.state.sandbox_signal_consumer = sim_consumer
        logger.info("trade sandbox signal consumer task started")
    except Exception as e:
        # 信号消费者失败目前不作为启动健康的硬性指标，但记录错误
        logger.error("trade sandbox signal consumer start failed: %s", e, exc_info=True)

    healthy = bool(
        app.state.startup_healthy
        and app.state.db_connected
        and app.state.redis_connected
    )
    set_service_health("quantmind-trade", healthy)

    yield

    for task in (
        scanner_task,
        margin_task,
        snapshot_task,
        ledger_settlement_task,
        manual_execution_task,
        simulation_corporate_action_task,
        simulation_pending_order_task,
        simulation_margin_monitor_task,
        simulation_eod_task,
    ):
        if task is None:
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("trade background task stop failed: %s", e)

    if sim_fund_snapshot_worker is not None:
        try:
            await sim_fund_snapshot_worker.stop()
        except Exception as e:
            logger.warning("trade simulation fund snapshot worker stop failed: %s", e)

    if simulation_hosted_scheduler is not None:
        try:
            await simulation_hosted_scheduler.stop()
        except Exception as e:
            logger.warning("trade simulation hosted scheduler stop failed: %s", e)

    if vectorized_matcher_task is not None:
        try:
            from backend.services.trade.services.vectorized_matcher import (
                vectorized_matcher,
            )

            vectorized_matcher.stop()
            vectorized_matcher_task.cancel()
            try:
                await vectorized_matcher_task
            except asyncio.CancelledError:
                pass
        except Exception as e:
            logger.warning("trade vectorized matcher stop failed: %s", e)

    if sandbox_pool_started:
        try:
            from backend.services.trade.sandbox.manager import sandbox_manager

            sandbox_manager.stop_pool()
        except Exception as e:
            logger.warning("trade sandbox worker pool stop failed: %s", e)

    if sandbox_signal_consumer_task is not None:
        try:
            app.state.sandbox_signal_consumer.stop()
            sandbox_signal_consumer_task.cancel()
            try:
                await sandbox_signal_consumer_task
            except asyncio.CancelledError:
                pass
        except Exception as e:
            logger.warning("trade sandbox signal consumer stop failed: %s", e)

    exec_consumer = getattr(app.state, "execution_stream_consumer", None)
    if exec_consumer is not None:
        try:
            await exec_consumer.stop()
        except Exception as e:
            logger.warning("trade execution stream consumer stop failed: %s", e)

    try:
        await close_database()
    except Exception as e:
        logger.warning("trade database close failed: %s", e)

    try:
        redis_client.close()
    except Exception as e:
        logger.warning("trade redis close failed: %s", e)


app = FastAPI(
    title="QuantMind Trade Core",
    version="2.0.0",
    lifespan=lifespan,
    generate_unique_id_function=quantmind_generate_unique_id,
)

install_request_id_middleware(app)
install_error_contract_handlers(app)
install_access_log_middleware(app, service_name="quantmind-trade")

app.include_router(trading_orders.router, prefix="/api/v1/orders", tags=["Orders"])
app.include_router(trading_history.router, prefix="/api/v1/trades", tags=["Trades"])
app.include_router(
    real_trading.router, prefix="/api/v1/real-trading", tags=["Real Trading"]
)
app.include_router(portfolios.router, prefix="/api/v1/portfolios", tags=["Portfolios"])
app.include_router(positions.router, prefix="/api/v1", tags=["Positions"])
app.include_router(
    simulation.router, prefix="/api/v1/simulation", tags=["Simulation-Account"]
)
app.include_router(
    simulation_orders.router, prefix="/api/v1/simulation", tags=["Simulation-Orders"]
)
app.include_router(
    simulation_history.router, prefix="/api/v1/simulation", tags=["Simulation-Trades"]
)
app.include_router(simulation_batch.router)
app.include_router(internal_strategy.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=resolve_cors_origins(logger=logger),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    startup_healthy = bool(getattr(app.state, "startup_healthy", True))
    db_connected = bool(getattr(app.state, "db_connected", startup_healthy))
    redis_connected = bool(getattr(app.state, "redis_connected", startup_healthy))
    healthy = bool(startup_healthy and db_connected and redis_connected)

    set_service_health("quantmind-trade", healthy)
    return {
        "status": "healthy" if healthy else "degraded",
        "service": "quantmind-trade",
        "components": {
            "database": "connected" if db_connected else "disconnected",
            "redis": "connected" if redis_connected else "disconnected",
        },
    }


@app.get("/")
async def root():
    return {"message": "QuantMind Trade Core V2 is running"}


@app.get("/metrics")
async def metrics():
    return build_metrics_response()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002, access_log=False)
