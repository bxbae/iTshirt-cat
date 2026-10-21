"""Storefront logic: price an order, take stock, move it through shipping, screen reviews."""
import re
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import clock
from .copilot.pii import find_pii
from .models import Order, OrderItem, PointLedger, Product, Review, User
from .rules.policy import FREE_SHIPPING_MIN, SHIPPING_FEE


class ShopError(ValueError):
    pass


def price_cart(db: Session, lines: list[dict]) -> dict:
    """Totals for [{product_id, qty}] without touching stock."""
    items, total = [], 0
    for ln in lines:
        p = db.get(Product, ln["product_id"])
        if p is None:
            raise ShopError("존재하지 않는 상품이 장바구니에 있습니다.")
        qty = int(ln["qty"])
        if qty < 1 or qty > 20:
            raise ShopError("수량은 1~20권 사이여야 합니다.")
        items.append((p, qty))
        total += p.sale_price * qty
    shipping = 0 if total >= FREE_SHIPPING_MIN or total == 0 or all(p.category == "ebook" for p, _ in items) else SHIPPING_FEE
    return {"items": items, "items_total": total, "shipping_fee": shipping}


def create_order(db: Session, user: User, lines: list[dict], *, points_used: int, payment_method: str,
                 receiver: str, address: str) -> Order:
    if not lines:
        raise ShopError("장바구니가 비어 있습니다.")
    priced = price_cart(db, lines)
    for p, qty in priced["items"]:
        if p.stock < qty:
            raise ShopError(f"'{p.title}' 재고가 부족합니다. (남은 수량 {p.stock})")
    gross = priced["items_total"] + priced["shipping_fee"]
    if points_used < 0 or points_used > user.points or points_used > gross:
        raise ShopError("사용할 적립금이 보유 적립금 또는 결제 금액을 넘습니다.")

    now = clock.now()
    only_ebook = all(p.category == "ebook" for p, _ in priced["items"])
    order = Order(
        order_no=f"pending-{uuid.uuid4().hex[:12]}",  # replaced by the id-based number right after the insert
        user_id=user.id, status="delivered" if only_ebook else "paid",
        items_total=priced["items_total"], shipping_fee=priced["shipping_fee"], points_used=points_used,
        paid_amount=gross - points_used, payment_method=payment_method, receiver=receiver, address=address,
        paid_at=now, expected_delivery_at=None if only_ebook else now + timedelta(days=2),
    )
    if only_ebook:
        order.delivered_at = now
    db.add(order)
    # Spread the points over the lines in proportion to price; the last line takes the rounding remainder.
    left_points = points_used
    for n, (p, qty) in enumerate(priced["items"]):
        line_total = p.sale_price * qty
        share = left_points if n == len(priced["items"]) - 1 else round(points_used * line_total / max(priced["items_total"], 1))
        share = min(share, line_total, left_points)
        left_points -= share
        order.items.append(OrderItem(product_id=p.id, title=p.title, category=p.category, unit_price=p.sale_price, qty=qty,
                                     paid_amount=line_total - share, points_share=share, returnable=p.returnable))
        p.stock -= qty
        p.sales += qty
    # Shipping is cash only: lines carry item money, so cash paid = sum(line cash) + shipping.
    db.flush()
    order.order_no = f"{now:%Y%m%d}-{order.id:04d}"  # the row id is unique, so two checkouts can never share a number
    if points_used:
        user.points -= points_used
        db.add(PointLedger(user_id=user.id, delta=-points_used, reason=f"주문 {order.order_no} 적립금 사용", order_id=order.id))
    db.commit()
    return order


NEXT_STATE = {"paid": "preparing", "preparing": "shipped", "shipped": "delivered"}


def advance_order(db: Session, order: Order, *, late_days: float = 0) -> Order:
    """Demo helper standing in for the logistics system. `late_days` makes the delivery arrive late."""
    nxt = NEXT_STATE.get(order.status)
    if not nxt:
        raise ShopError("더 진행할 수 없는 주문 상태입니다.")
    now = clock.now()
    order.status = nxt
    if nxt == "shipped":
        order.shipped_at = now
    if nxt == "delivered":
        order.delivered_at = now
        if late_days:  # demo: pretend the estimate was `late_days` days before the actual arrival
            order.expected_delivery_at = now - timedelta(days=late_days)
    db.commit()
    return order


# ---------------------------------------------------------------- reviews
CONTACT = re.compile(r"(카톡|카카오톡|오픈채팅|텔레그램|open\.kakao|t\.me/)", re.I)
URL = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(?:com|net|kr|io|me)\b)", re.I)
PROFANITY = re.compile(r"(씨발|시발|병신|좆|개새끼|지랄|ㅅㅂ|ㅂㅅ)")
REPEAT = re.compile(r"(.)\1{7,}")
PROMO = re.compile(r"(할인\s*코드|무료\s*증정|수익\s*보장|대출|도박|토토)")
DEFECT_WORDS = re.compile(r"(불량|파손|찢어|찢겨|오염|훼손|누락|잘못\s*왔|다른\s*(?:책|상품)|배송.{0,6}(?:늦|지연)|환불)")


def screen_review(title: str, body: str) -> list[dict]:
    text = f"{title}\n{body}"
    flags: list[dict] = []
    if find_pii(text):
        flags.append({"code": "PERSONAL_INFO", "message": "연락처·이메일 등 개인정보가 포함되어 있습니다."})
    if URL.search(text) or CONTACT.search(text):
        flags.append({"code": "LINK_OR_CONTACT", "message": "외부 링크 또는 연락 유도 문구가 포함되어 있습니다."})
    if PROFANITY.search(text):
        flags.append({"code": "PROFANITY", "message": "비속어가 포함되어 있습니다."})
    if PROMO.search(text):
        flags.append({"code": "PROMOTION", "message": "광고·홍보성 문구가 포함되어 있습니다."})
    if REPEAT.search(text):
        flags.append({"code": "REPEATED_CHARS", "message": "같은 글자가 과도하게 반복됩니다."})
    return flags


def create_review(db: Session, user: User, *, order_item_id: int, rating: int, title: str, body: str) -> Review:
    item = db.get(OrderItem, order_item_id)
    if item is None or item.order.user_id != user.id:
        raise ShopError("구매한 상품에만 후기를 쓸 수 있습니다.")
    if item.order.status != "delivered":
        raise ShopError("상품을 받은 뒤에 후기를 쓸 수 있습니다.")
    if item.refunded_qty >= item.qty:
        raise ShopError("환불이 완료된 상품에는 후기를 쓸 수 없습니다.")
    if db.scalar(select(Review.id).where(Review.order_item_id == order_item_id)):
        raise ShopError("이미 후기를 작성한 상품입니다.")
    if not 1 <= rating <= 5:
        raise ShopError("별점은 1~5점입니다.")
    if len(body.strip()) < 10:
        raise ShopError("후기는 10자 이상 작성해 주세요.")
    flags = screen_review(title, body)
    if rating <= 2 and DEFECT_WORDS.search(f"{title} {body}"):
        flags.append({"code": "CS_FOLLOW_UP", "message": "낮은 별점과 불량·배송 문제 언급 — 고객센터 선제 연락 대상입니다.", "info": True})
    blocking = [f for f in flags if not f.get("info")]
    review = Review(product_id=item.product_id, user_id=user.id, order_item_id=order_item_id, rating=rating,
                    title=title.strip(), body=body.strip(), flags=flags, status="flagged" if blocking else "visible")
    db.add(review)
    db.commit()
    return review


def product_rating(db: Session, product_id: int) -> tuple[float | None, int]:
    avg, n = db.execute(select(func.avg(Review.rating), func.count(Review.id))
                        .where(Review.product_id == product_id, Review.status == "visible")).one()
    return (round(float(avg), 1) if avg is not None else None), n
