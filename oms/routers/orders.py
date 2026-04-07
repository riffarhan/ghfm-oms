from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from oms.database import get_db
from oms.enums import OrderStatus
from oms.schemas import OrderCreateRequest, OrderDetailResponse, OrderResponse
from oms.services import order_service
from oms.state_machine import InvalidTransitionError

router = APIRouter()


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    request: OrderCreateRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.create_order(db, request, req.app.state.venue)
    return OrderResponse.model_validate(order)


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    status: OrderStatus | None = None,
    symbol: str | None = None,
    trader: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    orders = await order_service.list_orders(db, status=status, symbol=symbol, trader=trader, skip=skip, limit=limit)
    return [OrderResponse.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    order = await order_service.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetailResponse.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(order_id: str, req: Request, db: AsyncSession = Depends(get_db)):
    try:
        order = await order_service.cancel_order(db, order_id, req.app.state.venue)
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
