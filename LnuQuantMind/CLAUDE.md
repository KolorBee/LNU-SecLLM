# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuantMind is a quantitative trading platform with Python backend (FastAPI) and Electron/React/TypeScript frontend. The OSS edition uses single-container deployment where all backend services run in one container.

## Backend Services (all via `backend/main_oss.py`)

| Service | Port | Responsibility |
|---------|------|----------------|
| api | 8000 | User auth, strategy management, community |
| engine | 8001 | Qlib backtesting, AI strategy generation, model inference |
| trade | 8002 | Order management, positions, risk control |
| stream | 8003 | Real-time quotes, WebSocket push |

## Commands

### Backend
```bash
# Start all services (Docker)
docker-compose up -d

# Run single service locally
SERVICE_MODE=api python backend/main_oss.py

# Tests (run from project root)
python backend/run_tests.py unit        # Unit tests
python backend/run_tests.py integration # Integration tests
python backend/run_tests.py all         # All tests
python backend/run_tests.py trade-long-short  # QMT MVP chain tests

# Lint/format
ruff check backend/
ruff format backend/
```

### Frontend (Electron app in `electron/`)
```bash
npm install              # Install dependencies
npm run dev              # Development (Electron desktop)
npm run dev:web          # Development (Web browser)
npm run typecheck        # Type check
npm run dashboard:build  # Production build
```

## Architecture Notes

- **Feature engineering**: 48-dim features written to `market_data_daily` table by external service
- **Trade service**: Enforces "local-first" order persistence before external submission
- **Redis DB allocation**: 0=general, 1=auth, 2=trade, 3=market, 4=backtest, 5=cache
- **Shared modules**: `backend/shared/` contains cross-service code (DB manager, Redis client, config, logging)
- **Strategy storage**: `backend/shared/strategy_storage.py` is the single entry point for all strategy CRUD operations

## Data Source Boundaries (CRITICAL)

数据读取有明确边界，不同模块使用不同数据源：

### 本地数据库 (Local PostgreSQL)
- **表**: `stock_daily_latest`
- **用途**: 智能策略回测、模型训练特征
- **配置**: `backend/shared/db_manager.py` (环境变量 `DB_*`)
- **注意**: 本地数据需要通过 ETL 服务同步维护

### 远程行情服务器 (Remote Market Server - 106.53.100.144)
- **PostgreSQL**: `quantmind_market` 用户 (只读)
- **Redis**: `readonly_monitor` 用户 (只读)
- **用途**: 投研平台候选池、实盘行情推送
- **配置文件**:
  - PostgreSQL: `backend/shared/market_db_manager.py` (Fernet 加密密码)
  - Redis: `backend/shared/remote_redis_client.py` (Fernet 加密密码)
- **连接方式**: 密码使用 Fernet 对称加密硬编码，运行时解密

### 开发配置
- `.env` 文件中可覆盖远程连接配置（用于开发调试）：
  - `REMOTE_MARKET_DB_HOST`, `REMOTE_MARKET_DB_PORT`, `REMOTE_MARKET_DB_USER`, `REMOTE_MARKET_DB_PASSWORD`
  - `REMOTE_QUOTE_REDIS_HOST`, `REMOTE_QUOTE_REDIS_PORT`, `REMOTE_QUOTE_REDIS_USER`, `REMOTE_QUOTE_REDIS_PASSWORD`
- 如未配置则使用硬编码加密默认值

## Stock Code Standardization (CRITICAL)

**强制约束：股票代码统一使用 `SH600000` 大写前缀格式，严禁使用 `600000.SH` 后缀格式。**

- **Mandatory Format**: Prefix-based (e.g., `SH600036`). **All internal Redis keys, database fields, and API parameters MUST use this format.**
- **Forbidden Format**: Suffix-based (e.g., `600036.SH`). **Do NOT use this format in any new code or configuration.**
- **Normalization Utilities**: 
  - **Backend**: `backend/shared/stock_utils.py` -> `StockCodeUtil.to_prefix(code)`
  - **Frontend**: `electron/src/utils/portfolioUtils.ts` -> `normalizeStockCode(code)`
- **Redis Key Patterns**:
  - Snapshot: `market:snapshot:sh600036` (lowercase prefix for snapshot keys)
  - SDL Cache: `sdl:2026-04-30:SH600036` (uppercase prefix for SDL keys)
  - Series: `market:series:SH600036` (uppercase prefix for sequences)
- **Market Auto-Identification**:
  - `SH`: 6xxxxx, 9xxxxx
  - `SZ`: 0xxxxx, 3xxxxx, 2xxxxx
  - `BJ`: 4xxxxx, 8xxxxx

## Environment

Required `.env` keys (defaults in `docker-compose.yml`):
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`
- `SECRET_KEY`, `JWT_SECRET_KEY`
- `STORAGE_MODE=local` for OSS edition

## Code Style

- Python: Line length 88, use ruff for linting/formatting
- TypeScript: Run `npm run typecheck` before committing frontend changes

## Development Constraints (CRITICAL)

- **Single-Machine Deployment**: The current project is a standalone/single-machine project. After completing code modifications, always promptly restart or rebuild the Docker container to apply changes.
- **Database Access Restriction**: Aside from the project's own internal database, the system ONLY supports reading market data. **Do NOT connect to or modify any external databases.**
- **Service Name Standardization**: Always standardize and strictly follow the service names defined above (`api`, `engine`, `trade`, `stream`).

## Deployment Workflow

After making code changes, always:
1. **Commit to git**: Create a commit with descriptive message
2. **Deploy to server**: SSH to `quant-server` and pull/deploy updates

```bash
# Local: commit changes
git add .
git commit -m "descriptive message"

# Deploy to quant-server
ssh quant-server "cd /opt/quantmind && git pull && docker-compose restart"
```

## Key Files

- `backend/main_oss.py` - Unified entry point for all backend services
- `backend/run_tests.py` - Test runner with multiple modes
- `backend/shared/` - Shared modules across services
- `docker-compose.yml` - Local deployment configuration
