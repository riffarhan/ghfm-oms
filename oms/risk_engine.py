"""
Pre-trade risk engine.

Runs synchronous validation checks before an order is accepted into the OMS.
All checks run regardless of individual failures, so the trader sees every
issue at once rather than fixing them one at a time.

In production, these limits would be stored in a database and configurable
per trader/desk/fund. Hardcoded here for the prototype.
"""

from dataclasses import dataclass
from decimal import Decimal

from oms.enums import AssetClass, OrderType
from oms.models import Position


REFERENCE_PRICES: dict[str, Decimal] = {
    # Equities
    "AAPL": Decimal("185.50"),
    "MSFT": Decimal("420.00"),
    "NVDA": Decimal("850.00"),
    "TSM": Decimal("165.00"),
    "9984.T": Decimal("8500.00"),
    # FX
    "USDJPY": Decimal("152.50"),
    "EURUSD": Decimal("1.0850"),
    "GBPUSD": Decimal("1.2650"),
    "AUDUSD": Decimal("0.6550"),
    "USDSGD": Decimal("1.3450"),
    # Commodities
    "GCQ26": Decimal("2350.00"),
    "CLQ26": Decimal("78.50"),
    # Fixed income
    "TY1": Decimal("110.25"),
    "JGB1": Decimal("145.50"),
}

MAX_ORDER_QUANTITY: dict[str, Decimal] = {
    AssetClass.EQUITY.value: Decimal("100000"),
    AssetClass.FX.value: Decimal("50000000"),
    AssetClass.COMMODITY.value: Decimal("500"),
    AssetClass.FIXED_INCOME.value: Decimal("1000"),
}

MAX_NOTIONAL = Decimal("10000000")
MAX_POSITION_PER_SYMBOL = Decimal("500000")

# GHFM explicitly avoids China domestic equity
RESTRICTED_SYMBOLS = {"600519.SS", "000858.SZ", "CSI300", "000001.SS", "399001.SZ"}

TRADER_PERMISSIONS: dict[str, set[str]] = {
    "yi_ling": {ac.value for ac in AssetClass},
    "lawrence": {ac.value for ac in AssetClass},
    "pm_macro": {ac.value for ac in AssetClass},
    "trader_fx": {AssetClass.FX.value},
    "trader_eq": {AssetClass.EQUITY.value},
}


@dataclass
class RiskCheckResult:
    passed: bool
    check_name: str
    message: str


def check_order(
    symbol: str,
    asset_class: str,
    order_type: str,
    quantity: Decimal,
    limit_price: Decimal | None,
    trader: str,
    positions: dict[str, Position],
) -> list[RiskCheckResult]:
    results = []
    results.append(_check_restricted_symbol(symbol))
    results.append(_check_order_size(quantity, asset_class))
    results.append(_check_notional(symbol, quantity, limit_price, order_type))
    results.append(_check_position_limit(symbol, quantity, positions))
    results.append(_check_trader_permission(trader, asset_class))
    if order_type == OrderType.LIMIT.value and limit_price is not None:
        results.append(_check_limit_price_sanity(symbol, limit_price))
    return results


def _check_restricted_symbol(symbol: str) -> RiskCheckResult:
    if symbol in RESTRICTED_SYMBOLS:
        return RiskCheckResult(False, "RESTRICTED_SYMBOL", f"{symbol} is restricted (China domestic equity)")
    return RiskCheckResult(True, "RESTRICTED_SYMBOL", "passed")


def _check_order_size(quantity: Decimal, asset_class: str) -> RiskCheckResult:
    limit = MAX_ORDER_QUANTITY.get(asset_class, Decimal("100000"))
    if quantity > limit:
        return RiskCheckResult(False, "ORDER_SIZE", f"Quantity {quantity} exceeds {asset_class} limit of {limit}")
    return RiskCheckResult(True, "ORDER_SIZE", "passed")


def _check_notional(symbol: str, quantity: Decimal, limit_price: Decimal | None, order_type: str) -> RiskCheckResult:
    ref = REFERENCE_PRICES.get(symbol)
    if ref is None:
        return RiskCheckResult(True, "NOTIONAL", "no reference price, skipped")
    price = limit_price if (order_type == OrderType.LIMIT.value and limit_price) else ref
    notional = quantity * price
    if notional > MAX_NOTIONAL:
        return RiskCheckResult(False, "NOTIONAL", f"Notional ${notional:,.2f} exceeds limit ${MAX_NOTIONAL:,.2f}")
    return RiskCheckResult(True, "NOTIONAL", "passed")


def _check_position_limit(symbol: str, quantity: Decimal, positions: dict[str, Position]) -> RiskCheckResult:
    current_qty = Decimal("0")
    if symbol in positions:
        current_qty = positions[symbol].quantity
    projected = abs(current_qty + quantity)
    if projected > MAX_POSITION_PER_SYMBOL:
        return RiskCheckResult(
            False, "POSITION_LIMIT",
            f"Projected position {projected} exceeds limit {MAX_POSITION_PER_SYMBOL}",
        )
    return RiskCheckResult(True, "POSITION_LIMIT", "passed")


def _check_trader_permission(trader: str, asset_class: str) -> RiskCheckResult:
    perms = TRADER_PERMISSIONS.get(trader)
    if perms is None:
        return RiskCheckResult(False, "TRADER_PERMISSION", f"Unknown trader: {trader}")
    if asset_class not in perms:
        return RiskCheckResult(False, "TRADER_PERMISSION", f"Trader {trader} not authorized for {asset_class}")
    return RiskCheckResult(True, "TRADER_PERMISSION", "passed")


def _check_limit_price_sanity(symbol: str, limit_price: Decimal) -> RiskCheckResult:
    ref = REFERENCE_PRICES.get(symbol)
    if ref is None:
        return RiskCheckResult(True, "PRICE_SANITY", "no reference price, skipped")
    deviation = abs(limit_price - ref) / ref
    if deviation > Decimal("0.10"):
        return RiskCheckResult(
            False, "PRICE_SANITY",
            f"Limit price {limit_price} deviates {deviation:.1%} from reference {ref} (max 10%)",
        )
    return RiskCheckResult(True, "PRICE_SANITY", "passed")
