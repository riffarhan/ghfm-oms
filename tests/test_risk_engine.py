from decimal import Decimal

from oms.enums import AssetClass, OrderType
from oms.risk_engine import check_order


def _run_checks(**kwargs):
    defaults = dict(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY.value,
        order_type=OrderType.MARKET.value,
        quantity=Decimal("1000"),
        limit_price=None,
        trader="pm_macro",
        positions={},
    )
    defaults.update(kwargs)
    return check_order(**defaults)


def test_valid_order_passes_all():
    results = _run_checks()
    assert all(r.passed for r in results)


def test_restricted_symbol_rejected():
    results = _run_checks(symbol="600519.SS")
    failed = [r for r in results if not r.passed]
    assert any(r.check_name == "RESTRICTED_SYMBOL" for r in failed)


def test_unauthorized_trader_rejected():
    results = _run_checks(
        symbol="USDJPY",
        asset_class=AssetClass.FX.value,
        trader="trader_eq",
    )
    failed = [r for r in results if not r.passed]
    assert any(r.check_name == "TRADER_PERMISSION" for r in failed)


def test_excessive_notional_rejected():
    results = _run_checks(symbol="NVDA", quantity=Decimal("500000"))
    failed = [r for r in results if not r.passed]
    assert any(r.check_name == "NOTIONAL" for r in failed)


def test_excessive_order_size_rejected():
    results = _run_checks(quantity=Decimal("999999"))
    failed = [r for r in results if not r.passed]
    assert any(r.check_name == "ORDER_SIZE" for r in failed)


def test_limit_price_sanity_rejected():
    results = _run_checks(
        order_type=OrderType.LIMIT.value,
        limit_price=Decimal("50.00"),  # 73% below ref of 185.50
    )
    failed = [r for r in results if not r.passed]
    assert any(r.check_name == "PRICE_SANITY" for r in failed)


def test_unknown_trader_rejected():
    results = _run_checks(trader="unknown_person")
    failed = [r for r in results if not r.passed]
    assert any(r.check_name == "TRADER_PERMISSION" for r in failed)
