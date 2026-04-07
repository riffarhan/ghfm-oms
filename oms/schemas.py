from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from oms.enums import AssetClass, OrderSide, OrderStatus, OrderType, TimeInForce


# ── Requests ──


class OrderCreateRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32, examples=["AAPL"])
    asset_class: AssetClass
    side: OrderSide
    order_type: OrderType
    quantity: Decimal = Field(..., gt=0, examples=[Decimal("5000")])
    limit_price: Decimal | None = Field(None, gt=0, examples=[Decimal("186.00")])
    time_in_force: TimeInForce = TimeInForce.DAY
    trader: str = Field(..., min_length=1, max_length=64, examples=["pm_macro"])
    strategy: str | None = Field(None, max_length=64, examples=["US_TECH_MOMENTUM"])

    @model_validator(mode="after")
    def validate_limit_price(self) -> Self:
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")
        return self


# ── Responses ──


class FillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    exec_id: str
    fill_quantity: Decimal
    fill_price: Decimal
    commission: Decimal
    venue: str
    filled_at: datetime


class OrderEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    details: str | None
    timestamp: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    client_order_id: str
    symbol: str
    asset_class: str
    side: str
    order_type: str
    quantity: Decimal
    limit_price: Decimal | None
    time_in_force: str
    status: str
    filled_quantity: Decimal
    average_price: Decimal
    trader: str
    strategy: str | None
    venue: str
    reject_reason: str | None
    created_at: datetime
    updated_at: datetime


class OrderDetailResponse(OrderResponse):
    fills: list[FillResponse] = []
    events: list[OrderEventResponse] = []


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    asset_class: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    updated_at: datetime


class RiskCheckResponse(BaseModel):
    passed: bool
    check_name: str
    message: str


class HealthResponse(BaseModel):
    status: str
    system: str
    version: str
