"""
Execution service — processes venue execution reports and updates positions.

This is the callback target for the venue simulator. In production, it would
receive FIX ExecutionReport messages from the FIX engine.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oms.enums import OrderSide, OrderStatus
from oms.models import Fill, Order, OrderEvent, Position
from oms.risk_engine import REFERENCE_PRICES
from oms.state_machine import can_transition, is_terminal


async def process_execution_report(
    session_factory: async_sessionmaker[AsyncSession],
    report: dict,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            order = await session.get(Order, report["OrderID"])
            if order is None:
                return

            exec_type = report["ExecType"]
            target_status = OrderStatus(report["OrdStatus"])
            current_status = OrderStatus(order.status)

            if is_terminal(current_status):
                return

            if not can_transition(current_status, target_status):
                return

            if exec_type == "NEW":
                _handle_acknowledged(order, target_status, session, report)

            elif exec_type == "TRADE":
                await _handle_fill(order, target_status, session, report)

            elif exec_type == "CANCELLED":
                _handle_cancelled(order, target_status, session, report)

            elif exec_type == "REJECTED":
                _handle_rejected(order, target_status, session, report)


def _handle_acknowledged(
    order: Order, target: OrderStatus, session: AsyncSession, report: dict,
) -> None:
    order.status = target.value
    order.updated_at = datetime.now(timezone.utc)
    session.add(OrderEvent(
        order_id=order.id,
        event_type="ACKNOWLEDGED",
        from_status=OrderStatus.SENT.value,
        to_status=target.value,
        details=json.dumps({"exec_id": report["ExecID"]}),
        timestamp=datetime.now(timezone.utc),
    ))


async def _handle_fill(
    order: Order, target: OrderStatus, session: AsyncSession, report: dict,
) -> None:
    last_qty = Decimal(report["LastQty"])
    last_px = Decimal(report["LastPx"])
    cum_qty = Decimal(report["CumQty"])
    avg_px = Decimal(report["AvgPx"])

    fill = Fill(
        order_id=order.id,
        exec_id=report["ExecID"],
        fill_quantity=last_qty,
        fill_price=last_px,
        commission=Decimal("0"),  # Simplified for prototype
        venue=order.venue,
        filled_at=datetime.now(timezone.utc),
    )
    session.add(fill)

    previous_status = order.status
    order.filled_quantity = cum_qty
    order.average_price = avg_px
    order.status = target.value
    order.updated_at = datetime.now(timezone.utc)

    session.add(OrderEvent(
        order_id=order.id,
        event_type="FILL",
        from_status=previous_status,
        to_status=target.value,
        details=json.dumps({
            "exec_id": report["ExecID"],
            "fill_qty": str(last_qty),
            "fill_price": str(last_px),
            "cum_qty": str(cum_qty),
            "avg_px": str(avg_px),
            "leaves_qty": report.get("LeavesQty"),
        }),
        timestamp=datetime.now(timezone.utc),
    ))

    await _update_position(session, order, last_qty, last_px)


async def _update_position(
    session: AsyncSession, order: Order, fill_qty: Decimal, fill_price: Decimal,
) -> None:
    result = await session.execute(select(Position).where(Position.symbol == order.symbol))
    position = result.scalar_one_or_none()

    signed_qty = fill_qty if order.side == OrderSide.BUY.value else -fill_qty

    if position is None:
        ref_price = REFERENCE_PRICES.get(order.symbol, fill_price)
        position = Position(
            symbol=order.symbol,
            asset_class=order.asset_class,
            quantity=signed_qty,
            average_cost=fill_price,
            current_price=ref_price,
            unrealized_pnl=(ref_price - fill_price) * signed_qty,
            realized_pnl=Decimal("0"),
        )
        session.add(position)
        return

    old_qty = position.quantity
    new_qty = old_qty + signed_qty

    if old_qty == Decimal("0"):
        position.average_cost = fill_price
    elif (old_qty > 0 and signed_qty > 0) or (old_qty < 0 and signed_qty < 0):
        # Increasing position: weighted average cost
        total_cost = abs(old_qty) * position.average_cost + abs(signed_qty) * fill_price
        position.average_cost = total_cost / abs(new_qty)
    else:
        # Reducing or closing: realize P&L on the closed portion
        closed_qty = min(abs(signed_qty), abs(old_qty))
        pnl_per_unit = fill_price - position.average_cost
        if old_qty < 0:
            pnl_per_unit = -pnl_per_unit
        position.realized_pnl += pnl_per_unit * closed_qty

        # If flipping direction, set new average cost for the flipped portion
        if abs(signed_qty) > abs(old_qty):
            position.average_cost = fill_price

    position.quantity = new_qty
    ref_price = REFERENCE_PRICES.get(order.symbol, fill_price)
    position.current_price = ref_price
    if new_qty != Decimal("0"):
        position.unrealized_pnl = (ref_price - position.average_cost) * new_qty
    else:
        position.unrealized_pnl = Decimal("0")
    position.updated_at = datetime.now(timezone.utc)


def _handle_cancelled(
    order: Order, target: OrderStatus, session: AsyncSession, report: dict,
) -> None:
    order.status = target.value
    order.updated_at = datetime.now(timezone.utc)
    session.add(OrderEvent(
        order_id=order.id,
        event_type="CANCELLED",
        from_status=OrderStatus.PENDING_CANCEL.value,
        to_status=target.value,
        details=json.dumps({"exec_id": report["ExecID"]}),
        timestamp=datetime.now(timezone.utc),
    ))


def _handle_rejected(
    order: Order, target: OrderStatus, session: AsyncSession, report: dict,
) -> None:
    reason = report.get("Text", "Unknown reason")
    previous_status = order.status
    order.status = target.value
    order.reject_reason = reason
    order.updated_at = datetime.now(timezone.utc)
    session.add(OrderEvent(
        order_id=order.id,
        event_type="VENUE_REJECTED",
        from_status=previous_status,
        to_status=target.value,
        details=json.dumps({"reason": reason, "exec_id": report["ExecID"]}),
        timestamp=datetime.now(timezone.utc),
    ))
