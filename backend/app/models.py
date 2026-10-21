from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import clock
from .db import Base, UTCDateTime


def now() -> datetime:
    return clock.now()


# ---------------------------------------------------------------- shop
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(20))  # book | foreign_book | ebook | stationery | goods
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(120), default="")
    publisher: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    list_price: Mapped[int] = mapped_column(Integer)
    discount_rate: Mapped[float] = mapped_column(Float, default=0.0)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    returnable: Mapped[bool] = mapped_column(Boolean, default=True)  # False: ebook, made-to-order
    custom_made: Mapped[bool] = mapped_column(Boolean, default=False)
    hue: Mapped[int] = mapped_column(Integer, default=200)  # drives the generated cover
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)

    @property
    def sale_price(self) -> int:
        # Round down to the 10 won unit, as Korean book stores do.
        return int(self.list_price * (1 - self.discount_rate)) // 10 * 10


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(20), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # paid -> preparing -> shipped -> delivered, or cancelled before shipping
    status: Mapped[str] = mapped_column(String(15), default="paid")
    items_total: Mapped[int] = mapped_column(Integer)
    shipping_fee: Mapped[int] = mapped_column(Integer, default=0)
    points_used: Mapped[int] = mapped_column(Integer, default=0)
    paid_amount: Mapped[int] = mapped_column(Integer)  # cash: items + shipping - points
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str] = mapped_column(String(20), default="card")
    receiver: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    paid_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    shipped_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expected_delivery_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", order_by="OrderItem.id", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    title: Mapped[str] = mapped_column(String(200))  # receipt snapshot
    category: Mapped[str] = mapped_column(String(20))
    unit_price: Mapped[int] = mapped_column(Integer)  # sale price at purchase time
    qty: Mapped[int] = mapped_column(Integer)
    paid_amount: Mapped[int] = mapped_column(Integer)  # cash share of this line (points allocated out)
    points_share: Mapped[int] = mapped_column(Integer, default=0)
    returnable: Mapped[bool] = mapped_column(Boolean, default=True)
    refunded_qty: Mapped[int] = mapped_column(Integer, default=0)
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

    @property
    def line_total(self) -> int:
        return self.unit_price * self.qty


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    order_item_id: Mapped[int | None] = mapped_column(ForeignKey("order_items.id"), nullable=True, unique=True)
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="visible")  # visible | flagged | hidden
    flags: Mapped[list] = mapped_column(JSON, default=list)
    helpful: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)

    user: Mapped[User] = relationship()
    product: Mapped[Product] = relationship()


class PointLedger(Base):
    __tablename__ = "point_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claim_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


# ---------------------------------------------------------------- claims
class Claim(Base):
    """A cancel / return / exchange / compensation request, judged against the receipt and policy."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(15))  # cancel | return | exchange | compensation
    reason: Mapped[str] = mapped_column(String(20))
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{order_item_id, qty}] as requested
    claimed_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unsealed: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")

    # needs_info | needs_review | awaiting_return | return_received | completed | rejected | withdrawn
    status: Mapped[str] = mapped_column(String(20), default="needs_review")
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_by: Mapped[str] = mapped_column(String(40), default="system")  # system | agent name
    manager_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    return_tracking: Mapped[str | None] = mapped_column(String(30), nullable=True)
    return_received_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    inspection: Mapped[str | None] = mapped_column(String(10), nullable=True)  # pending | ok | mismatch
    inspection_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    refund_amount: Mapped[int] = mapped_column(Integer, default=0)
    points_returned: Mapped[int] = mapped_column(Integer, default=0)
    compensation_amount: Mapped[int] = mapped_column(Integer, default=0)
    hold_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship()
    order: Mapped[Order] = relationship()


class AuditLog(Base):
    """Every automatic or manual step on a claim, so each decision can be explained later."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))
    actor: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


# ---------------------------------------------------------------- customer service
class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved | escalated
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now, onupdate=now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.id", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(10))  # "customer" | "agent"
    text: Mapped[str] = mapped_column(Text)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # classification, drafts, sources, timings
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class FeedbackEvent(Base):
    """How the agent used a suggestion: accepted as-is, edited, or rejected."""

    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_style: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str] = mapped_column(String(10))  # accepted | edited | rejected | manual
    edit_ratio: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
