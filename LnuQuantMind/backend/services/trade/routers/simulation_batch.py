from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.services.trade.deps import AuthContext, get_auth_context, get_db
from backend.services.trade.services.simulation_settler import settler

router = APIRouter(
    prefix="/api/v1/simulation/batch", tags=["Simulation Batch Operations"]
)


@router.post("/step")
async def trigger_simulation_step(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """
    手动触发一次模拟交易的步进（结算）
    用于测试“单一写权限”和“数据驱动模拟盘”流程
    """
    user_id = payload.get("user_id")
    strategy_id = payload.get("strategy_id")
    tenant_id = (
        str(payload.get("tenant_id") or auth.tenant_id or "default").strip()
        or "default"
    )

    if not user_id or not strategy_id:
        raise HTTPException(status_code=400, detail="Missing user_id or strategy_id")
    if str(user_id).strip() != str(auth.user_id).strip():
        raise HTTPException(status_code=403, detail="Forbidden user_id override")
    if tenant_id != str(auth.tenant_id or "default").strip():
        raise HTTPException(status_code=403, detail="Forbidden tenant_id override")

    try:
        result = await settler.run_daily_settlement(
            db,
            int(user_id),
            strategy_id,
            tenant_id=tenant_id,
        )
        return {
            "status": "success",
            "message": f"Daily simulation step completed for user {user_id}",
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
