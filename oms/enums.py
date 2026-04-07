from enum import Enum


class OrderStatus(str, Enum):
    PENDING_NEW = "PENDING_NEW"
    NEW = "NEW"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    FX = "FX"
    COMMODITY = "COMMODITY"
    FIXED_INCOME = "FIXED_INCOME"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
