"""Compensation queue: returned goods are processed in the order they arrived at the warehouse.

A claim waits here once its goods are received. It is paid when every condition holds:
  1. inspection passed (the returned item matches the claimed reason)
  2. no abuse hold, unless an agent approved it
  3. amount within the automatic limit, unless an agent approved it
  4. exchange only: the replacement is in stock (stock goes to the earliest arrival first)
Claims that fail a condition stay in line with the blocker shown; they never block the ones behind them.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import claims
from .models import Claim, Order, Product
from .rules.policy import ABUSE_REVIEW_SCORE, AUTO_LIMIT


def _blockers(db: Session, c: Claim, stock: dict[int, int]) -> list[dict]:
    if c.status != "return_received":  # held for an agent (e.g. inspection mismatch)
        return [{"code": "ON_HOLD", "message": c.hold_reason or "상담원 확인이 필요합니다."}]
    out: list[dict] = []
    if c.inspection != "ok":
        out.append({"code": "NOT_INSPECTED", "message": "입고 검수 결과가 아직 '정상'으로 확인되지 않았습니다."})
    if c.hold_reason:
        out.append({"code": "ON_HOLD", "message": c.hold_reason})
    d = c.decision
    if not c.manager_approved:
        if d.get("abuse", {}).get("score", 0) >= ABUSE_REVIEW_SCORE:
            out.append({"code": "ABUSE_HOLD", "message": "상담원 승인 전에는 자동 처리할 수 없습니다 (내부 점검 대상)."})
        total = d.get("payable", 0) + (d.get("compensation") or {}).get("amount", 0)
        if total > AUTO_LIMIT:
            out.append({"code": "OVER_LIMIT", "message": f"처리 금액 {total:,}원이 자동 처리 한도 {AUTO_LIMIT:,}원을 넘습니다."})
    if c.type == "exchange":
        product_of = {i.id: i.product_id for i in db.get(Order, c.order_id).items}
        for ln in d.get("lines", []):
            have = stock.get(product_of[ln["order_item_id"]], 0)
            if have < ln["qty"]:
                out.append({"code": "OUT_OF_STOCK", "message": f"교환 상품 '{ln['title']}' 재고 부족 (필요 {ln['qty']}, 보유 {max(have, 0)})"})
    return out


def _stock(db: Session) -> dict[int, int]:
    return {p.id: p.stock for p in db.scalars(select(Product)).all()}


def waiting(db: Session) -> list[Claim]:
    rows = db.scalars(select(Claim).where(Claim.status == "return_received")).all()
    held = db.scalars(select(Claim).where(Claim.status == "needs_review", Claim.return_received_at.is_not(None))).all()
    return sorted([*rows, *held], key=lambda c: (c.return_received_at, c.id))


def build_queue(db: Session) -> list[dict]:
    """The line as it stands, with each claim's blockers. Stock is handed out in arrival order, as process() will."""
    stock = _stock(db)
    out = []
    for pos, c in enumerate(waiting(db), start=1):
        blockers = _blockers(db, c, stock)
        if not blockers:
            for pid, delta in claims.stock_delta(c, db.get(Order, c.order_id)).items():
                stock[pid] = stock.get(pid, 0) + delta
        out.append({"position": pos, "claim_id": c.id, "order_no": db.get(Order, c.order_id).order_no,
                    "customer": c.user.name, "type": c.type, "reason": c.reason,
                    "received_at": c.return_received_at.isoformat(), "inspection": c.inspection,
                    "amount": c.decision.get("payable", 0), "compensation": (c.decision.get("compensation") or {}).get("amount", 0),
                    "ready": not blockers, "blockers": blockers,
                    "items": [{"title": ln["title"], "qty": ln["qty"]} for ln in c.decision.get("lines", [])]})
    return out


def process(db: Session, *, actor: str, limit: int | None = None, claim_ids: list[int] | None = None) -> list[dict]:
    """Pay every ready claim, oldest arrival first. Returns what happened to each claim in line."""
    stock = _stock(db)
    results: list[dict] = []
    paid = 0
    for c in waiting(db):
        if claim_ids is not None and c.id not in claim_ids:
            continue
        blockers = _blockers(db, c, stock)
        if limit is not None and paid >= limit and not blockers:
            results.append({"claim_id": c.id, "result": "skipped", "blockers": [{"code": "LIMIT", "message": "이번 처리 개수 제한에 걸렸습니다."}]})
            continue
        if blockers:
            results.append({"claim_id": c.id, "result": "held", "blockers": blockers})
            continue
        claims.execute(db, c, actor=actor)
        paid += 1
        stock = _stock(db)  # execute() changed shelves; the next claim in line sees the new numbers
        results.append({"claim_id": c.id, "result": "paid", "refund": c.refund_amount,
                        "points": c.points_returned, "compensation": c.compensation_amount})
    db.commit()
    return results
