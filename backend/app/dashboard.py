"""Aggregates for the agent dashboard: inquiry trend, claim automation, queue, guard findings."""
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import clock, queue
from .config import settings
from .models import AuditLog, Claim, Conversation, Review

URGENCY_RANK = {"high": 0, "medium": 1, "low": 2, None: 3}


def _d(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def build_dashboard(db: Session, days: int = 14) -> dict:
    tz = ZoneInfo(settings.timezone)
    now = clock.now()
    today = now.astimezone(tz).date()
    start = today - timedelta(days=days - 1)
    keys = [start + timedelta(days=i) for i in range(days)]
    daily = {k: {"date": k.isoformat(), "inquiries": 0, "claims": 0, "auto": 0, "agent": 0, "paid": 0} for k in keys}

    convs = db.scalars(select(Conversation).options(selectinload(Conversation.messages))).all()
    claims = db.scalars(select(Claim)).all()
    findings: Counter = Counter()
    period_convs = []
    for c in convs:
        d = _d(c.created_at, tz)
        if start <= d <= today:
            daily[d]["inquiries"] += 1
            period_convs.append(c)
        for m in c.messages:
            if m.analysis and _d(m.created_at, tz) >= start:
                for dr in m.analysis.get("drafts", []):
                    findings.update(f["code"] for f in dr["validation"]["findings"])

    reasons: Counter = Counter()
    auto = agent = rejected = 0
    paid_cash = paid_points = 0
    for c in claims:
        d = _d(c.created_at, tz)
        if not (start <= d <= today):
            continue
        daily[d]["claims"] += 1
        # "auto" = settled by the rules alone (never needed an agent)
        needed_agent = c.decided_by != "system" or c.decision.get("outcome") == "needs_review"
        if needed_agent:
            daily[d]["agent"] += 1
            agent += 1
        else:
            daily[d]["auto"] += 1
            auto += 1
        if c.status == "rejected":
            rejected += 1
        if c.processed_at and start <= _d(c.processed_at, tz) <= today:
            daily[_d(c.processed_at, tz)]["paid"] += c.refund_amount + c.compensation_amount
            paid_cash += c.refund_amount
            paid_points += c.compensation_amount + c.points_returned
        reasons.update(r["code"] for r in c.decision.get("reasons", []) if r["level"] in ("block", "review", "warn"))

    q = queue.build_queue(db)
    open_waiting = [c for c in convs if c.status == "open" and c.messages and c.messages[-1].role == "customer"]
    waiting_sorted = sorted(open_waiting, key=lambda c: (URGENCY_RANK.get(c.urgency, 3), c.messages[-1].created_at))
    overrides = db.scalars(select(AuditLog).where(AuditLog.action.in_(["agent_override", "agent_confirmed"]))).all()
    decided_by_agent = len(overrides)
    reverted = sum(1 for o in overrides if o.action == "agent_override")
    total = auto + agent
    return {
        "days": days, "timezone": settings.timezone,
        "daily": list(daily.values()),
        "totals": {
            "inquiries": len(period_convs), "open_waiting": len(open_waiting),
            "high_waiting": sum(1 for c in open_waiting if c.urgency == "high"),
            "claims": total, "auto_rate": round(auto / total, 3) if total else None,
            "claims_rejected": rejected, "needs_review": sum(1 for c in claims if c.status == "needs_review"),
            "awaiting_return": sum(1 for c in claims if c.status == "awaiting_return"),
            "queue_waiting": len(q), "queue_ready": sum(1 for e in q if e["ready"]),
            "paid_cash": paid_cash, "paid_points": paid_points,
            "agent_reviews": decided_by_agent, "agent_overrides": reverted,
            "flagged_reviews": sum(1 for r in db.scalars(select(Review)).all() if r.status == "flagged"),
        },
        "by_category": dict(Counter(c.category or "other" for c in period_convs).most_common()),
        "claim_reasons": dict(reasons.most_common(8)),
        "guard_findings": dict(findings.most_common(6)),
        "queue": q[:5],
        "inquiry_queue": [{
            "id": c.id, "customer_name": c.customer_name, "subject": c.subject, "category": c.category, "urgency": c.urgency,
            "sentiment": c.sentiment, "preview": c.messages[-1].text[:90],
            "waiting_minutes": max(0, int((now - c.messages[-1].created_at).total_seconds() // 60)),
        } for c in waiting_sorted[:5]],
    }
