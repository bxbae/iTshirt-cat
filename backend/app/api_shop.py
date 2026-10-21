"""Customer-facing API: catalog, cart, orders and receipts, reviews, claims, inquiries."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import claims as claim_svc
from . import clock, cs, shop
from .config import settings
from .copilot.llm.base import LLMError
from .db import get_db
from .deps import current_user
from .models import Claim, Conversation, Order, Product, Review, User
from .rules import abuse
from .rules.policy import REASONS, TYPES
from .rules.refund import decide, late_days, remaining_qty

router = APIRouter(prefix="/api")

CATEGORY_KO = {"book": "국내도서", "foreign_book": "외국도서", "ebook": "전자책", "stationery": "문구", "goods": "굿즈"}


# ---------------------------------------------------------------- schemas
class CartLine(BaseModel):
    product_id: int
    qty: int = Field(ge=1, le=20)


class OrderIn(BaseModel):
    lines: list[CartLine]
    points_used: int = Field(default=0, ge=0)
    payment_method: Literal["card", "transfer", "easy_pay"] = "card"
    receiver: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=300)


class ClaimLineIn(BaseModel):
    order_item_id: int
    qty: int = Field(ge=1, le=20)


class ClaimIn(BaseModel):
    order_id: int
    type: Literal["cancel", "return", "exchange", "compensation"]
    reason: Literal["change_of_mind", "defect", "wrong_item", "damaged", "late_delivery", "missing_item", "other"]
    items: list[ClaimLineIn] | None = None
    claimed_amount: int | None = Field(default=None, ge=0)
    unsealed: bool = False
    evidence_count: int = Field(default=0, ge=0, le=10)
    description: str = Field(default="", max_length=2000)


class EvidenceIn(BaseModel):
    count: int = Field(default=1, ge=1, le=10)


class ReviewIn(BaseModel):
    order_item_id: int
    rating: int = Field(ge=1, le=5)
    title: str = Field(default="", max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class InquiryIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    order_id: int | None = None


class FollowUp(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class AdvanceIn(BaseModel):
    late_days: float = Field(default=0, ge=0, le=30)


# ---------------------------------------------------------------- serializers
def product_out(db: Session, p: Product, with_rating: bool = True) -> dict:
    rating, n = shop.product_rating(db, p.id) if with_rating else (None, 0)
    return {
        "id": p.id, "category": p.category, "category_ko": CATEGORY_KO[p.category], "title": p.title, "author": p.author,
        "publisher": p.publisher, "description": p.description, "list_price": p.list_price, "sale_price": p.sale_price,
        "discount_pct": round(p.discount_rate * 100), "stock": p.stock, "sold_out": p.stock <= 0, "returnable": p.returnable,
        "custom_made": p.custom_made, "hue": p.hue, "sales": p.sales, "rating": rating, "review_count": n,
        "published_at": p.published_at.isoformat(),
    }


def review_out(r: Review, *, internal: bool = False) -> dict:
    out = {"id": r.id, "product_id": r.product_id, "user": r.user.name[0] + "*" * (len(r.user.name) - 1), "rating": r.rating,
           "title": r.title, "body": r.body, "helpful": r.helpful, "verified": r.order_item_id is not None,
           "created_at": r.created_at.isoformat(), "status": r.status}
    if internal:
        out.update({"user": r.user.name, "product": r.product.title, "flags": r.flags})
    return out


def order_out(db: Session, o: Order, *, full: bool = True) -> dict:
    reviewed = {rid for (rid,) in db.execute(select(Review.order_item_id).where(Review.order_item_id.in_([i.id for i in o.items])))}
    others = list(db.scalars(select(Claim).where(Claim.order_id == o.id)).all())
    out = {
        "id": o.id, "order_no": o.order_no, "status": o.status, "status_ko": cs.ORDER_STATUS_KO[o.status],
        "items_total": o.items_total, "shipping_fee": o.shipping_fee, "points_used": o.points_used, "paid_amount": o.paid_amount,
        "refunded_amount": o.refunded_amount, "payment_method": o.payment_method, "receiver": o.receiver, "address": o.address,
        "paid_at": o.paid_at.isoformat(), "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "expected_delivery_at": o.expected_delivery_at.isoformat() if o.expected_delivery_at else None,
        "late_days": round(max(0.0, late_days(o, clock.now())), 1) if o.status != "cancelled" else 0,
        "items": [{
            "id": i.id, "product_id": i.product_id, "title": i.title, "category": i.category, "unit_price": i.unit_price,
            "qty": i.qty, "paid_amount": i.paid_amount, "points_share": i.points_share, "returnable": i.returnable,
            "refunded_qty": i.refunded_qty, "remaining_qty": max(0, remaining_qty(i, others)),
            "reviewed": i.id in reviewed, "can_review": o.status == "delivered" and i.id not in reviewed and i.refunded_qty < i.qty,
            "hue": i.product.hue,
        } for i in o.items],
    }
    if full:
        out["claims"] = [cs.claim_summary(c) for c in sorted(others, key=lambda c: -c.id)]
    return out


def _owned(db: Session, user: User, model, id_: int):
    row = db.get(model, id_)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "찾을 수 없습니다.")
    return row


# ---------------------------------------------------------------- users
@router.get("/users")
def users(db: Session = Depends(get_db)):
    """Demo sign-in list."""
    return [{"id": u.id, "name": u.name, "email": u.email, "points": u.points}
            for u in db.scalars(select(User).order_by(User.id)).all()][:5]


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "points": user.points}


# ---------------------------------------------------------------- catalog
@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Product.category, func.count()).group_by(Product.category)).all())
    return [{"key": k, "label": v, "count": counts.get(k, 0)} for k, v in CATEGORY_KO.items()]


@router.get("/products")
def products(category: str | None = None, q: str | None = None, sort: Literal["popular", "new", "price_asc", "price_desc"] = "popular",
             limit: int = 60, db: Session = Depends(get_db)):
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Product.title.like(like) | Product.author.like(like) | Product.publisher.like(like))
    rows = db.scalars(stmt).all()
    key = {"popular": lambda p: -p.sales, "new": lambda p: -p.published_at.timestamp(),
           "price_asc": lambda p: p.sale_price, "price_desc": lambda p: -p.sale_price}[sort]
    return [product_out(db, p) for p in sorted(rows, key=key)[: max(1, min(limit, 100))]]


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "상품을 찾을 수 없습니다.")
    related = db.scalars(select(Product).where(Product.category == p.category, Product.id != p.id).limit(4)).all()
    reviews = db.scalars(select(Review).where(Review.product_id == p.id, Review.status == "visible").order_by(Review.helpful.desc(), Review.id.desc())).all()
    dist = {s: sum(1 for r in reviews if r.rating == s) for s in range(5, 0, -1)}
    return {**product_out(db, p), "related": [product_out(db, r) for r in related],
            "reviews": [review_out(r) for r in reviews], "rating_distribution": dist}


@router.post("/reviews/{review_id}/helpful")
def helpful(review_id: int, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if r is None or r.status != "visible":
        raise HTTPException(404, "후기를 찾을 수 없습니다.")
    r.helpful += 1
    db.commit()
    return {"helpful": r.helpful}


@router.post("/reviews", status_code=201)
def write_review(body: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        r = shop.create_review(db, user, **body.model_dump())
    except shop.ShopError as exc:
        raise HTTPException(422, str(exc)) from exc
    held = r.status == "flagged"
    return {**review_out(r), "held": held,
            "message": "후기가 등록되었습니다." if not held else "후기가 접수되었고, 운영 정책 확인 후 공개됩니다."}


# ---------------------------------------------------------------- cart and orders
@router.post("/cart/price")
def cart_price(lines: list[CartLine], db: Session = Depends(get_db)):
    try:
        priced = shop.price_cart(db, [ln.model_dump() for ln in lines])
    except shop.ShopError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"items_total": priced["items_total"], "shipping_fee": priced["shipping_fee"],
            "total": priced["items_total"] + priced["shipping_fee"],
            "free_shipping_gap": max(0, 15000 - priced["items_total"]) if priced["shipping_fee"] else 0}


@router.post("/orders", status_code=201)
def place_order(body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        order = shop.create_order(db, user, [ln.model_dump() for ln in body.lines], points_used=body.points_used,
                                  payment_method=body.payment_method, receiver=body.receiver, address=body.address)
    except shop.ShopError as exc:
        raise HTTPException(422, str(exc)) from exc
    return order_out(db, order)


@router.get("/orders")
def my_orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Order).where(Order.user_id == user.id).options(selectinload(Order.items)).order_by(Order.id.desc())).all()
    return [order_out(db, o, full=False) | {"open_claims": db.scalar(select(func.count(Claim.id)).where(
        Claim.order_id == o.id, Claim.status.in_(["needs_info", "needs_review", "awaiting_return", "return_received"])))} for o in rows]


@router.get("/orders/{order_id}")
def order_detail(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return order_out(db, _owned(db, user, Order, order_id))


@router.post("/orders/{order_id}/advance")
def advance(order_id: int, body: AdvanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo helper that stands in for the logistics system."""
    if not settings.demo_tools:
        raise HTTPException(404, "사용할 수 없습니다.")
    try:
        return order_out(db, shop.advance_order(db, _owned(db, user, Order, order_id), late_days=body.late_days))
    except shop.ShopError as exc:
        raise HTTPException(422, str(exc)) from exc


# ---------------------------------------------------------------- claims
@router.post("/claims/preview")
def preview_claim(body: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Refund simulator: run the same rules on the form without saving anything."""
    order = _owned(db, user, Order, body.order_id)
    draft = Claim(id=0, user_id=user.id, order_id=order.id, type=body.type, reason=body.reason,
                  items=[i.model_dump() for i in body.items] if body.items else [], claimed_amount=body.claimed_amount,
                  unsealed=body.unsealed, evidence_count=body.evidence_count, description=body.description, status="needs_review",
                  decision={}, created_at=clock.now())
    others = list(db.scalars(select(Claim).where(Claim.order_id == order.id)).all())
    history = abuse.history_signals(db, user.id)
    d = decide(order, draft, others=others, history=history, now=clock.now(),
               stock={i.id: i.product.stock for i in order.items})
    return cs.public_decision(d)


@router.post("/claims", status_code=201)
def submit_claim(body: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _owned(db, user, Order, body.order_id)
    try:
        c = claim_svc.create_claim(db, user, order_id=body.order_id, type=body.type, reason=body.reason,
                                   items=[i.model_dump() for i in body.items] if body.items else None,
                                   claimed_amount=body.claimed_amount, unsealed=body.unsealed,
                                   evidence_count=body.evidence_count, description=body.description)
    except claim_svc.ClaimError as exc:
        raise HTTPException(422, str(exc)) from exc
    return cs.claim_summary(c)


@router.get("/claims")
def my_claims(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Claim).where(Claim.user_id == user.id).order_by(Claim.id.desc())).all()
    return [cs.claim_summary(c) | {"order_no": c.order.order_no} for c in rows]


@router.get("/claims/{claim_id}")
def my_claim(claim_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _owned(db, user, Claim, claim_id)
    return cs.claim_summary(c) | {"order_no": c.order.order_no}


@router.post("/claims/{claim_id}/evidence")
def claim_evidence(claim_id: int, body: EvidenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _owned(db, user, Claim, claim_id)
    try:
        return cs.claim_summary(claim_svc.add_evidence(db, c, body.count))
    except claim_svc.ClaimError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/claims/{claim_id}/withdraw")
def claim_withdraw(claim_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _owned(db, user, Claim, claim_id)
    try:
        return cs.claim_summary(claim_svc.withdraw(db, c))
    except claim_svc.ClaimError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/claim-options")
def claim_options():
    return {"types": TYPES, "reasons": REASONS}


# ---------------------------------------------------------------- inquiries (customer side)
def _inquiry_out(c: Conversation, *, full: bool = False) -> dict:
    out = {"id": c.id, "subject": c.subject, "status": c.status, "order_id": c.order_id, "updated_at": c.updated_at.isoformat(),
           "answered": bool(c.messages) and c.messages[-1].role == "agent",
           "preview": (c.messages[-1].text if c.messages else "")[:80]}
    if full:
        out["messages"] = [{"id": m.id, "role": m.role, "text": m.text, "created_at": m.created_at.isoformat()} for m in c.messages]
    return out


@router.get("/inquiries")
def my_inquiries(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id).options(selectinload(Conversation.messages))
                      .order_by(Conversation.updated_at.desc())).all()
    return [_inquiry_out(c) for c in rows]


@router.post("/inquiries", status_code=201)
def new_inquiry(body: InquiryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        conv = cs.create_inquiry(db, user, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(502, f"문의 분석 중 오류가 발생했습니다: {exc}") from exc
    return _inquiry_out(conv, full=True)


@router.get("/inquiries/{inquiry_id}")
def inquiry_detail(inquiry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _inquiry_out(_owned(db, user, Conversation, inquiry_id), full=True)


@router.post("/inquiries/{inquiry_id}/messages", status_code=201)
def inquiry_follow_up(inquiry_id: int, body: FollowUp, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = _owned(db, user, Conversation, inquiry_id)
    try:
        cs.handle_customer_message(db, conv, body.text)
    except LLMError as exc:
        raise HTTPException(502, f"문의 분석 중 오류가 발생했습니다: {exc}") from exc
    db.refresh(conv)
    return _inquiry_out(conv, full=True)
