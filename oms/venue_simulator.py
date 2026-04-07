"""
Venue simulator — mock broker/exchange.

Simulates a trading venue that accepts orders and produces FIX-inspired
execution reports. Runs in-process using asyncio tasks to simulate network
latency without blocking the API.

In production, this module would be replaced by a FIX gateway adapter
(e.g., QuickFIX/Python) connecting to real prime brokers and exchanges.
"""

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal

from oms.enums import OrderSide, OrderStatus, OrderType
from oms.models import Order
from oms.risk_engine import REFERENCE_PRICES


class VenueSimulator:
    def __init__(
        self,
        execution_callback: Callable[[dict], Awaitable[None]],
        fill_probability: float = 0.85,
        partial_fill_probability: float = 0.30,
        min_latency_ms: int = 50,
        max_latency_ms: int = 500,
    ):
        self._callback = execution_callback
        self._fill_prob = fill_probability
        self._partial_prob = partial_fill_probability
        self._min_lat = min_latency_ms
        self._max_lat = max_latency_ms
        self._tasks: dict[str, asyncio.Task] = {}

    async def submit_order(self, order: Order) -> None:
        task = asyncio.create_task(self._process_order(order))
        self._tasks[order.id] = task

    async def cancel_order(self, order: Order) -> None:
        task = self._tasks.get(order.id)
        if task and not task.done():
            task.cancel()
        await self._send_report(order, exec_type="CANCELLED", ord_status=OrderStatus.CANCELLED.value)

    async def _process_order(self, order: Order) -> None:
        try:
            # Simulate network latency for acknowledgment
            await asyncio.sleep(random.randint(self._min_lat, self._max_lat) / 1000)

            # Send acknowledgment (FIX ExecType=New)
            await self._send_report(order, exec_type="NEW", ord_status=OrderStatus.ACKNOWLEDGED.value)

            # Simulate matching latency
            await asyncio.sleep(random.randint(self._min_lat, self._max_lat) / 1000)

            # Determine outcome
            roll = random.random()
            if roll > self._fill_prob:
                # Rejection
                await self._send_report(
                    order,
                    exec_type="REJECTED",
                    ord_status=OrderStatus.REJECTED.value,
                    text="Venue rejected: insufficient liquidity",
                )
                return

            remaining = order.quantity
            cum_qty = Decimal("0")
            cum_value = Decimal("0")

            if random.random() < self._partial_prob:
                # Partial fills (1-3 rounds)
                rounds = random.randint(1, 3)
                for i in range(rounds):
                    fill_qty = (remaining * Decimal(str(random.uniform(0.2, 0.5)))).quantize(Decimal("1"))
                    fill_qty = max(fill_qty, Decimal("1"))
                    if fill_qty >= remaining:
                        fill_qty = remaining

                    fill_price = self._simulate_price(order)
                    cum_qty += fill_qty
                    cum_value += fill_qty * fill_price
                    remaining -= fill_qty

                    await self._send_report(
                        order,
                        exec_type="TRADE",
                        ord_status=OrderStatus.PARTIALLY_FILLED.value if remaining > 0 else OrderStatus.FILLED.value,
                        last_qty=fill_qty,
                        last_px=fill_price,
                        cum_qty=cum_qty,
                        avg_px=(cum_value / cum_qty).quantize(Decimal("0.00000001")),
                        leaves_qty=remaining,
                    )

                    if remaining <= 0:
                        return

                    await asyncio.sleep(random.randint(100, 300) / 1000)

            # Fill the rest (or full fill if no partials)
            fill_price = self._simulate_price(order)
            cum_qty += remaining
            cum_value += remaining * fill_price

            await self._send_report(
                order,
                exec_type="TRADE",
                ord_status=OrderStatus.FILLED.value,
                last_qty=remaining,
                last_px=fill_price,
                cum_qty=cum_qty,
                avg_px=(cum_value / cum_qty).quantize(Decimal("0.00000001")),
                leaves_qty=Decimal("0"),
            )
        except asyncio.CancelledError:
            pass  # Order was cancelled

    def _simulate_price(self, order: Order) -> Decimal:
        ref = REFERENCE_PRICES.get(order.symbol, Decimal("100.00"))
        # Slippage: 0-50 basis points
        slippage = Decimal(str(random.uniform(-0.005, 0.005)))
        simulated = ref * (1 + slippage)

        if order.order_type == OrderType.LIMIT.value and order.limit_price:
            if order.side == OrderSide.BUY.value:
                simulated = min(simulated, order.limit_price)
            else:
                simulated = max(simulated, order.limit_price)

        return simulated.quantize(Decimal("0.01"))

    async def _send_report(
        self,
        order: Order,
        exec_type: str,
        ord_status: str,
        last_qty: Decimal | None = None,
        last_px: Decimal | None = None,
        cum_qty: Decimal | None = None,
        avg_px: Decimal | None = None,
        leaves_qty: Decimal | None = None,
        text: str | None = None,
    ) -> None:
        """Send a FIX-inspired execution report via callback."""
        report = {
            "OrderID": order.id,                          # FIX tag 37
            "ClOrdID": order.client_order_id,             # FIX tag 11
            "ExecID": str(uuid.uuid4())[:12],             # FIX tag 17
            "ExecType": exec_type,                        # FIX tag 150
            "OrdStatus": ord_status,                      # FIX tag 39
            "Symbol": order.symbol,                       # FIX tag 55
            "Side": order.side,                           # FIX tag 54
            "LastQty": str(last_qty) if last_qty is not None else None,    # FIX tag 32
            "LastPx": str(last_px) if last_px is not None else None,     # FIX tag 31
            "CumQty": str(cum_qty) if cum_qty is not None else None,     # FIX tag 14
            "AvgPx": str(avg_px) if avg_px is not None else None,        # FIX tag 6
            "LeavesQty": str(leaves_qty) if leaves_qty is not None else None,  # FIX tag 151
            "TransactTime": datetime.now(timezone.utc).isoformat(),  # FIX tag 60
            "Text": text,                                 # FIX tag 58
        }
        await self._callback(report)
