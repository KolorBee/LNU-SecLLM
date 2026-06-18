"""
Auth middleware adapter for trade service.
Re-exports get_current_user_id using the trade service's own auth mechanism.
"""

from fastapi import Depends, HTTPException

from backend.services.trade.deps import AuthContext, get_auth_context


async def get_current_user_id(auth: AuthContext = Depends(get_auth_context)) -> int:
    """获取当前用户 ID (adapted from portfolio_service)"""
    try:
        return int(auth.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid user_id in token")


async def get_current_tenant_id(auth: AuthContext = Depends(get_auth_context)) -> str:
    tenant_id = str(auth.tenant_id or "").strip()
    return tenant_id or "default"
