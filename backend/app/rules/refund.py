"""Judge a claim against the receipt (order data) and store policy.

`decide` is a pure function of its inputs plus the current time: same claim, same order, same
history, same answer. It never writes to the database; app/claims.py applies the outcome.

Outcomes
  auto_rejected            clear policy or receipt violation; the reasons say which rule
  needs_info               valid so far, but something is missing (e.g. a photo of the defect)
  needs_review             something is off or too big for automation; an agent decides
  approved_pending_return  approved; money is paid after the returned goods are received and inspected
  auto_approved            approved and payable now (cancel before shipping, late-delivery compensation)
"""
from datetime import datetime

from ..models import Claim, Order, OrderItem
from . import abuse
from .policy import (
    ABUSE_REVIEW_SCORE, AUTO_LIMIT, DEFECT_COMPENSATION, DEFECT_WINDOW_DAYS, FREE_SHIPPING_MIN, LATE_GRACE_DAYS,
    LATE_TIERS, MIND_WINDOW_DAYS, RETURN_FEE, RULE_REFS, SELLER_FAULT, SHIPPING_FEE,
)

ACTIVE = {"needs_info", "needs_review", "awaiting_return", "return_received"}
CATEGORY_KO = {"book": "도서", "foreign_book": "외국도서", "ebook": "전자책", "stationery": "문구", "goods": "굿즈"}


def remaining_qty(item: OrderItem, others: list[Claim]) -> int:
    reserved = sum(
        line["qty"] for c in others if c.status in ACTIVE
        for line in c.decision.get("lines", []) if line["order_item_id"] == item.id
    )
    return item.qty - item.refunded_qty - reserved


def _line_refund(item: OrderItem, qty: int) -> tuple[int, int]:
    """(cash, points) given back for `qty` units of this line. The last unit takes the rounding remainder."""
    left_qty = item.qty - item.refunded_qty
    if qty >= left_qty:
        paid_left = item.paid_amount - item.refunded_amount
        points_left = item.points_share - round(item.points_share * item.refunded_qty / item.qty)
        return max(0, paid_left), max(0, points_left)
    return round(item.paid_amount * qty / item.qty), round(item.points_share * qty / item.qty)


def late_days(order: Order, now: datetime) -> float:
    if not order.expected_delivery_at:
        return 0.0
    end = order.delivered_at or now
    return (end - order.expected_delivery_at).total_seconds() / 86400


def decide(order: Order, claim: Claim, *, others: list[Claim], history: list[dict], now: datetime,
           stock: dict[int, int] | None = None) -> dict:
    reasons: list[dict] = []
    signals: list[dict] = list(history)

    def add(code: str, level: str, message: str):
        reasons.append({"code": code, "level": level, "message": message, "rule": RULE_REFS.get(code)})

    seller_fault = claim.reason in SELLER_FAULT
    by_id = {i.id: i for i in order.items}
    ctype, reason = claim.type, claim.reason

    # 0) A return or exchange needs a reason about the goods; delay / not-received go through compensation.
    #    Without this, "return + late_delivery" would skip the change-of-mind window and unsealed checks.
    if ctype in ("return", "exchange") and reason in ("late_delivery", "missing_item"):
        add("INVALID_REASON", "block", "배송 지연·미수령은 반품·교환이 아니라 '보상' 신청으로 접수해 주세요.")

    # 1) Whose order is it, and is this kind of claim possible at this stage?
    if claim.user_id != order.user_id:
        add("OWNER_MISMATCH", "block", "주문자와 신청자가 일치하지 않아 처리할 수 없습니다.")
    if order.status == "cancelled" and ctype != "compensation":
        add("ALREADY_CANCELLED", "block", "이미 취소된 주문입니다.")
    elif ctype == "cancel" and order.status in ("shipped", "delivered"):
        add("CANCEL_TOO_LATE", "block", "이미 출고된 주문은 취소할 수 없습니다. 상품을 받은 뒤 반품으로 신청해 주세요.")
    elif ctype in ("return", "exchange") and order.status in ("paid", "preparing"):
        add("CANCEL_INSTEAD", "block", "아직 출고 전인 주문입니다. 반품이 아니라 주문 취소로 신청해 주세요.")
    elif ctype in ("return", "exchange") and order.status == "shipped":
        add("NOT_DELIVERED_YET", "block", "배송이 완료된 뒤에 반품·교환을 신청할 수 있습니다.")
    elif ctype == "compensation" and reason == "missing_item" and order.status != "delivered":
        add("NOT_DELIVERED_YET", "block", "배송 완료 상태가 아닌 주문은 '받지 못함' 보상을 신청할 수 없습니다.")

    # 2) Which lines, how many? Compare with what the receipt says is still open.
    lines: list[dict] = []
    requested = claim.items or [{"order_item_id": i.id, "qty": i.qty} for i in order.items]
    for req in requested:
        item = by_id.get(req["order_item_id"])
        if item is None:
            add("ITEM_NOT_IN_ORDER", "block", "영수증에 없는 상품이 포함되어 있습니다.")
            signals.append({"code": "ITEM_MISMATCH", "points": 30, "message": "주문에 없는 상품으로 신청"})
            continue
        if ctype == "compensation":
            continue
        left = remaining_qty(item, others)
        want = max(1, int(req["qty"]))
        if left <= 0:
            add("ALREADY_CLAIMED", "block", f"'{item.title}'은(는) 이미 환불됐거나 처리 중인 신청이 있습니다.")
            continue
        qty = min(want, left)
        if qty < want:
            add("QTY_ADJUSTED", "warn", f"'{item.title}' 신청 수량 {want}권을 영수증 기준 남은 수량 {qty}권으로 보정했습니다.")
            signals.append({"code": "QTY_OVER", "points": 10, "message": "구매·잔여 수량 초과 신청"})
        cash, pts = _line_refund(item, qty)
        lines.append({"order_item_id": item.id, "title": item.title, "qty": qty, "requested_qty": want,
                      "unit_price": item.unit_price, "refund_cash": cash, "points_back": pts})

    # 3) Time windows and product rules (return / exchange / cancel of delivered goods).
    if ctype in ("return", "exchange") and order.status == "delivered" and order.delivered_at:
        days = (now - order.delivered_at).total_seconds() / 86400
        if seller_fault and days > DEFECT_WINDOW_DAYS:
            add("WINDOW_DEFECT_EXPIRED", "block", f"수령 후 {int(days)}일이 지나 {DEFECT_WINDOW_DAYS}일 이내 불량·오배송 기준을 넘었습니다.")
        if reason in ("change_of_mind", "other") and days > MIND_WINDOW_DAYS:
            add("WINDOW_MIND_EXPIRED", "block", f"수령 후 {int(days)}일이 지나 단순변심 반품 기간({MIND_WINDOW_DAYS}일)을 넘었습니다.")
    for ln in lines:
        item = by_id[ln["order_item_id"]]
        label = CATEGORY_KO.get(item.category, "상품")
        if not item.returnable and reason in ("change_of_mind", "other") and ctype != "cancel":
            add("NON_RETURNABLE", "block", f"'{item.title}'은(는) {label} 특성상 단순변심 반품·환불이 불가한 상품입니다.")
        elif not item.returnable and seller_fault and item.category == "ebook":
            add("EBOOK_DEFECT", "review", f"'{item.title}'은(는) 전자책이라 오류 여부를 상담원이 확인해야 합니다.")
        if claim.unsealed and reason in ("change_of_mind", "other") and ctype in ("return", "exchange"):
            add("UNSEALED", "block", f"개봉·사용한 {label}은(는) 단순변심 반품이 불가합니다.")

    # 4) Evidence for seller-fault claims.
    if seller_fault and ctype in ("return", "exchange") and claim.evidence_count == 0:
        add("NEED_EVIDENCE", "info", "불량·파손·오배송은 상품 상태를 확인할 수 있는 사진이 필요합니다.")

    # 5) Money.
    refund_cash = sum(ln["refund_cash"] for ln in lines)
    points_back = sum(ln["points_back"] for ln in lines)
    shipping_refund = 0
    deductions: list[dict] = []
    compensation: dict | None = None
    if ctype in ("cancel", "return", "exchange") and lines:
        open_after = sum(
            remaining_qty(i, others) - next((ln["qty"] for ln in lines if ln["order_item_id"] == i.id), 0)
            for i in order.items
        )
        fully = open_after <= 0
        remaining_goods = sum(
            i.unit_price * (remaining_qty(i, others) - next((ln["qty"] for ln in lines if ln["order_item_id"] == i.id), 0))
            for i in order.items
        )
        lost_free_shipping = order.shipping_fee == 0 and not fully and remaining_goods < FREE_SHIPPING_MIN
        if ctype == "cancel" or seller_fault:
            if fully and order.shipping_fee:
                shipping_refund = order.shipping_fee
            if lost_free_shipping and ctype == "cancel":
                deductions.append({"code": "SHIPPING_FEE_LOST", "amount": SHIPPING_FEE,
                                   "message": f"무료배송 기준({FREE_SHIPPING_MIN:,}원) 미달로 배송비 {SHIPPING_FEE:,}원 차감"})
        else:  # change of mind after delivery
            deductions.append({"code": "RETURN_FEE", "amount": RETURN_FEE, "message": f"단순변심 반품 배송비 {RETURN_FEE:,}원 차감"})
            if lost_free_shipping:
                deductions.append({"code": "SHIPPING_FEE_LOST", "amount": SHIPPING_FEE,
                                   "message": f"무료배송 기준({FREE_SHIPPING_MIN:,}원) 미달로 최초 배송비 {SHIPPING_FEE:,}원 차감"})
        refund_cash = max(0, refund_cash + shipping_refund - sum(d["amount"] for d in deductions))
        for d in deductions:
            add(d["code"], "info", d["message"])
        if seller_fault and ctype in ("return", "exchange"):
            compensation = {"kind": "points", "amount": DEFECT_COMPENSATION, "reason": "불량·파손·오배송 보상 적립금"}
            add("DEFECT_COMPENSATION", "info", f"반품 상품이 입고·검수를 통과하면 보상 적립금 {DEFECT_COMPENSATION:,}원이 지급됩니다.")
        if ctype == "exchange":
            refund_cash, points_back, shipping_refund = 0, 0, 0
            for ln in lines:
                ln["refund_cash"] = ln["points_back"] = 0
            if stock and any(stock.get(ln["order_item_id"], 10**6) < ln["qty"] for ln in lines):
                add("EXCHANGE_STOCK_LOW", "info", "교환할 상품의 재고가 부족해 입고 순서대로 재고가 확보되면 발송됩니다.")

    if ctype == "compensation":
        if reason == "late_delivery":
            dl = late_days(order, now)
            prior = [c for c in others if c.type == "compensation" and c.reason == "late_delivery"
                     and c.status in ACTIVE | {"completed"}]
            tier = next((amt for days, amt in LATE_TIERS if dl >= days), 0)
            if dl < LATE_GRACE_DAYS or not tier:
                add("NOT_LATE", "block", f"배송 예정일 기준 지연이 {LATE_GRACE_DAYS}일 미만이라 지연 보상 대상이 아닙니다.")
            elif prior:
                add("ALREADY_COMPENSATED", "block", "이 주문은 이미 배송 지연 보상이 접수·지급되었습니다.")
            else:
                compensation = {"kind": "points", "amount": tier, "reason": f"배송 {int(dl)}일 지연 보상 적립금"}
                add("LATE_COMPENSATION", "info", f"영수증 기준 배송 예정일보다 {int(dl)}일 늦어 적립금 {tier:,}원 보상 대상입니다.")
        elif reason == "missing_item":
            add("MISSING_ITEM_INVESTIGATE", "review", "배송 완료로 기록되었으나 받지 못했다는 신청입니다. 배송 기록 확인 후 상담원이 처리합니다.")
        else:
            add("OTHER_REASON", "review", "정해진 보상 기준에 없는 사유라 상담원이 확인합니다.")
    elif reason == "other" and ctype in ("return", "exchange") and not any(r["level"] == "block" for r in reasons):
        add("OTHER_REASON", "review", "사유가 '기타'라 상담원이 확인합니다.")

    # 6) Compare what the customer asked for with what the receipt supports.
    payable = refund_cash + points_back + (compensation["amount"] if ctype == "compensation" and compensation else 0)
    gross = sum(ln["unit_price"] * ln["qty"] for ln in lines) + (order.shipping_fee if ctype != "compensation" else 0)
    receipt_cap = order.paid_amount + order.points_used if ctype == "compensation" else gross
    if claim.claimed_amount is not None and not any(r["level"] == "block" for r in reasons):
        if claim.claimed_amount > receipt_cap:
            add("AMOUNT_EXCEEDS_RECEIPT", "review",
                f"신청 금액 {claim.claimed_amount:,}원이 영수증에서 확인되는 최대 {receipt_cap:,}원을 넘어 상담원이 확인합니다.")
            signals.append({"code": "AMOUNT_OVER_RECEIPT", "points": 30, "message": "영수증 금액을 초과해 신청"})
        elif claim.claimed_amount > payable and ctype != "compensation":
            add("AMOUNT_ADJUSTED", "warn",
                f"신청 금액 {claim.claimed_amount:,}원을 영수증·규정 기준 {payable:,}원으로 자동 보정했습니다.")
            signals.append({"code": "AMOUNT_OVER_POLICY", "points": 10, "message": "규정 금액보다 많이 신청"})

    # 7) Limits and abuse.
    if payable + (compensation["amount"] if compensation and ctype != "compensation" else 0) > AUTO_LIMIT:
        add("OVER_AUTO_LIMIT", "review", f"처리 금액이 자동 처리 한도({AUTO_LIMIT:,}원)를 넘어 상담원 승인이 필요합니다.")
    abuse_score = abuse.score(signals)
    if abuse_score >= ABUSE_REVIEW_SCORE:
        add("ABUSE_SUSPECTED", "review", "신청 내용을 담당 상담원이 확인합니다.")

    blocks = [r for r in reasons if r["level"] == "block"]
    if blocks:  # a rejected claim pays nothing, so drop the fee and compensation notes computed above
        reasons = [r for r in reasons if r["level"] in ("block", "warn")]
        refund_cash = points_back = shipping_refund = payable = 0
        deductions, compensation = [], None
        for ln in lines:
            ln["refund_cash"] = ln["points_back"] = 0
    reviews = [r for r in reasons if r["level"] == "review"]
    needs_info = any(r["code"] == "NEED_EVIDENCE" for r in reasons)
    requires_return = ctype in ("return", "exchange")
    if blocks:
        outcome = "auto_rejected"
    elif needs_info:
        outcome = "needs_info"
    elif reviews:
        outcome = "needs_review"
    elif requires_return:
        outcome = "approved_pending_return"
    else:
        outcome = "auto_approved"

    return {
        "outcome": outcome,
        "resolution": {"cancel": "refund", "return": "refund", "exchange": "exchange", "compensation": "compensation"}[ctype],
        "requires_return": requires_return,
        "reasons": reasons,
        "lines": lines,
        "refund_cash": refund_cash,
        "points_back": points_back,
        "shipping_refund": shipping_refund,
        "deductions": deductions,
        "compensation": compensation,
        "claimed_amount": claim.claimed_amount,
        "payable": payable,
        "abuse": {"score": abuse_score, "signals": signals},
        "policy_refs": sorted({r["rule"] for r in reasons if r["rule"]}),
        "evaluated_at": now.isoformat(),
    }
