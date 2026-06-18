#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "${ROOT_DIR}"

if [ ! -f ".env" ]; then
  echo "Missing .env in ${ROOT_DIR}"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing Python runtime: ${ROOT_DIR}/.venv/bin/python"
  exit 1
fi

set -a
. ./.env
set +a

# 宿主机执行时，容器网络别名 quantmind-postgresql 不可解析，统一改连本机映射端口。
if [[ "${DATABASE_URL:-}" == *"@quantmind-postgresql:"* ]]; then
  DATABASE_URL="${DATABASE_URL/@quantmind-postgresql:/@127.0.0.1:}"
  export DATABASE_URL
fi

if [ "${DB_HOST:-}" = "quantmind-postgresql" ]; then
  export DB_HOST="127.0.0.1"
fi

if [ "${DB_MASTER_HOST:-}" = "quantmind-postgresql" ]; then
  export DB_MASTER_HOST="127.0.0.1"
fi

echo "[1/3] Import corporate actions from CSV..."
.venv/bin/python backend/services/trade/scripts/import_simulation_corporate_actions.py --replace-existing "$@"

echo "[2/3] Apply due corporate actions..."
.venv/bin/python - <<'PY'
import asyncio
from backend.services.trade.simulation.services.corporate_action_service import SimulationCorporateActionService

async def main():
    applied = await SimulationCorporateActionService.apply_due_actions()
    print(f"applied_count={applied}")

asyncio.run(main())
PY

echo "[3/3] Print status summary..."
.venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import func, select
from backend.shared.database_manager_v2 import get_session
from backend.services.trade.simulation.models.corporate_action import SimulationCorporateAction

async def main():
    async with get_session(read_only=True) as session:
        rows = await session.execute(
            select(SimulationCorporateAction.status, func.count())
            .group_by(SimulationCorporateAction.status)
            .order_by(SimulationCorporateAction.status.asc())
        )
        for status, count in rows.all():
            print(f"status[{status}]={count}")

asyncio.run(main())
PY
