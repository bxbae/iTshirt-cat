import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Isolated SQLite DB and offline provider for every test run (set before the app is imported).
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["SEED_DEMO"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import itertools

import pytest

from app import clock
from app.db import Base, SessionLocal, engine
from app.models import Order, OrderItem, Product, User

_order_seq = itertools.count(1)
NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clock.freeze(NOW)
    yield
    clock.freeze(None)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_user(db, name="김민지", points=0, email=None):
    u = User(name=name, email=email or f"{name}@example.com", points=points)
    db.add(u)
    db.flush()
    return u


def make_product(db, title="테스트 책", price=20_000, category="book", stock=10, returnable=True, discount=0.1):
    p = Product(title=title, category=category, list_price=price, discount_rate=discount, stock=stock,
                returnable=returnable, author="저자", publisher="출판사")
    db.add(p)
    db.flush()
    return p


def make_order(db, user, lines, *, status="delivered", delivered_days_ago=2, shipping=0, points_used=0,
               expected_days_after_paid=2, delivered_late_days=0):
    """lines: [(product, qty)]. Builds a receipt the same way checkout does."""
    items_total = sum(p.sale_price * q for p, q in lines)
    paid_at = NOW - timedelta(days=delivered_days_ago + 3)
    order = Order(order_no=f"T{next(_order_seq):05d}", user_id=user.id, status=status,
                  items_total=items_total, shipping_fee=shipping, points_used=points_used,
                  paid_amount=items_total + shipping - points_used, paid_at=paid_at,
                  expected_delivery_at=paid_at + timedelta(days=expected_days_after_paid))
    if status in ("shipped", "delivered"):
        order.shipped_at = paid_at + timedelta(days=1)
    if status == "delivered":
        order.delivered_at = NOW - timedelta(days=delivered_days_ago)
    db.add(order)
    left = points_used
    for n, (p, q) in enumerate(lines):
        total = p.sale_price * q
        share = left if n == len(lines) - 1 else round(points_used * total / items_total)
        share = min(share, total, left)
        left -= share
        order.items.append(OrderItem(product_id=p.id, title=p.title, category=p.category, unit_price=p.sale_price,
                                     qty=q, paid_amount=total - share, points_share=share, returnable=p.returnable))
    db.flush()
    return order
