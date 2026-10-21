"""Agent-facing API (demo build: no sign-in; put it behind real auth before production)."""
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import claims as claim_svc
from . import cs, queue
from .api_shop import review_out
from .config import settings
from .copilot.llm.base import LLMError
from .copilot.retrieve import get_retriever
from .dashboard import build_dashboard
from .db import get_db
from .models import AuditLog, Claim, Conversation, Order, Review, User

router = APIRouter(prefix="/api/admin")


class NewConversation(BaseModel):
    user_id: int
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    order_id: int | None = None


class CustomerMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class CheckText(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class AgentMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    draft_style: str | None = None
    draft_text: str | None = None


class Rejection(BaseModel):
    draft_style: str | None = None


class StatusUpdate(BaseModel):
    status: Literal["open", "resolved", "escalated"]


class Decision(BaseModel):
    note: str = Field(default="", max_length=1000)


class Receive(BaseModel):
    inspection: Literal["pending", "ok", "mismatch"] = "ok"
    note: str | None = Field(default=None, max_length=500)


class Process(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=500)
    claim_ids: list[int] | None = None


class ReviewStatus(BaseModel):
    status: Literal["visible", "hidden"]


# ---------------------------------------------------------------- conversations
def _message_out(m) -> dict:
    return {"id": m.id, "role": m.role, "text": m.text, "analysis": m.analysis, "created_at": m.created_at.isoformat()}


def _conv_out(db: Session, c: Conversation, full: bool = False) -> dict:
    out = {
        "id": c.id, "customer_name": c.customer_name, "subject": c.subject, "category": c.category, "sentiment": c.sentiment,
        "urgency": c.urgency, "status": c.status, "order_id": c.order_id, "updated_at": c.updated_at.isoformat(),
        "preview": c.messages[-1].text[:80] if c.messages else "",
        "awaiting_reply": bool(c.messages) and c.messages[-1].role == "customer",
    }
    if full:
        out["messages"] = [_message_out(m) for m in c.messages]
        out["summary"] = c.summary
        facts = cs.order_facts(db, c)
        out["order_no"] = facts["order"]["order_no"] if facts else None
        claims = db.scalars(select(Claim).where(Claim.order_id == c.order_id).order_by(Claim.id.desc())).all() if c.order_id else []
        out["claims"] = [cs.claim_summary(x, internal=True) for x in claims]
    return out


def _conv(db: Session, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "conversation not found")
    return conv


def _llm_guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LLMError as exc:
        raise HTTPException(502, f"LLM error: {exc}") from exc


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).options(selectinload(Conversation.messages))).all()
    rank = {"high": 0, "medium": 1, "low": 2, None: 3}
    rows = sorted(rows, key=lambda c: (c.status != "open", not (c.messages and c.messages[-1].role == "customer"),
                                       rank.get(c.urgency, 3), -c.updated_at.timestamp()))
    return [_conv_out(db, c) for c in rows]


@router.post("/conversations", status_code=201)
def new_conversation(body: NewConversation, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(404, "고객을 찾을 수 없습니다.")
    try:
        conv = _llm_guard(cs.create_inquiry, db, user, subject=body.subject, message=body.message, order_id=body.order_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _conv_out(db, conv, full=True)


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    return _conv_out(db, _conv(db, conv_id), full=True)


@router.post("/conversations/{conv_id}/customer-messages", status_code=201)
def customer_message(conv_id: int, body: CustomerMessage, db: Session = Depends(get_db)):
    conv = _conv(db, conv_id)
    _llm_guard(cs.handle_customer_message, db, conv, body.text)
    db.refresh(conv)
    return _conv_out(db, conv, full=True)


@router.post("/conversations/{conv_id}/check")
def check(conv_id: int, body: CheckText, db: Session = Depends(get_db)):
    return cs.check_text(db, _conv(db, conv_id), body.text)


@router.post("/conversations/{conv_id}/agent-messages", status_code=201)
def agent_message(conv_id: int, body: AgentMessage, db: Session = Depends(get_db)):
    conv = _conv(db, conv_id)
    try:
        cs.send_agent_message(db, conv, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, {"message": "검증을 통과하지 못해 보낼 수 없습니다.", "validation": exc.args[0]}) from exc
    db.refresh(conv)
    return _conv_out(db, conv, full=True)


@router.post("/conversations/{conv_id}/reject-draft", status_code=204)
def reject_draft(conv_id: int, body: Rejection, db: Session = Depends(get_db)):
    cs.record_rejection(db, _conv(db, conv_id), body.draft_style)


@router.post("/conversations/{conv_id}/summary")
def summary(conv_id: int, db: Session = Depends(get_db)):
    return _llm_guard(cs.summarize_conversation, db, _conv(db, conv_id))


@router.post("/conversations/{conv_id}/status")
def set_status(conv_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    conv = _conv(db, conv_id)
    conv.status = body.status
    db.commit()
    return _conv_out(db, conv)


# ---------------------------------------------------------------- claims
def _claim(db: Session, claim_id: int) -> Claim:
    c = db.get(Claim, claim_id)
    if c is None:
        raise HTTPException(404, "claim not found")
    return c


def _claim_detail(db: Session, c: Claim) -> dict:
    audit = db.scalars(select(AuditLog).where(AuditLog.claim_id == c.id).order_by(AuditLog.id)).all()
    order = db.get(Order, c.order_id)
    return cs.claim_summary(c, internal=True) | {
        "audit": [{"actor": a.actor, "action": a.action, "detail": a.detail, "at": a.created_at.isoformat()} for a in audit],
        "receipt": {"order_no": order.order_no, "status": order.status, "items_total": order.items_total,
                    "shipping_fee": order.shipping_fee, "points_used": order.points_used, "paid_amount": order.paid_amount,
                    "paid_at": order.paid_at.isoformat(),
                    "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                    "expected_delivery_at": order.expected_delivery_at.isoformat() if order.expected_delivery_at else None,
                    "items": [{"id": i.id, "title": i.title, "qty": i.qty, "paid_amount": i.paid_amount,
                               "points_share": i.points_share, "refunded_qty": i.refunded_qty} for i in order.items]},
    }


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except claim_svc.ClaimError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/orders")
def customer_orders(user_id: int, db: Session = Depends(get_db)):
    """Orders of one customer, for linking a simulated inquiry to a receipt."""
    rows = db.scalars(select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())).all()
    return [{"id": o.id, "order_no": o.order_no, "status": o.status, "status_ko": cs.ORDER_STATUS_KO[o.status],
             "title": o.items[0].title + (f" 외 {len(o.items) - 1}건" if len(o.items) > 1 else "")} for o in rows]


@router.get("/claims")
def list_claims(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Claim).order_by(Claim.id.desc())
    if status:
        stmt = stmt.where(Claim.status == status)
    return [cs.claim_summary(c, internal=True) for c in db.scalars(stmt).all()]


@router.get("/claims/stats")
def claim_stats(db: Session = Depends(get_db)):
    claims = db.scalars(select(Claim)).all()
    by_status = Counter(c.status for c in claims)
    logs = db.scalars(select(AuditLog).where(AuditLog.action.in_(["agent_override", "agent_confirmed"]))).all()
    rules: Counter = Counter()
    for c in claims:
        rules.update({r["code"] for r in c.decision.get("reasons", []) if r["level"] in ("block", "review")})
    overridden: Counter = Counter()
    for a in logs:
        if a.action == "agent_override":
            overridden.update(a.detail.get("reasons", []))
    return {
        "total": len(claims), "by_status": dict(by_status),
        "rule_hits": dict(rules.most_common()),
        "agent_reviews": len(logs), "agent_overrides": sum(1 for a in logs if a.action == "agent_override"),
        "overridden_rules": dict(overridden.most_common()),
    }


@router.get("/claims/{claim_id}")
def claim_detail(claim_id: int, db: Session = Depends(get_db)):
    return _claim_detail(db, _claim(db, claim_id))


@router.post("/claims/{claim_id}/approve")
def approve(claim_id: int, body: Decision, db: Session = Depends(get_db)):
    c = _call(claim_svc.agent_decide, db, _claim(db, claim_id), approve=True, note=body.note, agent=settings.agent_name)
    return _claim_detail(db, c)


@router.post("/claims/{claim_id}/reject")
def reject(claim_id: int, body: Decision, db: Session = Depends(get_db)):
    c = _call(claim_svc.agent_decide, db, _claim(db, claim_id), approve=False, note=body.note, agent=settings.agent_name)
    return _claim_detail(db, c)


@router.post("/claims/{claim_id}/receive")
def receive(claim_id: int, body: Receive, db: Session = Depends(get_db)):
    c = _call(claim_svc.receive_return, db, _claim(db, claim_id), inspection=body.inspection, note=body.note, agent="물류센터")
    return _claim_detail(db, c)


@router.post("/claims/{claim_id}/inspection")
def inspection(claim_id: int, body: Receive, db: Session = Depends(get_db)):
    c = _call(claim_svc.set_inspection, db, _claim(db, claim_id), inspection=body.inspection, note=body.note, agent="물류센터")
    return _claim_detail(db, c)


# ---------------------------------------------------------------- compensation queue
@router.get("/queue")
def get_queue(db: Session = Depends(get_db)):
    entries = queue.build_queue(db)
    inbound = db.scalars(select(Claim).where(Claim.status == "awaiting_return").order_by(Claim.id)).all()
    return {"queue": entries,
            "awaiting_return": [cs.claim_summary(c, internal=True) for c in inbound]}


@router.post("/queue/process")
def process_queue(body: Process, db: Session = Depends(get_db)):
    results = queue.process(db, actor=settings.agent_name, limit=body.limit, claim_ids=body.claim_ids)
    return {"results": results, "paid": sum(1 for r in results if r["result"] == "paid"),
            "held": sum(1 for r in results if r["result"] == "held"), "queue": queue.build_queue(db)}


# ---------------------------------------------------------------- reviews
@router.get("/reviews")
def list_reviews(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Review).order_by(Review.id.desc())
    if status:
        stmt = stmt.where(Review.status == status)
    rows = db.scalars(stmt).all()
    # Pending moderation first, then low-rating reviews that mention defects (proactive outreach).
    rows.sort(key=lambda r: (r.status != "flagged", not any(f.get("code") == "CS_FOLLOW_UP" for f in r.flags), -r.id))
    return [review_out(r, internal=True) for r in rows]


@router.post("/reviews/{review_id}/status")
def set_review_status(review_id: int, body: ReviewStatus, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if r is None:
        raise HTTPException(404, "review not found")
    r.status = body.status
    db.commit()
    return review_out(r, internal=True)


# ---------------------------------------------------------------- misc
@router.get("/dashboard")
def dashboard(days: int = 14, db: Session = Depends(get_db)):
    return build_dashboard(db, days=max(7, min(days, 60)))


@router.get("/kpi")
def kpi(db: Session = Depends(get_db)):
    return cs.kpi(db)


@router.get("/kb")
def knowledge_base():
    return [{"id": c.id, "category": c.category, "title": c.title, "section": c.section, "text": c.text}
            for c in get_retriever().chunks]
