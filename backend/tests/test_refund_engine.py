"""The decision engine against the receipt and policy, one rule at a time."""
from datetime import timedelta

import pytest

from app import claims, clock, queue
from app.models import Claim, Product, User
from conftest import NOW, make_order, make_product, make_user

R = "return"


def submit(db, user, order, **kw):
    args = dict(order_id=order.id, type=R, reason="change_of_mind", items=None, claimed_amount=None,
                unsealed=False, evidence_count=0, description="")
    args.update(kw)
    return claims.create_claim(db, user, **args)


def codes(claim):
    return {r["code"] for r in claim.decision["reasons"]}


def test_change_of_mind_within_window_is_approved_pending_return_with_fee(db):
    u = make_user(db)
    p = make_product(db, price=20_000)  # sale 18,000
    order = make_order(db, u, [(p, 1)], delivered_days_ago=3, shipping=2_500)
    c = submit(db, u, order)
    d = c.decision
    assert d["outcome"] == "approved_pending_return" and c.status == "awaiting_return"
    assert d["refund_cash"] == 18_000 - 3_000  # 반품배송비 차감, 최초 배송비는 환불 안 함
    assert "RETURN_FEE" in codes(c) and c.return_tracking


def test_change_of_mind_after_seven_days_is_rejected_with_rule_reference(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db), 1)], delivered_days_ago=8)
    c = submit(db, u, order)
    assert c.status == "rejected" and c.decision["outcome"] == "auto_rejected"
    assert "WINDOW_MIND_EXPIRED" in codes(c)
    assert "KB-REF-01#1" in c.decision["policy_refs"]


def test_unsealed_goods_cannot_be_returned_for_change_of_mind(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db, category="stationery"), 1)])
    c = submit(db, u, order, unsealed=True)
    assert "UNSEALED" in codes(c) and c.status == "rejected"


def test_ebook_and_custom_goods_are_not_refundable_for_change_of_mind(db):
    u = make_user(db)
    ebook = make_product(db, title="전자책", category="ebook", returnable=False)
    order = make_order(db, u, [(ebook, 1)])
    c = submit(db, u, order)
    assert "NON_RETURNABLE" in codes(c) and c.status == "rejected"


def test_defect_without_photo_asks_for_evidence_then_proceeds(db):
    u = make_user(db)
    p = make_product(db, price=20_000)
    order = make_order(db, u, [(p, 1)], delivered_days_ago=15, shipping=2_500)
    c = submit(db, u, order, reason="defect")
    assert c.status == "needs_info" and "NEED_EVIDENCE" in codes(c)
    claims.add_evidence(db, c, 1)
    assert c.status == "awaiting_return"
    d = c.decision
    assert d["refund_cash"] == 18_000 + 2_500  # 전체 반품: 판매자 책임이라 배송비도 환불
    assert d["compensation"]["amount"] == 2_000


def test_defect_window_is_thirty_days(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db), 1)], delivered_days_ago=31)
    c = submit(db, u, order, reason="damaged", evidence_count=2)
    assert "WINDOW_DEFECT_EXPIRED" in codes(c) and c.status == "rejected"


def test_item_not_on_receipt_and_foreign_order_are_rejected(db):
    u, other = make_user(db), make_user(db, "박서준")
    order = make_order(db, u, [(make_product(db), 1)])
    assert submit(db, u, order, items=[{"order_item_id": 99999, "qty": 1}]).status == "rejected"
    c = submit(db, other, order)
    assert "OWNER_MISMATCH" in codes(c) and c.status == "rejected"


def test_quantity_over_receipt_is_corrected_not_rejected(db):
    u = make_user(db)
    p = make_product(db, price=10_000)  # 9,000 each
    order = make_order(db, u, [(p, 2)], shipping=0)
    c = submit(db, u, order, items=[{"order_item_id": order.items[0].id, "qty": 5}])
    assert c.decision["lines"][0]["qty"] == 2 and "QTY_ADJUSTED" in codes(c)
    assert c.decision["abuse"]["score"] == 10  # remembered as a signal, not a verdict


def test_duplicate_claim_on_same_line_is_rejected(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db), 1)])
    assert submit(db, u, order).status == "awaiting_return"
    second = submit(db, u, order)
    assert "ALREADY_CLAIMED" in codes(second) and second.status == "rejected"


def test_claimed_amount_above_policy_is_adjusted_to_receipt(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db, price=20_000), 1)], shipping=0)  # 18,000
    c = submit(db, u, order, claimed_amount=18_000)  # customer forgot the 3,000 return fee
    assert "AMOUNT_ADJUSTED" in codes(c) and c.decision["payable"] == 15_000
    assert c.status == "awaiting_return"


def test_claimed_amount_above_receipt_goes_to_an_agent(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db, price=20_000), 1)], shipping=0)
    c = submit(db, u, order, claimed_amount=50_000)
    assert c.status == "needs_review" and "AMOUNT_EXCEEDS_RECEIPT" in codes(c)


def test_points_are_returned_as_points_and_cash_by_receipt(db):
    u = make_user(db, points=5_000)
    p = make_product(db, price=20_000)  # 18,000
    order = make_order(db, u, [(p, 1)], shipping=0, points_used=4_000)
    c = submit(db, u, order, reason="defect", evidence_count=1)
    d = c.decision
    assert d["refund_cash"] == 14_000 and d["points_back"] == 4_000


def test_cancel_before_shipping_pays_immediately_with_shipping_and_points(db):
    u = make_user(db)
    p = make_product(db, price=10_000, stock=3)  # 9,000
    order = make_order(db, u, [(p, 1)], status="preparing", shipping=2_500)
    c = submit(db, u, order, type="cancel")
    assert c.status == "completed" and c.refund_amount == 9_000 + 2_500
    assert order.status == "cancelled" and db.get(Product, p.id).stock == 4


def test_cancel_after_shipping_is_rejected_and_return_before_delivery_too(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db), 1)], status="shipped")
    assert "CANCEL_TOO_LATE" in codes(submit(db, u, order, type="cancel"))
    assert "NOT_DELIVERED_YET" in codes(submit(db, u, order))


def test_partial_cancel_that_drops_below_free_shipping_charges_shipping(db):
    u = make_user(db)
    a, b = make_product(db, price=10_000), make_product(db, price=10_000)  # 9,000 + 9,000 = 18,000 free ship
    order = make_order(db, u, [(a, 1), (b, 1)], status="paid", shipping=0)
    c = submit(db, u, order, type="cancel", items=[{"order_item_id": order.items[0].id, "qty": 1}])
    assert c.decision["refund_cash"] == 9_000 - 2_500 and "SHIPPING_FEE_LOST" in codes(c)


@pytest.mark.parametrize("late,expected", [(2, None), (3, 1_000), (6, 1_000), (7, 3_000)])
def test_late_delivery_compensation_tiers_come_from_the_receipt(db, late, expected):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db), 1)], status="shipped", delivered_days_ago=0)
    order.expected_delivery_at = NOW - timedelta(days=late)
    c = submit(db, u, order, type="compensation", reason="late_delivery")
    if expected is None:
        assert c.status == "rejected" and "NOT_LATE" in codes(c)
    else:
        assert c.status == "completed" and c.compensation_amount == expected
        assert db.get(User, u.id).points == expected
        again = submit(db, u, order, type="compensation", reason="late_delivery")
        assert "ALREADY_COMPENSATED" in codes(again)


def test_missing_item_needs_an_agent(db):
    u = make_user(db)
    order = make_order(db, u, [(make_product(db), 1)])
    c = submit(db, u, order, type="compensation", reason="missing_item")
    assert c.status == "needs_review" and "MISSING_ITEM_INVESTIGATE" in codes(c)


def test_over_limit_amount_needs_an_agent(db):
    u = make_user(db)
    big = make_product(db, price=150_000)
    order = make_order(db, u, [(big, 1)])
    c = submit(db, u, order, reason="defect", evidence_count=1)
    assert c.status == "needs_review" and "OVER_AUTO_LIMIT" in codes(c)


def test_frequent_claimer_is_never_auto_approved_and_reason_stays_internal(db):
    u = make_user(db)
    for _ in range(5):  # five earlier claims in the window, all rejected by the rules
        o = make_order(db, u, [(make_product(db), 1)], delivered_days_ago=20)
        submit(db, u, o)  # window expired -> rejected by the system
    order = make_order(db, u, [(make_product(db), 1)], status="preparing")
    c = submit(db, u, order, type="cancel")
    assert c.status == "needs_review" and "ABUSE_SUSPECTED" in codes(c)
    assert c.decision["abuse"]["score"] >= 60
    msg = next(r["message"] for r in c.decision["reasons"] if r["code"] == "ABUSE_SUSPECTED")
    assert "점검" not in msg and "의심" not in msg  # the customer-facing text does not accuse


def test_agent_override_is_logged_for_rule_tuning(db):
    from app.models import AuditLog
    u = make_user(db)
    order = make_order(db, u, [(make_product(db, price=20_000), 1)], shipping=0)
    c = submit(db, u, order, claimed_amount=50_000)
    claims.agent_decide(db, c, approve=True, note="영수증 재확인: 정상", agent="배상담")
    assert c.status == "awaiting_return" and c.manager_approved
    entry = db.query(AuditLog).filter_by(claim_id=c.id, action="agent_override").one()
    assert entry.detail["system_outcome"] == "needs_review" and entry.detail["agent_action"] == "approve"


# ------------------------------------------------------------------ compensation queue
def _received(db, user, product, *, at_hours_ago, reason="defect", type=R, inspection="ok", price_qty=1):
    order = make_order(db, user, [(product, price_qty)])
    c = submit(db, user, order, reason=reason, type=type, evidence_count=1)
    clock.freeze(NOW - timedelta(hours=at_hours_ago))
    claims.receive_return(db, c, inspection=inspection, note=None, agent="물류")
    clock.freeze(NOW)
    return c


def test_queue_is_ordered_by_warehouse_arrival_not_by_claim_time(db):
    u = make_user(db)
    p = make_product(db)
    first_filed = _received(db, u, p, at_hours_ago=1)   # filed first, arrived last
    second_filed = _received(db, u, p, at_hours_ago=5)  # filed second, arrived first
    q = queue.build_queue(db)
    assert [e["claim_id"] for e in q] == [second_filed.id, first_filed.id]
    assert [e["position"] for e in q] == [1, 2] and all(e["ready"] for e in q)
    results = queue.process(db, actor="system")
    assert [r["claim_id"] for r in results if r["result"] == "paid"] == [second_filed.id, first_filed.id]
    assert db.get(User, u.id).points == 4_000  # 2,000 x 2 보상 적립금
    assert first_filed.status == second_filed.status == "completed"


def test_queue_holds_pending_inspection_and_does_not_block_later_claims(db):
    u = make_user(db)
    p = make_product(db)
    waiting = _received(db, u, p, at_hours_ago=9, inspection="pending")
    ready = _received(db, u, p, at_hours_ago=2)
    res = {r["claim_id"]: r for r in queue.process(db, actor="system")}
    assert res[waiting.id]["result"] == "held" and res[waiting.id]["blockers"][0]["code"] == "NOT_INSPECTED"
    assert res[ready.id]["result"] == "paid"
    claims.set_inspection(db, waiting, inspection="ok", note=None, agent="물류")
    assert queue.process(db, actor="system")[0]["result"] == "paid"


def test_inspection_mismatch_goes_to_an_agent(db):
    u = make_user(db)
    c = _received(db, u, make_product(db), at_hours_ago=1, inspection="mismatch")
    assert c.status == "needs_review" and "검수 불일치" in c.hold_reason
    assert queue.build_queue(db)[0]["ready"] is False
    claims.agent_decide(db, c, approve=True, note="사진과 일치 확인", agent="배상담")
    assert c.status == "return_received" and c.inspection == "ok"
    assert queue.process(db, actor="system")[0]["result"] == "paid"


def test_exchange_stock_goes_to_the_earliest_arrival(db):
    u = make_user(db)
    p = make_product(db, stock=1)
    late = _received(db, u, p, at_hours_ago=1, type="exchange")
    early = _received(db, u, p, at_hours_ago=6, type="exchange")
    res = {r["claim_id"]: r for r in queue.process(db, actor="system")}
    assert res[early.id]["result"] == "paid" and res[late.id]["result"] == "held"
    assert res[late.id]["blockers"][0]["code"] == "OUT_OF_STOCK"
    assert early.decision["exchange_shipment"]["tracking"].startswith("EX")
    assert db.get(Product, p.id).stock == 0


def test_manager_approval_releases_over_limit_claim_into_the_queue(db):
    u = make_user(db)
    big = make_product(db, price=150_000)
    order = make_order(db, u, [(big, 1)])
    c = submit(db, u, order, reason="defect", evidence_count=1)
    assert c.status == "needs_review"
    claims.agent_decide(db, c, approve=True, note="고가 상품 확인", agent="배상담")
    clock.freeze(NOW - timedelta(hours=1))
    claims.receive_return(db, c, inspection="ok", note=None, agent="물류")
    clock.freeze(NOW)
    assert queue.process(db, actor="system")[0]["result"] == "paid"
    assert c.refund_amount == 135_000


def test_limit_parameter_pays_only_the_first_n_in_line(db):
    u = make_user(db)
    p = make_product(db)
    a = _received(db, u, p, at_hours_ago=3)
    b = _received(db, u, p, at_hours_ago=2)
    res = queue.process(db, actor="system", limit=1)
    assert [r["result"] for r in res] == ["paid", "skipped"]
    assert a.status == "completed" and b.status == "return_received"


def test_return_with_a_delivery_reason_cannot_skip_the_return_rules(db):
    u = make_user(db)
    old = make_order(db, u, [(make_product(db), 1)], delivered_days_ago=20)
    c = submit(db, u, old, reason="late_delivery")
    assert c.status == "rejected" and "INVALID_REASON" in codes(c)
    c2 = submit(db, u, make_order(db, u, [(make_product(db), 1)]), type="exchange", reason="missing_item")
    assert c2.status == "rejected" and "INVALID_REASON" in codes(c2)
