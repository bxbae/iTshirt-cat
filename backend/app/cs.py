"""Support workflows: a customer writes, the copilot drafts, an agent replies, a case closes."""
import difflib
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .copilot import steps
from .copilot.llm.anthropic_provider import AnthropicProvider
from .copilot.llm.base import LLMProvider
from .copilot.facts import pick_claim
from .copilot.llm.mock_provider import MockProvider
from .copilot.validate import check_reply
from .models import Claim, Conversation, FeedbackEvent, Message, Order, User

ORDER_STATUS_KO = {"paid": "결제완료", "preparing": "상품준비중", "shipped": "배송중", "delivered": "배송완료", "cancelled": "취소"}
CLAIM_TYPE_KO = {"cancel": "주문 취소", "return": "반품", "exchange": "교환", "compensation": "보상"}


@lru_cache
def get_llm() -> LLMProvider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    return MockProvider()


# ---------------------------------------------------------------- customer-safe views of a decision
def public_decision(decision: dict) -> dict:
    """What the customer may see: outcome, reasons, amounts. Never the abuse score or its signals."""
    return {k: v for k, v in decision.items() if k != "abuse"}


def claim_summary(c: Claim, *, internal: bool = False) -> dict:
    d = c.decision or {}
    out = {
        "id": c.id, "order_id": c.order_id, "type": c.type, "reason": c.reason, "status": c.status,
        "created_at": c.created_at.isoformat(), "description": c.description, "claimed_amount": c.claimed_amount,
        "unsealed": c.unsealed, "evidence_count": c.evidence_count,
        "outcome": d.get("outcome"), "resolution": d.get("resolution"), "requires_return": d.get("requires_return", False),
        "reasons": d.get("reasons", []), "lines": d.get("lines", []), "deductions": d.get("deductions", []),
        "expected_refund": d.get("refund_cash", 0), "points_back": d.get("points_back", 0),
        "compensation": (d.get("compensation") or {}).get("amount", 0), "payable": d.get("payable", 0),
        "tracking": c.return_tracking, "return_received_at": c.return_received_at.isoformat() if c.return_received_at else None,
        "inspection": c.inspection, "refund": c.refund_amount, "compensation_paid": c.compensation_amount,
        "points_returned": c.points_returned, "policy_refs": d.get("policy_refs", []),
        "exchange_shipment": d.get("exchange_shipment"),
        "processed_at": c.processed_at.isoformat() if c.processed_at else None,
        "conversation_id": c.conversation_id,
    }
    if internal:
        out.update({"customer": c.user.name, "order_no": c.order.order_no, "abuse": d.get("abuse"), "decided_by": c.decided_by,
                    "agent_note": c.agent_note, "hold_reason": c.hold_reason, "manager_approved": c.manager_approved,
                    "inspection_note": c.inspection_note, "user_id": c.user_id})
    return out


def order_facts(db: Session, conv: Conversation) -> dict | None:
    """Receipt + claim state the draft may rely on. Customer-visible fields only."""
    if not conv.order_id:
        return None
    order = db.get(Order, conv.order_id)
    if order is None:
        return None
    claims = db.scalars(select(Claim).where(Claim.order_id == order.id).order_by(Claim.id.desc())).all()
    return {
        "order": {
            "order_no": order.order_no, "status": order.status, "status_ko": ORDER_STATUS_KO[order.status],
            "paid_amount": order.paid_amount, "shipping_fee": order.shipping_fee, "points_used": order.points_used,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "expected_delivery_at": order.expected_delivery_at.isoformat() if order.expected_delivery_at else None,
            "items": [{"title": i.title, "qty": i.qty, "paid_amount": i.paid_amount} for i in order.items],
        },
        "claims": [{
            "id": c.id, "type": c.type, "reason": c.reason, "status": c.status, "outcome": (c.decision or {}).get("outcome"),
            "requires_return": (c.decision or {}).get("requires_return", False),
            "expected_refund": (c.decision or {}).get("refund_cash", 0),
            "points_back": (c.decision or {}).get("points_back", 0),
            "compensation": ((c.decision or {}).get("compensation") or {}).get("amount", 0),
            "refund": c.refund_amount, "tracking": c.return_tracking,
            "reasons": [{"code": r["code"], "level": r["level"], "message": r["message"]} for r in (c.decision or {}).get("reasons", [])],
            "policy_refs": (c.decision or {}).get("policy_refs", []),
            "lines": [{"title": ln["title"], "qty": ln["qty"], "gross": ln["unit_price"] * ln["qty"]} for ln in (c.decision or {}).get("lines", [])],
        } for c in claims],
    }


# ---------------------------------------------------------------- conversation workflow
def _history(conv: Conversation) -> list[dict]:
    return [{"role": m.role, "text": m.text} for m in conv.messages]


def latest_context(conv: Conversation) -> tuple[list[dict], dict | None]:
    for m in reversed(conv.messages):
        if m.role == "customer" and m.analysis:
            return m.analysis.get("sources", []), m.analysis.get("facts")
    return [], None


def handle_customer_message(db: Session, conv: Conversation, text: str, llm: LLMProvider | None = None) -> Message:
    """Triage, retrieve policy, attach the receipt facts, draft 3 replies and validate each one."""
    llm = llm or get_llm()
    timer = steps.Timer()
    analysis = timer.run("analyze", steps.analyze, llm, text)
    facts = order_facts(db, conv)
    picked = pick_claim((facts or {}).get("claims", []), text)
    refs = sorted(picked.get("policy_refs", [])) if picked else []
    sources = timer.run("retrieve", steps.retrieve, analysis["search_query"], text, analysis["category"], refs)

    msg = Message(conversation=conv, role="customer", text=text)
    db.add(msg)
    db.flush()
    drafts = timer.run("drafts", steps.drafts, llm, customer_name=conv.customer_name, category=analysis["category"],
                       sentiment=analysis["sentiment"], history=_history(conv), sources=sources, facts=facts)
    timer.ms["total"] = sum(timer.ms.values())

    msg.analysis = {"classification": analysis, "sources": sources, "facts": facts, "drafts": drafts, "timings_ms": timer.ms}
    conv.category = analysis["category"]
    conv.sentiment = analysis["sentiment"]
    order = ["low", "medium", "high"]  # urgency only escalates within a conversation
    if conv.urgency is None or order.index(analysis["urgency"]) > order.index(conv.urgency):
        conv.urgency = analysis["urgency"]
    conv.status = "open"
    db.commit()
    return msg


def create_inquiry(db: Session, user: User, *, subject: str, message: str, order_id: int | None = None,
                   llm: LLMProvider | None = None) -> Conversation:
    if order_id is not None:
        order = db.get(Order, order_id)
        if order is None or order.user_id != user.id:
            raise ValueError("본인의 주문만 연결할 수 있습니다.")
    conv = Conversation(user_id=user.id, customer_name=user.name, subject=subject, order_id=order_id)
    db.add(conv)
    db.flush()
    handle_customer_message(db, conv, message, llm)
    db.refresh(conv)
    return conv


def send_agent_message(db: Session, conv: Conversation, *, text: str, draft_style: str | None, draft_text: str | None) -> Message:
    sources, facts = latest_context(conv)
    facts = order_facts(db, conv) or facts  # judge against the claim's state right now
    validation = check_reply(text, sources, facts)
    if not validation["passed"]:
        raise ValueError(validation)
    msg = Message(conversation=conv, role="agent", text=text, analysis={"validation": validation})
    db.add(msg)
    db.flush()
    if draft_text:
        ratio = 1 - difflib.SequenceMatcher(None, draft_text, text).ratio()
        db.add(FeedbackEvent(conversation_id=conv.id, message_id=msg.id, draft_style=draft_style,
                             action="accepted" if ratio < 0.05 else "edited", edit_ratio=round(ratio, 3)))
    else:
        db.add(FeedbackEvent(conversation_id=conv.id, message_id=msg.id, action="manual"))
    db.commit()
    return msg


def check_text(db: Session, conv: Conversation, text: str) -> dict:
    sources, facts = latest_context(conv)
    return check_reply(text, sources, order_facts(db, conv) or facts)


def record_rejection(db: Session, conv: Conversation, draft_style: str | None) -> None:
    db.add(FeedbackEvent(conversation_id=conv.id, draft_style=draft_style, action="rejected"))
    db.commit()


def summarize_conversation(db: Session, conv: Conversation, llm: LLMProvider | None = None) -> dict:
    llm = llm or get_llm()
    facts = order_facts(db, conv)
    claim_status = facts["claims"][0]["status"] if facts and facts["claims"] else None
    summary = steps.summarize(llm, messages=_history(conv), category=conv.category, claim_status=claim_status)
    conv.summary = summary
    conv.status = "escalated" if summary["escalate"] else "resolved" if summary["resolved"] else conv.status
    db.commit()
    return summary


def kpi(db: Session) -> dict:
    counts = {a: n for a, n in db.execute(select(FeedbackEvent.action, func.count()).group_by(FeedbackEvent.action)).all()}
    from_drafts = counts.get("accepted", 0) + counts.get("edited", 0)
    replies = from_drafts + counts.get("manual", 0)
    avg_edit = db.scalar(select(func.avg(FeedbackEvent.edit_ratio)).where(FeedbackEvent.edit_ratio.is_not(None)))
    customer_msgs = db.scalars(select(Message).where(Message.role == "customer")).all()
    latencies = [m.analysis["timings_ms"]["total"] for m in customer_msgs if m.analysis and "timings_ms" in m.analysis]
    drafts = [d for m in customer_msgs if m.analysis for d in m.analysis.get("drafts", [])]
    by_status = dict(db.execute(select(Conversation.status, func.count()).group_by(Conversation.status)).all())
    return {
        "conversations": sum(by_status.values()), "by_status": by_status, "agent_replies": replies,
        "draft_adoption_rate": round(from_drafts / replies, 3) if replies else None,
        "accepted_as_is": counts.get("accepted", 0), "edited": counts.get("edited", 0), "rejected": counts.get("rejected", 0),
        "avg_edit_ratio": round(avg_edit, 3) if avg_edit is not None else None,
        "avg_first_draft_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "drafts_generated": len(drafts), "drafts_blocked_by_guard": sum(1 for d in drafts if not d["validation"]["passed"]),
    }
