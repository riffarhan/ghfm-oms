from oms.enums import OrderStatus
from oms.state_machine import TERMINAL_STATES, can_transition, is_terminal


def test_valid_forward_transitions():
    assert can_transition(OrderStatus.PENDING_NEW, OrderStatus.NEW)
    assert can_transition(OrderStatus.NEW, OrderStatus.SENT)
    assert can_transition(OrderStatus.SENT, OrderStatus.ACKNOWLEDGED)
    assert can_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED)
    assert can_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.FILLED)
    assert can_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)


def test_partial_fill_self_transition():
    assert can_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED)


def test_terminal_states_block_all():
    for terminal in TERMINAL_STATES:
        for target in OrderStatus:
            assert not can_transition(terminal, target)


def test_cannot_cancel_filled_order():
    assert not can_transition(OrderStatus.FILLED, OrderStatus.PENDING_CANCEL)
    assert not can_transition(OrderStatus.FILLED, OrderStatus.CANCELLED)


def test_pending_cancel_can_still_fill():
    """Race condition: fill arrives after cancel request sent to venue."""
    assert can_transition(OrderStatus.PENDING_CANCEL, OrderStatus.FILLED)
    assert can_transition(OrderStatus.PENDING_CANCEL, OrderStatus.PARTIALLY_FILLED)


def test_rejection_from_multiple_states():
    for state in [OrderStatus.PENDING_NEW, OrderStatus.NEW, OrderStatus.SENT, OrderStatus.ACKNOWLEDGED]:
        assert can_transition(state, OrderStatus.REJECTED)


def test_invalid_backward_transitions():
    assert not can_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.NEW)
    assert not can_transition(OrderStatus.SENT, OrderStatus.NEW)
    assert not can_transition(OrderStatus.FILLED, OrderStatus.ACKNOWLEDGED)


def test_is_terminal():
    assert is_terminal(OrderStatus.FILLED)
    assert is_terminal(OrderStatus.CANCELLED)
    assert is_terminal(OrderStatus.REJECTED)
    assert not is_terminal(OrderStatus.NEW)
    assert not is_terminal(OrderStatus.PARTIALLY_FILLED)
