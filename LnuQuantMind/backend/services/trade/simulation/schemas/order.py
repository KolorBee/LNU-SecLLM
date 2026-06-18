"""
Simulation order schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.services.trade.simulation.models.order import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradingMode,
)


class SimOrderBase(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0)
    price: float | None = Field(None, gt=0)
    remarks: str | None = Field(None, max_length=500)


class SimOrderCreate(SimOrderBase):
    portfolio_id: int = Field(0, ge=0)
    strategy_id: int | None = Field(None, gt=0)
    trading_mode: TradingMode = TradingMode.SIMULATION
    client_order_id: str | None = Field(None, max_length=64)
    time_in_force: str = Field("DAY", max_length=16)
    expires_at: datetime | None = None
    # 多空/融券字段
    trade_action: str | None = Field(None, max_length=32)
    position_side: str = Field("long", max_length=16)
    is_margin_trade: bool = False

    @field_validator("time_in_force")
    @classmethod
    def validate_time_in_force(cls, value: str) -> str:
        normalized = str(value or "DAY").strip().upper() or "DAY"
        if normalized not in {"DAY", "GTD", "IOC"}:
            raise ValueError("time_in_force must be one of DAY/GTD/IOC")
        return normalized

    @model_validator(mode="after")
    def validate_expiry_rules(self):
        if self.time_in_force == "GTD" and self.expires_at is None:
            raise ValueError("expires_at is required when time_in_force=GTD")
        return self


class SimOrderCancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=200)


class SimOrderResponse(SimOrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: UUID4
    tenant_id: str
    user_id: int
    portfolio_id: int
    strategy_id: int | None
    client_order_id: str | None
    trigger_source: str
    time_in_force: str
    expires_at: datetime | None
    trading_mode: TradingMode
    status: OrderStatus
    filled_quantity: float
    average_price: float | None
    order_value: float
    filled_value: float
    commission: float
    submitted_at: datetime | None
    filled_at: datetime | None
    cancelled_at: datetime | None
    execution_model: str
    price_source: str | None
    created_at: datetime
    updated_at: datetime
