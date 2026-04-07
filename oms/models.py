import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oms.database import Base
from oms.enums import AssetClass, OrderSide, OrderStatus, OrderType, TimeInForce


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    asset_class: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    time_in_force: Mapped[str] = mapped_column(String(4), default=TimeInForce.DAY.value)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING_NEW.value, index=True)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    average_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    trader: Mapped[str] = mapped_column(String(64))
    strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    venue: Mapped[str] = mapped_column(String(32), default="SIMULATOR")
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    fills: Mapped[list["Fill"]] = relationship(back_populates="order", lazy="selectin")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", lazy="selectin", order_by="OrderEvent.timestamp")

    __table_args__ = (
        Index("ix_orders_trader_status", "trader", "status"),
    )


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), index=True)
    exec_id: Mapped[str] = mapped_column(String(64), unique=True)
    fill_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    venue: Mapped[str] = mapped_column(String(32), default="SIMULATOR")
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    order: Mapped["Order"] = relationship(back_populates="fills")


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    order: Mapped["Order"] = relationship(back_populates="events")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    asset_class: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    average_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
