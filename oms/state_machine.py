"""
Order lifecycle state machine.

Models the valid state transitions for a trade order, inspired by FIX protocol
OrdStatus (tag 39) and ExecType (tag 150) semantics.

Transition table approach: explicit dict of valid (from -> to) transitions,
rather than scattered if/else logic. This makes the lifecycle auditable and
prevents invalid state changes at the domain level.
"""

import json
from datetime import datetime, timezone

from oms.enums import OrderStatus
from oms.models import Order, OrderEvent


VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING_NEW:      {OrderStatus.NEW, OrderStatus.REJECTED},
    OrderStatus.NEW:              {OrderStatus.SENT, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.SENT:             {OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED},
    OrderStatus.ACKNOWLEDGED:     {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                                   OrderStatus.PENDING_CANCEL, OrderStatus.REJECTED},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                                   OrderStatus.PENDING_CANCEL},
    OrderStatus.PENDING_CANCEL:   {OrderStatus.CANCELLED, OrderStatus.FILLED,
                                   OrderStatus.PARTIALLY_FILLED},
    OrderStatus.FILLED:           set(),
    OrderStatus.CANCELLED:        set(),
    OrderStatus.REJECTED:         set(),
}

TERMINAL_STATES = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


class InvalidTransitionError(Exception):
    def __init__(self, current: OrderStatus, target: OrderStatus):
        self.current = current
        self.target = target
        super().__init__(f"Invalid transition: {current.value} -> {target.value}")


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


def is_terminal(status: OrderStatus) -> bool:
    return status in TERMINAL_STATES


def transition(order: Order, target: OrderStatus, details: dict | None = None) -> OrderEvent:
    """
    Perform a state transition on an order. Creates an audit event.
    Raises InvalidTransitionError if the transition is not allowed.
    """
    current = OrderStatus(order.status)
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)

    from_status = order.status
    order.status = target.value
    order.updated_at = datetime.now(timezone.utc)

    event = OrderEvent(
        order_id=order.id,
        event_type="STATE_CHANGE",
        from_status=from_status,
        to_status=target.value,
        details=json.dumps(details) if details else None,
        timestamp=datetime.now(timezone.utc),
    )
    return event
