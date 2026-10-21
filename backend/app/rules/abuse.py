"""Refund-abuse signals from a customer's own history. Agent-facing only: never shown to customers."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import Claim, Order
from .policy import ABUSE_WINDOW_DAYS

ACTIVE = {"needs_info", "needs_review", "awaiting_return", "return_received"}


def history_signals(db: Session, user_id: int, exclude_claim_id: int | None = None) -> list[dict]:
    since = clock.now() - timedelta(days=ABUSE_WINDOW_DAYS)
    claims = [
        c for c in db.scalars(select(Claim).where(Claim.user_id == user_id, Claim.created_at >= since)).all()
        if c.id != exclude_claim_id and c.status != "withdrawn"
    ]
    signals: list[dict] = []
    n = len(claims)
    if n >= 5:
        signals.append({"code": "FREQUENT_CLAIMS", "points": 45, "message": f"최근 {ABUSE_WINDOW_DAYS}일 클레임 {n}건"})
    elif n >= 3:
        signals.append({"code": "FREQUENT_CLAIMS", "points": 25, "message": f"최근 {ABUSE_WINDOW_DAYS}일 클레임 {n}건"})

    rejected = sum(1 for c in claims if c.status == "rejected" and c.decided_by == "system")
    if rejected >= 2:
        signals.append({"code": "REPEAT_POLICY_VIOLATIONS", "points": 15, "message": f"규정 위반으로 자동 거절된 이력 {rejected}건"})

    spent = sum(o.paid_amount for o in db.scalars(select(Order).where(Order.user_id == user_id, Order.paid_at >= since)).all())
    refunded = sum(c.refund_amount for c in claims)
    if spent and len([1 for _ in claims]) >= 2 and refunded / spent > 0.5:
        signals.append({"code": "HIGH_REFUND_RATIO", "points": 20, "message": f"최근 구매액 대비 환불 비율 {refunded / spent:.0%}"})
    return signals


def score(signals: list[dict]) -> int:
    return min(100, sum(s["points"] for s in signals))
