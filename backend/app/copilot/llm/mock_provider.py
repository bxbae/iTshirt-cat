"""Offline provider: deterministic answers built from the pipeline context.

It lets the app, the tests and CI run with no API key. Classification uses keyword rules and
drafts are assembled from the customer's own receipt facts and the retrieved policy sections, so
they are grounded by construction. Real writing quality comes from LLM_PROVIDER=anthropic.
"""
import re
from typing import Any

from ..facts import pick_claim

CATEGORY_KEYWORDS = [
    ("defect", ["불량", "파손", "찢어", "찢겨", "훼손", "오염", "잘못 왔", "잘못왔", "다른 책", "다른 상품", "누락", "구겨", "젖어"]),
    ("delivery", ["배송", "택배", "안 와", "안왔", "아직 도착", "언제 오", "송장", "못 받", "못받", "늦"]),
    ("cancel", ["주문 취소", "주문취소", "취소하고", "취소해", "취소 가능", "취소할"]),
    ("refund", ["환불", "반품", "교환", "돈 돌려", "돌려받"]),
    ("payment", ["결제", "이중", "두 번", "두번", "카드", "영수증"]),
    ("review", ["후기", "리뷰", "별점"]),
    ("account", ["적립금", "포인트", "쿠폰", "로그인", "회원", "비밀번호"]),
    ("product", ["재고", "품절", "재입고", "전자책", "추천", "할인", "정가"]),
]
CATEGORY_KO = {"refund": "환불·반품", "cancel": "주문 취소", "delivery": "배송", "defect": "불량·파손·오배송", "payment": "결제",
               "product": "상품", "review": "후기", "account": "적립금·계정", "other": "기타"}
ANGRY = re.compile(r"!!|어이없|화가|최악|소비자원|신고|사기|황당|말이 되|환장|열받")
FRUSTRATED = re.compile(r"아직도|계속|벌써|몇 번|몇번|답답|또 |여러 번|기다리")
HIGH = re.compile(r"소비자원|신고|이중|두 번 결제|두번 결제|법적")
INTERNAL_SENTENCE = re.compile(r"(상담원|약속|내부)")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+", text) if s.strip()]


def _customer_sentences(sources: list[dict], limit: int = 4) -> list[str]:
    out: list[str] = []
    for s in sources:
        for sent in _sentences(s["text"]):
            if not INTERNAL_SENTENCE.search(sent) and sent not in out:
                out.append(sent)
    return out[:limit]


def claim_sentences(claim: dict) -> list[str]:
    """What we can truthfully tell the customer about one claim, from the system's own decision."""
    status = claim["status"]
    block = [r["message"] for r in claim["reasons"] if r["level"] == "block"]
    if status == "rejected":
        why = " ".join(block) if block else "신청 사유가 처리 기준에 맞지 않았습니다."
        return [f"신청하신 건(#{claim['id']})은 아래 사유로 접수가 어렵습니다.", why, "자세한 기준은 환불·반품 규정 안내를 확인해 주세요."]
    if status == "needs_info":
        return ["불량·파손·오배송 여부를 확인할 수 있도록 상품 사진을 신청 내역에 첨부해 주세요.", "사진이 확인되면 이어서 안내해 드리겠습니다."]
    if status == "needs_review":
        return [f"신청하신 건(#{claim['id']})은 담당 상담원이 내용을 확인하고 있습니다.", "확인이 끝나면 결과를 안내해 드리겠습니다."]
    if status == "awaiting_return":
        out = [f"반품 상품이 물류센터에 입고되어 검수를 통과하면, 입고된 순서대로 {claim['expected_refund']:,}원이 환불됩니다."
               if claim["type"] != "exchange" else "반품 상품이 입고되어 검수를 통과하면, 입고된 순서대로 교환 상품을 발송합니다."]
        if claim.get("compensation"):
            out.append(f"검수가 끝나면 보상 적립금 {claim['compensation']:,}원이 함께 지급됩니다.")
        if claim.get("tracking"):
            out.append(f"반품 송장번호는 {claim['tracking']}입니다.")
        return out
    if status == "return_received":
        return ["반품 상품이 입고되어 처리 순서를 기다리고 있습니다.", "검수가 끝난 순서대로 처리됩니다."]
    if status == "completed":
        bits = []
        if claim.get("refund"):
            bits.append(f"환불 {claim['refund']:,}원")
        if claim.get("points_back"):
            bits.append(f"적립금 {claim['points_back']:,}원 반환")
        if claim.get("compensation"):
            bits.append(f"보상 적립금 {claim['compensation']:,}원")
        return [f"신청하신 건(#{claim['id']})은 처리가 끝나 {', '.join(bits) or '요청하신 내용'}이 반영되었습니다."]
    return []


class MockProvider:
    name = "mock"

    def complete_json(self, task: str, system: str, user: str, context: dict[str, Any]) -> dict[str, Any]:
        return getattr(self, f"_{task}")(context)

    def _analyze(self, ctx: dict) -> dict:
        text = ctx["text"]
        scores = {cat: sum(k in text for k in kws) for cat, kws in CATEGORY_KEYWORDS}
        best = max(scores, key=lambda c: scores[c])  # dict order = priority on ties
        category = best if scores[best] else "other"
        sentiment = "angry" if ANGRY.search(text) else "frustrated" if FRUSTRATED.search(text) else "calm"
        urgency = ("high" if sentiment == "angry" or HIGH.search(text)
                   else "medium" if category in {"refund", "cancel", "defect", "payment", "delivery"} else "low")
        first = _sentences(text)[0] if _sentences(text) else text
        return {
            "intent_ko": f"{CATEGORY_KO[category]} 문의 — {first[:50]}",
            "category": category,
            "sentiment": sentiment,
            "urgency": urgency,
            "search_query": text,
        }

    def _drafts(self, ctx: dict) -> dict:
        name, agent, brand = ctx["customer_name"], ctx["agent_name"], ctx["brand"]
        facts, sources = ctx.get("facts") or {}, ctx["sources"]
        claims = facts.get("claims") or []
        order = facts.get("order")
        body: list[str] = []
        ids: list[str] = []
        asked = next((m["text"] for m in reversed(ctx.get("history", [])) if m["role"] == "customer"), "")
        about = pick_claim(claims, asked)
        if about:
            body = claim_sentences(about)
            ids = list(about.get("policy_refs", []))[:2]
        elif order and ctx["category"] == "delivery":
            body = [f"주문번호 {order['order_no']}의 현재 상태는 '{order['status_ko']}'입니다."]
            if order.get("expected_delivery_at"):
                body.append(f"영수증 기준 배송 예정일은 {order['expected_delivery_at'][:10]}입니다.")
        if not body:
            body = _customer_sentences(sources)
            ids = [sources[0]["id"]] if sources else []
        if not body:
            body = ["문의하신 내용은 관련 부서에 확인한 뒤 다시 안내해 드리겠습니다."]
        if not ids and sources:
            ids = [sources[0]["id"]]
        hello = f"안녕하세요, {name} 고객님. {brand}입니다."
        sign = f"감사합니다.\n{agent} 드림"
        drafts = {
            "empathetic": "\n".join([hello, "문의 주셔서 감사하고, 불편을 드려 죄송합니다.", " ".join(body), sign]),
            "concise": "\n".join([hello, " ".join(body[:2]), sign]),
            "step_by_step": "\n".join([hello, "아래 순서로 안내해 드립니다."] + [f"{i}. {s}" for i, s in enumerate(body[:4], 1)] + [sign]),
        }
        return {"drafts": [{"style": s, "reply": r, "source_ids": ids} for s, r in drafts.items()]}

    def _summary(self, ctx: dict) -> dict:
        msgs = ctx["messages"]
        first = next((m for m in msgs if m["role"] == "customer"), None)
        agent_msgs = [m for m in msgs if m["role"] == "agent"]
        category = ctx.get("category") or "other"
        claim_status = ctx.get("claim_status")
        escalate = claim_status in ("needs_review", "needs_info")
        return {
            "summary_ko": f"{CATEGORY_KO.get(category, category)} 문의. 고객 메시지 {len(msgs) - len(agent_msgs)}건, 상담원 답변 {len(agent_msgs)}건."
                          + (f" 연결된 클레임 상태: {claim_status}." if claim_status else ""),
            "issue_ko": (first or {}).get("text", "")[:160],
            "actions_ko": [m["text"].splitlines()[1][:120] if len(m["text"].splitlines()) > 1 else m["text"][:120] for m in agent_msgs],
            "next_action_ko": "없음" if agent_msgs and not escalate else ("클레임 처리 결과 확인" if claim_status else "상담원 답변 필요"),
            "category": category,
            "resolved": bool(agent_msgs) and not escalate,
            "escalate": escalate,
            "escalate_reason_ko": "상담원의 클레임 판단이 필요합니다" if escalate else "",
            "tags": [CATEGORY_KO.get(category, category), "mock"],
        }
