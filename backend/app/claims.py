"""Claim workflow: judge, apply the outcome, record every step.

  submit -> decide (rules) -> auto_approved ........................ completed
                           -> approved_pending_return -> received -> compensation queue -> completed
                           -> needs_review (agent) -> approve / reject
                           -> needs_info (customer adds a photo) -> decide again
                           -> auto_rejected ............................................. rejected
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .models import AuditLog, Claim, Order, PointLedger, Product, User
from .rules import abuse
from .rules.policy import SELLER_FAULT
from .rules.refund import decide

STATUS_BY_OUTCOME = {
    "auto_rejected": "rejected",
    "needs_info": "needs_info",
    "needs_review": "needs_review",
    "approved_pending_return": "awaiting_return",
    "auto_approved": "completed",
}


class ClaimError(ValueError):
    pass


def log(db: Session, claim: Claim, actor: str, action: str, **detail) -> None:
    db.add(AuditLog(claim_id=claim.id, actor=actor, action=action, detail=detail))


def _others(db: Session, claim: Claim) -> list[Claim]:
    return [c for c in db.scalars(select(Claim).where(Claim.order_id == claim.order_id)).all() if c.id != claim.id]


def _stock_by_line(db: Session, order: Order) -> dict[int, int]:
    return {i.id: db.get(Product, i.product_id).stock for i in order.items}


def evaluate(db: Session, claim: Claim) -> dict:
    """Run the rules and store the result. Applies the payout when the outcome is auto_approved."""
    order = db.get(Order, claim.order_id)
    history = abuse.history_signals(db, claim.user_id, exclude_claim_id=claim.id)
    decision = decide(order, claim, others=_others(db, claim), history=history, now=clock.now(),
                      stock=_stock_by_line(db, order))
    claim.decision = decision
    claim.status = STATUS_BY_OUTCOME[decision["outcome"]]
    claim.decided_by = "system"
    log(db, claim, "system", "decided", outcome=decision["outcome"],
        reasons=[r["code"] for r in decision["reasons"]], payable=decision["payable"],
        abuse_score=decision["abuse"]["score"])
    if decision["outcome"] == "approved_pending_return":
        claim.return_tracking = claim.return_tracking or f"CB{claim.id:08d}"
    if decision["outcome"] == "auto_approved":
        execute(db, claim, actor="system")
    return decision


def create_claim(db: Session, user: User, *, order_id: int, type: str, reason: str, items: list[dict] | None,
                 claimed_amount: int | None, unsealed: bool, evidence_count: int, description: str,
                 conversation_id: int | None = None) -> Claim:
    order = db.get(Order, order_id)
    if order is None:
        raise ClaimError("주문을 찾을 수 없습니다.")
    claim = Claim(user_id=user.id, order_id=order_id, type=type, reason=reason, items=items or [],
                  claimed_amount=claimed_amount, unsealed=unsealed, evidence_count=evidence_count,
                  description=description, conversation_id=conversation_id)
    db.add(claim)
    db.flush()
    log(db, claim, user.name, "submitted", type=type, reason=reason, claimed_amount=claimed_amount,
        unsealed=unsealed, evidence_count=evidence_count)
    evaluate(db, claim)
    db.commit()
    return claim


def add_evidence(db: Session, claim: Claim, count: int) -> Claim:
    if claim.status != "needs_info":
        raise ClaimError("추가 자료를 받을 수 있는 상태가 아닙니다.")
    claim.evidence_count += max(1, count)
    log(db, claim, "customer", "evidence_added", evidence_count=claim.evidence_count)
    evaluate(db, claim)
    db.commit()
    return claim


def withdraw(db: Session, claim: Claim) -> Claim:
    if claim.status not in ("needs_info", "needs_review", "awaiting_return"):
        raise ClaimError("이미 처리 중이거나 완료된 신청은 철회할 수 없습니다.")
    claim.status = "withdrawn"
    log(db, claim, "customer", "withdrawn")
    db.commit()
    return claim


def agent_decide(db: Session, claim: Claim, *, approve: bool, note: str, agent: str) -> Claim:
    if claim.status != "needs_review":
        raise ClaimError("상담원 확인이 필요한 신청만 승인·거절할 수 있습니다.")
    system_outcome = claim.decision.get("outcome")
    claim.agent_note = note or None
    claim.decided_by = agent
    if approve:
        claim.manager_approved = True
        claim.hold_reason = None
        if claim.return_received_at:
            claim.inspection = "ok"
            claim.status = "return_received"
        elif claim.decision.get("requires_return"):
            claim.status = "awaiting_return"
            claim.return_tracking = claim.return_tracking or f"CB{claim.id:08d}"
        else:
            execute(db, claim, actor=agent)
    else:
        claim.status = "rejected"
    # The pair (what the rules said, what the agent did) is the feedback record for tuning the rules.
    log(db, claim, agent, "agent_override" if approve or system_outcome == "auto_approved" else "agent_confirmed",
        system_outcome=system_outcome, agent_action="approve" if approve else "reject", note=note,
        reasons=[r["code"] for r in claim.decision.get("reasons", []) if r["level"] == "review"])
    db.commit()
    return claim


def receive_return(db: Session, claim: Claim, *, inspection: str, note: str | None, agent: str) -> Claim:
    """Warehouse scan: the returned goods arrived. The time recorded here fixes the claim's place in the queue."""
    if claim.status != "awaiting_return":
        raise ClaimError("반품 입고를 기다리는 신청이 아닙니다.")
    claim.return_received_at = clock.now()
    claim.inspection = inspection
    claim.inspection_note = note
    claim.status = "return_received"
    if inspection == "mismatch":
        claim.status = "needs_review"
        claim.hold_reason = f"입고 검수 불일치: {note or '신청 사유와 상품 상태가 다릅니다.'}"
    log(db, claim, agent, "received", inspection=inspection, note=note)
    db.commit()
    return claim


def set_inspection(db: Session, claim: Claim, *, inspection: str, note: str | None, agent: str) -> Claim:
    if claim.status != "return_received":
        raise ClaimError("입고 완료된 신청만 검수 결과를 바꿀 수 있습니다.")
    claim.inspection = inspection
    claim.inspection_note = note
    if inspection == "mismatch":
        claim.status = "needs_review"
        claim.hold_reason = f"입고 검수 불일치: {note or '신청 사유와 상품 상태가 다릅니다.'}"
    log(db, claim, agent, "inspected", inspection=inspection, note=note)
    db.commit()
    return claim


def _credit(db: Session, user: User, delta: int, reason: str, claim: Claim) -> None:
    if not delta:
        return
    user.points += delta
    db.add(PointLedger(user_id=user.id, delta=delta, reason=reason, order_id=claim.order_id, claim_id=claim.id))


def stock_delta(claim: Claim, order: Order) -> dict[int, int]:
    """Shelf change when this claim is paid: cancelled goods return, an exchange sends a replacement out,
    and a resalable return (change of mind, wrong item) goes back on the shelf. Defective goods do not."""
    by_id = {i.id: i for i in order.items}
    out: dict[int, int] = {}
    for ln in claim.decision.get("lines", []):
        pid, qty = by_id[ln["order_item_id"]].product_id, ln["qty"]
        delta = 0
        if claim.type == "cancel":
            delta += qty
        else:
            if claim.type == "exchange":
                delta -= qty
            if claim.reason in ("change_of_mind", "wrong_item"):
                delta += qty
        out[pid] = out.get(pid, 0) + delta
    return out


def execute(db: Session, claim: Claim, *, actor: str) -> None:
    """Pay out an approved claim: update the receipt lines, stock, order and the customer's points."""
    order = db.get(Order, claim.order_id)
    user = db.get(User, claim.user_id)
    d = claim.decision
    by_id = {i.id: i for i in order.items}
    now = clock.now()

    for ln in d.get("lines", []):
        item = by_id[ln["order_item_id"]]
        item.refunded_qty += ln["qty"]
        item.refunded_amount += ln["refund_cash"]
    for product_id, delta in stock_delta(claim, order).items():
        db.get(Product, product_id).stock += delta

    cash = d.get("refund_cash", 0)
    claim.refund_amount = cash
    claim.points_returned = d.get("points_back", 0)
    order.refunded_amount += cash
    _credit(db, user, claim.points_returned, "환불에 사용된 적립금 반환", claim)
    comp = d.get("compensation")
    if comp:
        claim.compensation_amount = comp["amount"]
        _credit(db, user, comp["amount"], comp["reason"], claim)

    if claim.type == "cancel" and all(i.refunded_qty >= i.qty for i in order.items):
        order.status = "cancelled"
        order.cancelled_at = now
    if claim.type == "exchange":
        d["exchange_shipment"] = {"tracking": f"EX{claim.id:08d}", "shipped_at": now.isoformat()}
        claim.decision = {**d}  # reassign so the JSON column is saved

    claim.status = "completed"
    claim.processed_at = now
    log(db, claim, actor, "paid", refund_cash=cash, points_returned=claim.points_returned,
        compensation=claim.compensation_amount, resolution=d.get("resolution"))
