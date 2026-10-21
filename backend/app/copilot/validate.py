"""Rule-based guards run on every reply before an agent can send it.

The LLM writes; these checks decide whether the result is safe to send. Each finding is
{code, level, message}. level "error" blocks sending, "warning" asks the agent to look.
Grounding sources: the retrieved policy sections plus the customer's own receipt and claim decision.
"""
import re

from .pii import find_pii
from .retrieve import get_retriever

PROMISE_OBJECT = re.compile(r"(환불|보상|적립금|교환|재발송|재배송|지급|배상|무상|취소)")
PROMISE_VERB = re.compile(
    r"(드리겠습니다|드립니다|드릴게요|드릴 수 있습니다|됩니다|돼요|가능합니다|가능해요|보내드리|입금해|지급해|지급됩니다|처리해 드|처리됩니다|완료되었습니다|완료됐습니다)"
)
NEGATION = re.compile(r"(불가|어렵|없습니다|않습니다|않아요|안 됩니다|안됩니다|할 수 없|드릴 수 없|되지 않|제외|아닙니다|못합니다|어려운)")
CONDITION = re.compile(r"(경우|이내|이상|이후|이면|하면|되면|후에|한해|확인 후|확인되면|검수|입고)")
MONEY_OBJECT = re.compile(r"(환불|보상|적립금|교환|재발송|재배송|배상|지급)")
ABSOLUTE = re.compile(r"(무조건|반드시 환불|100%|즉시 환불|바로 환불|확실히|보장합니다|틀림없이|무제한)")
INTERNAL = re.compile(r"(어뷰징|블랙리스트|악성\s*고객|의심\s*고객|내부\s*점검|점검\s*대상|위험\s*점수|부정\s*수급|abuse)", re.I)
REVIEW_BARGAIN = re.compile(r"후기.{0,12}(삭제|수정|내려).{0,24}(보상|적립|환불|쿠폰)|(보상|적립|환불|쿠폰).{0,24}후기.{0,12}(삭제|수정|내려)")
RESTRICTION = re.compile(r"(불가|않습니다|없습니다|이내|이상|미만|경우|한해|제외|차감)")
NUMBER = re.compile(r"\d[\d,]*")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", text) if s.strip()]


def _rejected_claim_named(sentence: str, rejected: list[dict]) -> dict | None:
    """A rejected claim the sentence points at: by its number, its item, or the amount of its item."""
    amounts = numbers_in(sentence)
    for c in rejected:
        if f"#{c['id']}" in sentence:
            return c
        for ln in c.get("lines", []):
            if (len(ln["title"]) >= 4 and ln["title"][:4] in sentence) or str(ln["gross"]) in amounts:
                return c
    return None


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "").strip() for n in NUMBER.findall(text) if n.replace(",", "").strip()}


def facts_text(facts: dict | None) -> str:
    """Flatten the customer-visible facts so amounts in them count as grounded."""
    if not facts:
        return ""
    parts: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif v is not None:
            parts.append(str(v))

    walk(facts)
    return " ".join(parts)


def check_reply(reply: str, sources: list[dict], facts: dict | None = None, cited_ids: list[str] | None = None) -> dict:
    """Validate a customer-facing reply.

    sources:   KB chunks retrieved for this conversation (the only allowed policy grounding)
    facts:     the customer's receipt and claim decision (customer-visible fields only)
    cited_ids: chunk ids the draft claims to use
    """
    findings: list[dict] = []
    doc_ids = {s.get("doc_id") or s["id"].split("#")[0] for s in sources}
    siblings = [c.text for c in get_retriever().chunks if c.doc_id in doc_ids]
    policy_text = " ".join([s["text"] for s in sources] + siblings)
    fact_text = facts_text(facts)
    grounded_numbers = numbers_in(policy_text) | numbers_in(fact_text)
    retrieved_ids = {s["id"] for s in sources}
    claims = (facts or {}).get("claims") or []
    rejected = [c for c in claims if c.get("status") == "rejected"]
    live = [c for c in claims if c.get("status") not in ("rejected", "withdrawn")]

    # 1. Personal data must never go back out in a reply.
    for item in find_pii(reply):
        findings.append({"code": "pii", "level": "error", "message": f"답변에 개인정보({item['type']})가 포함되어 있습니다."})

    # 2. Internal review criteria and review bargaining must never reach the customer.
    if m := INTERNAL.search(reply):
        findings.append({"code": "internal_info_leak", "level": "error", "message": f"내부 점검 정보(\"{m.group()}\")는 고객에게 알릴 수 없습니다."})
    if REVIEW_BARGAIN.search(reply):
        findings.append({"code": "review_bargaining", "level": "error", "message": "후기 삭제·수정을 조건으로 한 보상 제안은 할 수 없습니다."})

    # 3. Promises of money or goods need support in policy or in the system's own decision.
    for sentence in _sentences(reply):
        if not (PROMISE_OBJECT.search(sentence) and PROMISE_VERB.search(sentence)) or NEGATION.search(sentence):
            continue
        if not sources and not facts:
            findings.append({"code": "unsupported_promise", "level": "error", "message": f"정책 근거 없는 약속일 수 있습니다: \"{sentence[:90]}\""})
            continue
        if claims and MONEY_OBJECT.search(sentence):
            about = _rejected_claim_named(sentence, rejected)
            if rejected and (not live or about):
                c = about or rejected[0]
                findings.append({"code": "contradicts_decision", "level": "error",
                                 "message": f"시스템이 거절한 신청(#{c['id']})에 환불·보상을 약속했습니다: \"{sentence[:80]}\""})
                continue
            if rejected and live:
                findings.append({"code": "ambiguous_claim", "level": "warning",
                                 "message": f"이 주문에는 거절된 신청(#{rejected[0]['id']})도 있습니다. 어떤 신청에 대한 안내인지 분명히 쓰세요."})
            if live and all(c.get("status") in ("needs_review", "needs_info") for c in live) and not CONDITION.search(sentence):
                findings.append({"code": "premature_promise", "level": "error",
                                 "message": f"아직 확인 중인 신청(#{live[0]['id']})에 결과를 먼저 약속했습니다: \"{sentence[:80]}\""})
                continue
        extra = numbers_in(sentence) - grounded_numbers
        if extra:
            findings.append({"code": "unsupported_promise", "level": "error",
                             "message": f"정책·영수증에 없는 수치가 포함된 약속입니다 ({', '.join(sorted(extra))}): \"{sentence[:90]}\""})
            continue
        restricted = [s for s in _sentences(policy_text) if RESTRICTION.search(s) and PROMISE_OBJECT.search(s)]
        if restricted and not CONDITION.search(sentence):
            findings.append({"code": "conditional_policy", "level": "warning",
                             "message": f"조건이 있는 정책입니다. 고객이 조건을 충족하는지 안내에 포함하세요 — \"{restricted[0][:80]}\""})

    # 4. Over-confident wording.
    for m in ABSOLUTE.finditer(reply):
        findings.append({"code": "absolute_wording", "level": "warning", "message": f"단정적 표현 \"{m.group()}\" — 처리 결과·기간을 보장하지 않도록 수정하세요."})

    # 5. Citations must point at chunks that were actually retrieved.
    for cid in cited_ids or []:
        if cid not in retrieved_ids:
            findings.append({"code": "ungrounded_citation", "level": "error", "message": f"검색되지 않은 근거 {cid}를 인용했습니다."})

    # 6. Format.
    if not re.match(r"^\s*(안녕하세요|고객님)", reply):
        findings.append({"code": "greeting", "level": "warning", "message": "첫 줄에 인사말(안녕하세요)이 없습니다."})
    if not re.search(r"(감사합니다|감사드립니다|드림|올림)[.!\s]*(\S+\s*)*$", reply[-120:]):
        findings.append({"code": "closing", "level": "warning", "message": "맺음 인사(감사합니다)가 없습니다."})
    if len(reply) > 900:
        findings.append({"code": "length", "level": "warning", "message": "답변이 깁니다(900자 초과). 핵심만 줄이세요."})

    return {"passed": not any(f["level"] == "error" for f in findings), "findings": findings}
