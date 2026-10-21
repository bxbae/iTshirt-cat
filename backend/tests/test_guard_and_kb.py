import re

import pytest

from app.config import settings
from app.copilot.pii import mask_pii
from app.copilot.retrieve import get_retriever
from app.copilot.validate import check_reply
from app.rules import policy

FACTS = {"order": {"paid_amount": 18_000}, "claims": [
    {"id": 3, "status": "awaiting_return", "expected_refund": 15_000, "compensation": 2_000, "reasons": []}]}
SRC = [{"id": "KB-REF-01#2", "doc_id": "KB-REF-01", "text": "반품 상품이 입고되어 검수를 통과하면 환불 또는 교환과 함께 보상 적립금 2,000원이 지급됩니다."}]
HELLO, BYE = "안녕하세요, 김민지 고객님.\n", "\n감사합니다."


def codes(reply, facts=FACTS, sources=SRC, **kw):
    return {f["code"] for f in check_reply(HELLO + reply + BYE, sources, facts, **kw)["findings"]}


def test_grounded_conditional_promise_passes():
    r = check_reply(HELLO + "반품 상품이 입고되어 검수를 통과하면 입고된 순서대로 15,000원이 환불됩니다." + BYE, SRC, FACTS)
    assert r["passed"] and not r["findings"]


def test_amount_not_in_policy_or_receipt_is_blocked():
    assert "unsupported_promise" in codes("검수를 통과하면 50,000원을 환불해 드리겠습니다.")


def test_internal_review_criteria_never_leave_the_building():
    assert "internal_info_leak" in codes("내부 점검 대상이라 확인이 오래 걸립니다.")
    assert "internal_info_leak" in codes("어뷰징 의심 고객으로 분류되어 있습니다.")


def test_bargaining_over_a_review_is_blocked():
    assert "review_bargaining" in codes("후기를 삭제해 주시면 적립금 1,000원을 드리겠습니다.")


def test_promising_before_the_agent_has_decided_is_blocked():
    facts = {"claims": [{"id": 9, "status": "needs_review", "reasons": []}]}
    assert "premature_promise" in codes("확인할 것도 없이 환불해 드리겠습니다.", facts=facts)
    assert "premature_promise" not in codes("상담원이 확인한 뒤 결과를 안내해 드리겠습니다.", facts=facts)


def test_rejected_claim_cannot_be_promised_a_refund_but_can_be_explained():
    facts = {"claims": [{"id": 4, "status": "rejected", "reasons": []}]}
    assert "contradicts_decision" in codes("환불해 드리겠습니다.", facts=facts)
    assert "contradicts_decision" not in codes("단순변심 반품 기간이 지나 환불이 불가합니다.", facts=facts)


def test_pii_and_absolute_wording_and_format():
    r = check_reply("010-1234-5678로 전화드리겠습니다. 무조건 바로 환불", SRC, FACTS)
    found = {f["code"] for f in r["findings"]}
    assert {"pii", "absolute_wording", "greeting", "closing"} <= found and not r["passed"]


def test_citing_a_section_that_was_not_retrieved_is_blocked():
    assert "ungrounded_citation" in codes("안내드립니다.", cited_ids=["KB-REF-01#9"])


def test_phone_numbers_without_dashes_are_masked():
    masked, types = mask_pii("연락처 01012345678 입니다")
    assert masked == "연락처 [PHONE] 입니다" and types == ["phone"]


@pytest.mark.parametrize("query,expected", [
    ("책 표지가 찢어진 채로 왔어요", "KB-REF-01#2"),
    ("전자책 환불되나요", "KB-REF-01#3"),
    ("카드가 두 번 결제됐어요", "KB-PAY-01#1"),
    ("후기 삭제해주세요", "KB-REV-01#2"),
    ("반품하면 입고 순서대로 처리되나요", "KB-CMP-01#2"),
    ("출고된 주문 취소할 수 있나요", "KB-CAN-01#2"),
])
def test_retrieval_finds_the_policy_section(query, expected):
    assert expected in [h["id"] for h in get_retriever().search(query, top_k=3)]


def test_every_rule_reference_points_at_a_real_kb_section():
    ids = {c.id for c in get_retriever().chunks}
    assert set(policy.RULE_REFS.values()) <= ids


def test_kb_states_the_same_numbers_as_the_rule_engine():
    kb = " ".join(c.text for c in get_retriever().chunks)
    for n in (policy.RETURN_FEE, policy.SHIPPING_FEE, policy.FREE_SHIPPING_MIN, policy.DEFECT_COMPENSATION, policy.AUTO_LIMIT):
        assert f"{n:,}원" in kb, n
    for days in (policy.MIND_WINDOW_DAYS, policy.DEFECT_WINDOW_DAYS):
        assert f"{days}일" in kb, days
    for days, amount in policy.LATE_TIERS:
        assert re.search(rf"{days}일 이상 늦으면 적립금 {amount:,}원", kb), (days, amount)
    assert settings.kb_dir.exists()


MIXED = {"claims": [
    {"id": 5, "status": "return_received", "reasons": [], "lines": [{"title": "개발자 티셔츠 고양이 로고", "qty": 1, "gross": 25_000}]},
    {"id": 4, "status": "rejected", "reasons": [], "lines": [{"title": "이름 새김 머그컵 (주문제작)", "qty": 1, "gross": 16_000}]},
]}


def test_one_rejected_claim_among_live_ones_still_blocks_a_promise_about_it():
    # by item, by amount, by claim number
    assert "contradicts_decision" in codes("이름 새김 머그컵은 검수 후 환불해 드리겠습니다.", facts=MIXED)
    assert "contradicts_decision" in codes("검수가 끝나면 16,000원이 환불됩니다.", facts=MIXED)
    assert "contradicts_decision" in codes("신청 #4는 검수 후 환불됩니다.", facts=MIXED)


def test_promise_about_the_live_claim_is_allowed_but_flagged_as_ambiguous():
    found = codes("티셔츠는 검수가 끝나면 교환 상품을 보내드리겠습니다.", facts=MIXED)
    assert "contradicts_decision" not in found and "ambiguous_claim" in found
    r = check_reply(HELLO + "티셔츠는 검수가 끝나면 교환해 드리겠습니다." + BYE, SRC, MIXED)
    assert r["passed"]  # a warning, not a block
