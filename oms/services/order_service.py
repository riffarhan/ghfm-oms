"""
Order service — orchestrates order creation, validation, and lifecycle.

This is the main entry point for the order workflow:
  1. Create order in PENDING_NEW
  2. Run pre-trade risk checks
  3. On pass: transition to NEW -> SENT, submit to venue
  4. On fail: transition to REJECTED with reasons
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oms.enums import OrderStatus
from oms.models import Order, OrderEvent, Position
from oms.risk_engine import check_order
from oms.schemas import OrderCreateRequest
from oms.state_machine import InvalidTransitionError, can_transition, transition
from oms.venue_simulator import VenueSimulator

_order_counter: int = 0


def _generate_client_order_id() -> str:
    global _order_counter
    _order_counter += 1
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ORD-{date_str}-{_order_counter:04d}"


async def create_order(
    session: AsyncSession,
    request: OrderCreateRequest,
    venue: VenueSimulator,
) -> Order:
    order = Order(
        client_order_id=_generate_client_order_id(),
        symbol=request.symbol,
        asset_class=request.asset_class.value,
        side=request.side.value,
        order_type=request.order_type.value,
        quantity=request.quantity,
        limit_price=request.limit_price,
        time_in_force=request.time_in_force.value,
        status=OrderStatus.PENDING_NEW.value,
        trader=request.trader,
        strategy=request.strategy,
    )
    session.add(order)
    await session.flush()

    # Audit: order created
    session.add(OrderEvent(
        order_id=order.id,
        event_type="ORDER_CREATED",
        from_status=None,
        to_status=OrderStatus.PENDING_NEW.value,
        details=json.dumps({
            "symbol": request.symbol,
            "side": request.side.value,
            "order_type": request.order_type.value,
            "quantity": str(request.quantity),
            "limit_price": str(request.limit_price) if request.limit_price else None,
            "trader": request.trader,
        }),
        timestamp=datetime.now(timezone.utc),
    ))

    # Load current positions for risk checks
    result = await session.execute(select(Position))
    positions = {p.symbol: p for p in result.scalars().all()}

    # Pre-trade risk checks
    risk_results = check_order(
        symbol=request.symbol,
        asset_class=request.asset_class.value,
        order_type=request.order_type.value,
        quantity=request.quantity,
        limit_price=request.limit_price,
        trader=request.trader,
        positions=positions,
    )

    failures = [r for r in risk_results if not r.passed]

    if failures:
        reasons = "; ".join(f"[{r.check_name}] {r.message}" for r in failures)
        order.status = OrderStatus.REJECTED.value
        order.reject_reason = reasons
        order.updated_at = datetime.now(timezone.utc)
        session.add(OrderEvent(
            order_id=order.id,
            event_type="RISK_REJECTED",
            from_status=OrderStatus.PENDING_NEW.value,
            to_status=OrderStatus.REJECTED.value,
            details=json.dumps({"failures": [{"check": r.check_name, "message": r.message} for r in failures]}),
            timestamp=datetime.now(timezone.utc),
        ))
        await session.commit()
        return order

    # Risk passed -> NEW
    session.add(OrderEvent(
        order_id=order.id,
        event_type="RISK_PASSED",
        from_status=OrderStatus.PENDING_NEW.value,
        to_status=OrderStatus.NEW.value,
        details=json.dumps({"checks_passed": len(risk_results)}),
        timestamp=datetime.now(timezone.utc),
    ))
    order.status = OrderStatus.NEW.value

    # NEW -> SENT
    order.status = OrderStatus.SENT.value
    order.updated_at = datetime.now(timezone.utc)
    session.add(OrderEvent(
        order_id=order.id,
        event_type="ORDER_SENT",
        from_status=OrderStatus.NEW.value,
        to_status=OrderStatus.SENT.value,
        details=json.dumps({"venue": order.venue}),
        timestamp=datetime.now(timezone.utc),
    ))

    await session.commit()

    # Submit to venue (fire and forget — venue callbacks handle the rest)
    await venue.submit_order(order)

    return order


async def cancel_order(
    session: AsyncSession,
    order_id: str,
    venue: VenueSimulator,
) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    current = OrderStatus(order.status)
    if not can_transition(current, OrderStatus.PENDING_CANCEL):
        raise InvalidTransitionError(current, OrderStatus.PENDING_CANCEL)

    event = transition(order, OrderStatus.PENDING_CANCEL, {"reason": "Client requested cancellation"})
    session.add(event)
    await session.commit()

    await venue.cancel_order(order)
    return order


async def get_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.get(Order, order_id)


async def list_orders(
    session: AsyncSession,
    status: OrderStatus | None = None,
    symbol: str | None = None,
    trader: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Order]:
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status.value)
    if symbol:
        stmt = stmt.where(Order.symbol == symbol)
    if trader:
        stmt = stmt.where(Order.trader == trader)
    stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
