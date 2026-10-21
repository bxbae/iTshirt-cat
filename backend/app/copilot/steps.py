"""Pipeline steps. Each one builds prompts, calls the provider and normalizes the JSON it gets back."""
import json
import time
from typing import Any

from ..config import settings
from . import prompts
from .llm.base import LLMProvider
from .pii import mask_pii
from .retrieve import get_retriever
from .validate import check_reply

STYLES = ["empathetic", "concise", "step_by_step"]


class Timer:
    def __init__(self):
        self.ms: dict[str, int] = {}

    def run(self, name: str, fn, *args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            self.ms[name] = round((time.perf_counter() - start) * 1000)


def _pick(value: Any, allowed: list[str], default: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in allowed else default


def analyze(llm: LLMProvider, text: str) -> dict:
    masked, pii_types = mask_pii(text)
    out = llm.complete_json("analyze", prompts.ANALYZE_SYSTEM, f"MESSAGE:\n{masked}", {"text": masked})
    return {
        "intent_ko": out.get("intent_ko") or "",
        "category": _pick(out.get("category"), prompts.CATEGORIES, "other"),
        "sentiment": _pick(out.get("sentiment"), ["calm", "frustrated", "angry"], "calm"),
        "urgency": _pick(out.get("urgency"), ["low", "medium", "high"], "medium"),
        "search_query": out.get("search_query") or masked,
        "pii_masked": pii_types,
    }


def retrieve(query: str, original: str, category: str, policy_refs: list[str] | None = None) -> list[dict]:
    """Search with the rewritten query and the original text, then add the sections the system's own
    decision cited (so a drafted answer can quote the exact rule that applied to this customer)."""
    retriever = get_retriever()
    hint = {"cancel": "cancel", "refund": "refund", "defect": "refund", "delivery": "delivery",
            "payment": "payment", "review": "review", "product": "product"}.get(category)
    merged: dict[str, dict] = {}
    for q in {query, original}:
        for hit in retriever.search(q, top_k=settings.top_k, category_hint=hint):
            if hit["id"] not in merged or hit["score"] > merged[hit["id"]]["score"]:
                merged[hit["id"]] = hit
    hits = sorted(merged.values(), key=lambda h: -h["score"])[: settings.top_k]
    have = {h["id"] for h in hits}
    by_id = {c.id: c for c in retriever.chunks}
    for ref in policy_refs or []:
        if ref not in have and ref in by_id:
            c = by_id[ref]
            hits.insert(0, {"id": c.id, "doc_id": c.doc_id, "category": c.category, "title": c.title,
                            "section": c.section, "text": c.text, "score": 0.0, "from_decision": True})
            have.add(ref)
    return hits


def _history_block(history: list[dict]) -> str:
    return "\n".join(
        f"{'CUSTOMER' if m['role'] == 'customer' else 'AGENT'}: {mask_pii(m['text'])[0]}" for m in history[-8:]
    )


def _sources_block(sources: list[dict]) -> str:
    if not sources:
        return "(no matching sources)"
    return "\n".join(f"[{s['id']}] {s['title']} / {s['section']}: {s['text']}" for s in sources)


def drafts(llm: LLMProvider, *, customer_name: str, category: str, sentiment: str, history: list[dict],
           sources: list[dict], facts: dict | None) -> list[dict]:
    fmt = {"brand": settings.brand_name, "agent_name": settings.agent_name, "customer_name": customer_name,
           "category": category, "sentiment": sentiment}
    out = llm.complete_json(
        "drafts",
        prompts.DRAFTS_SYSTEM.format(**fmt),
        prompts.DRAFTS_USER.format(history=_history_block(history), sources=_sources_block(sources),
                                   facts=json.dumps(facts, ensure_ascii=False, indent=1) if facts else "(no order linked)", **fmt),
        {**fmt, "sources": sources, "history": history, "facts": facts},
    )
    results = []
    for i, d in enumerate((out.get("drafts") or [])[:3]):
        reply = str(d.get("reply") or "").strip()
        if not reply:
            continue
        cited = [str(c) for c in (d.get("source_ids") or [])]
        results.append({
            "style": _pick(d.get("style"), STYLES, STYLES[i % 3]),
            "reply": reply,
            "source_ids": cited,
            "validation": check_reply(reply, sources, facts, cited_ids=cited),
        })
    return results


def summarize(llm: LLMProvider, *, messages: list[dict], category: str | None, claim_status: str | None) -> dict:
    transcript = "\n".join(
        f"{'CUSTOMER' if m['role'] == 'customer' else 'AGENT'}: {mask_pii(m['text'])[0]}" for m in messages
    )
    out = llm.complete_json("summary", prompts.SUMMARY_SYSTEM, f"TRANSCRIPT:\n{transcript}",
                            {"messages": messages, "category": category, "claim_status": claim_status})
    return {
        "summary_ko": out.get("summary_ko") or "",
        "issue_ko": out.get("issue_ko") or "",
        "actions_ko": [str(a) for a in (out.get("actions_ko") or [])],
        "next_action_ko": out.get("next_action_ko") or "",
        "category": _pick(out.get("category"), prompts.CATEGORIES, category or "other"),
        "resolved": bool(out.get("resolved")),
        "escalate": bool(out.get("escalate")),
        "escalate_reason_ko": out.get("escalate_reason_ko") or "",
        "tags": [str(t) for t in (out.get("tags") or [])][:5],
    }
