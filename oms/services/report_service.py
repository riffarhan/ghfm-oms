"""
Report service — generates trade files, position reports, and reconciliation.

Trade files go to the prime broker for settlement.
Position reports go to the fund administrator for NAV calculation.
Reconciliation compares internal positions against external records.
"""

import io
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oms.enums import AssetClass, OrderStatus
from oms.models import Fill, Order, Position


SETTLEMENT_OFFSETS = {
    AssetClass.EQUITY.value: 1,        # T+1
    AssetClass.FX.value: 0,            # T+0 (spot: T+2, but simplified)
    AssetClass.COMMODITY.value: 1,     # T+1
    AssetClass.FIXED_INCOME.value: 2,  # T+2
}


async def generate_trade_file(session: AsyncSession, trade_date: date | None = None) -> str:
    if trade_date is None:
        trade_date = datetime.now(timezone.utc).date()

    stmt = (
        select(Fill, Order)
        .join(Order, Fill.order_id == Order.id)
        .where(Order.status.in_([OrderStatus.FILLED.value, OrderStatus.PARTIALLY_FILLED.value]))
    )
    result = await session.execute(stmt)
    rows = result.all()

    records = []
    for fill, order in rows:
        offset = SETTLEMENT_OFFSETS.get(order.asset_class, 1)
        settlement_date = trade_date + timedelta(days=offset)
        notional = fill.fill_quantity * fill.fill_price

        records.append({
            "TradeDate": trade_date.isoformat(),
            "SettlementDate": settlement_date.isoformat(),
            "AccountID": "GHFM-MACRO-001",
            "ClientOrderID": order.client_order_id,
            "ExecID": fill.exec_id,
            "Symbol": order.symbol,
            "AssetClass": order.asset_class,
            "Side": order.side,
            "Quantity": float(fill.fill_quantity),
            "Price": float(fill.fill_price),
            "Notional": float(notional),
            "Currency": "USD",
            "Commission": float(fill.commission),
            "Venue": fill.venue,
            "Strategy": order.strategy or "",
            "Trader": order.trader,
        })

    if not records:
        return "TradeDate,SettlementDate,AccountID,ClientOrderID,ExecID,Symbol,AssetClass,Side,Quantity,Price,Notional,Currency,Commission,Venue,Strategy,Trader\n"

    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


async def generate_position_report(session: AsyncSession) -> str:
    result = await session.execute(select(Position).where(Position.quantity != 0))
    positions = result.scalars().all()

    total_market_value = Decimal("0")
    records = []
    for p in positions:
        market_value = p.quantity * p.current_price
        total_market_value += abs(market_value)

    for p in positions:
        market_value = p.quantity * p.current_price
        pct_nav = (abs(market_value) / total_market_value * 100) if total_market_value else Decimal("0")
        records.append({
            "ReportDate": datetime.now(timezone.utc).date().isoformat(),
            "AccountID": "GHFM-MACRO-001",
            "Symbol": p.symbol,
            "AssetClass": p.asset_class,
            "Quantity": float(p.quantity),
            "AverageCost": float(p.average_cost),
            "CurrentPrice": float(p.current_price),
            "MarketValue": float(market_value),
            "UnrealizedPnL": float(p.unrealized_pnl),
            "RealizedPnL": float(p.realized_pnl),
            "TotalPnL": float(p.unrealized_pnl + p.realized_pnl),
            "Currency": "USD",
            "PercentOfNAV": round(float(pct_nav), 2),
        })

    if not records:
        return "ReportDate,AccountID,Symbol,AssetClass,Quantity,AverageCost,CurrentPrice,MarketValue,UnrealizedPnL,RealizedPnL,TotalPnL,Currency,PercentOfNAV\n"

    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


async def generate_reconciliation(session: AsyncSession) -> dict:
    """
    Three-way reconciliation: OMS vs prime broker vs fund admin.

    In production, prime broker and fund admin positions come from external
    files (SFTP/API). Here we simulate them with small random discrepancies
    to demonstrate break detection.
    """
    result = await session.execute(select(Position).where(Position.quantity != 0))
    positions = result.scalars().all()

    details = []
    matched = 0
    breaks = 0

    for p in positions:
        oms_qty = float(p.quantity)
        oms_value = float(p.quantity * p.current_price)

        # Simulate prime broker data (small rounding difference ~5% chance)
        if random.random() < 0.05:
            pb_qty = oms_qty + random.choice([-1, 1]) * random.randint(1, 10)
        else:
            pb_qty = oms_qty
        pb_value = pb_qty * float(p.current_price)

        # Simulate fund admin data (occasional FX rate difference)
        if random.random() < 0.08:
            admin_qty = oms_qty
            admin_value = oms_value * random.uniform(0.998, 1.002)
        else:
            admin_qty = oms_qty
            admin_value = oms_value

        qty_match = oms_qty == pb_qty == admin_qty
        value_tolerance = abs(oms_value) * 0.001 if oms_value != 0 else 0.01
        value_match = abs(oms_value - pb_value) < value_tolerance and abs(oms_value - admin_value) < value_tolerance

        if qty_match and value_match:
            status = "MATCHED"
            matched += 1
            break_details = None
        else:
            status = "BREAK"
            breaks += 1
            issues = []
            if oms_qty != pb_qty:
                issues.append(f"PB qty mismatch: OMS={oms_qty}, PB={pb_qty}")
            if abs(oms_value - admin_value) >= value_tolerance:
                issues.append(f"Admin value mismatch: OMS={oms_value:.2f}, Admin={admin_value:.2f}")
            break_details = "; ".join(issues)

        details.append({
            "symbol": p.symbol,
            "asset_class": p.asset_class,
            "oms_quantity": oms_qty,
            "pb_quantity": pb_qty,
            "admin_quantity": admin_qty,
            "oms_value": round(oms_value, 2),
            "pb_value": round(pb_value, 2),
            "admin_value": round(admin_value, 2),
            "status": status,
            "break_details": break_details,
        })

    return {
        "report_date": datetime.now(timezone.utc).date().isoformat(),
        "account_id": "GHFM-MACRO-001",
        "status": "BREAKS_FOUND" if breaks > 0 else "RECONCILED",
        "summary": {
            "total_positions": len(positions),
            "matched": matched,
            "breaks": breaks,
        },
        "details": details,
    }
