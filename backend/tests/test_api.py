"""End to end through the HTTP API: shopping, receipts, reviews, claims, inquiries and the agent console."""
from datetime import timedelta

from fastapi.testclient import TestClient

from app import clock
from app.copilot.llm.mock_provider import claim_sentences
from app.main import app
from conftest import NOW, make_order, make_product, make_user


def hdr(user):
    return {"X-User-Id": str(user.id)}


def test_checkout_math_stock_points_and_receipt(db):
    u = make_user(db, points=3_000)
    a = make_product(db, "책 A", price=10_000, stock=5)   # 9,000
    b = make_product(db, "문구 B", price=4_000, category="stationery", stock=2, discount=0.0)  # 4,000
    db.commit()
    with TestClient(app) as c:
        priced = c.post("/api/cart/price", json=[{"product_id": a.id, "qty": 1}, {"product_id": b.id, "qty": 1}]).json()
        assert priced["items_total"] == 13_000 and priced["shipping_fee"] == 2_500 and priced["free_shipping_gap"] == 2_000
        r = c.post("/api/orders", headers=hdr(u), json={
            "lines": [{"product_id": a.id, "qty": 1}, {"product_id": b.id, "qty": 1}], "points_used": 2_000,
            "receiver": "김민지", "address": "서울"})
        assert r.status_code == 201
        o = r.json()
        assert o["paid_amount"] == 13_000 + 2_500 - 2_000 and o["status"] == "paid"
        assert sum(i["paid_amount"] for i in o["items"]) + o["shipping_fee"] == o["paid_amount"]
        assert sum(i["points_share"] for i in o["items"]) == 2_000
        assert c.get("/api/me", headers=hdr(u)).json()["points"] == 1_000
        assert c.get(f"/api/products/{b.id}").json()["stock"] == 1
        too_many = c.post("/api/orders", headers=hdr(u), json={"lines": [{"product_id": b.id, "qty": 5}], "receiver": "a", "address": "b"})
        assert too_many.status_code == 422 and "재고" in too_many.json()["detail"]
        too_many_points = c.post("/api/orders", headers=hdr(u), json={"lines": [{"product_id": a.id, "qty": 1}], "points_used": 9_999, "receiver": "a", "address": "b"})
        assert too_many_points.status_code == 422


def test_orders_are_private_to_their_owner(db):
    u, other = make_user(db), make_user(db, "박서준")
    o = make_order(db, u, [(make_product(db), 1)])
    db.commit()
    with TestClient(app) as c:
        assert c.get(f"/api/orders/{o.id}", headers=hdr(u)).status_code == 200
        assert c.get(f"/api/orders/{o.id}", headers=hdr(other)).status_code == 404
        assert c.get(f"/api/orders/{o.id}").status_code == 401
        assert c.post("/api/claims", headers=hdr(other), json={"order_id": o.id, "type": "return", "reason": "change_of_mind"}).status_code == 404


def test_claim_preview_saves_nothing_and_submit_matches_it(db):
    u = make_user(db)
    o = make_order(db, u, [(make_product(db, price=20_000), 1)], shipping=0)
    db.commit()
    body = {"order_id": o.id, "type": "return", "reason": "change_of_mind", "unsealed": False}
    with TestClient(app) as c:
        preview = c.post("/api/claims/preview", headers=hdr(u), json=body).json()
        assert c.get("/api/claims", headers=hdr(u)).json() == []
        assert "abuse" not in preview and preview["outcome"] == "approved_pending_return"
        saved = c.post("/api/claims", headers=hdr(u), json=body).json()
        assert saved["payable"] == preview["payable"] == 15_000 and saved["status"] == "awaiting_return"
        again = c.post("/api/claims", headers=hdr(u), json=body).json()
        assert again["status"] == "rejected" and any(r["code"] == "ALREADY_CLAIMED" for r in again["reasons"])


def test_customers_never_see_the_abuse_score(db):
    u = make_user(db)
    for _ in range(5):
        o = make_order(db, u, [(make_product(db), 1)], delivered_days_ago=20)
        from app import claims
        claims.create_claim(db, u, order_id=o.id, type="return", reason="change_of_mind", items=None, claimed_amount=None,
                            unsealed=False, evidence_count=0, description="")
    o = make_order(db, u, [(make_product(db), 1)], status="preparing")
    db.commit()
    with TestClient(app) as c:
        mine = c.post("/api/claims", headers=hdr(u), json={"order_id": o.id, "type": "cancel", "reason": "change_of_mind"}).json()
        assert mine["status"] == "needs_review"
        text = str(mine) + str(c.get("/api/claims", headers=hdr(u)).json())
        assert "abuse" not in text and "ABUSE" not in text.replace("ABUSE_SUSPECTED", "") and "점검" not in text
        agent_view = c.get(f"/api/admin/claims/{mine['id']}").json()
        assert agent_view["abuse"]["score"] >= 60 and agent_view["audit"]


def test_evidence_flow_over_the_api(db):
    u = make_user(db)
    o = make_order(db, u, [(make_product(db), 1)])
    db.commit()
    with TestClient(app) as c:
        cl = c.post("/api/claims", headers=hdr(u), json={"order_id": o.id, "type": "return", "reason": "damaged"}).json()
        assert cl["status"] == "needs_info"
        done = c.post(f"/api/claims/{cl['id']}/evidence", headers=hdr(u), json={"count": 2}).json()
        assert done["status"] == "awaiting_return" and done["compensation"] == 2_000


def test_review_rules_and_moderation(db):
    u, other = make_user(db), make_user(db, "박서준")
    p = make_product(db)
    delivered = make_order(db, u, [(p, 1)])
    shipped = make_order(db, u, [(p, 1)], status="shipped")
    db.commit()
    with TestClient(app) as c:
        def post(user, item, **kw):
            return c.post("/api/reviews", headers=hdr(user), json={"order_item_id": item.id, "rating": 5, "title": "t", "body": "정말 좋았어요 추천합니다", **kw})
        assert post(other, delivered.items[0]).status_code == 422          # not the buyer
        assert post(u, shipped.items[0]).status_code == 422                # not delivered yet
        ok = post(u, delivered.items[0])
        assert ok.status_code == 201 and ok.json()["verified"] and not ok.json()["held"]
        assert post(u, delivered.items[0]).status_code == 422              # once per item
        detail = c.get(f"/api/products/{p.id}").json()
        assert detail["review_count"] == 1 and detail["reviews"][0]["user"] == "김**"  # name is masked in public

    o2 = make_order(db, u, [(p, 1)])
    db.commit()
    with TestClient(app) as c:
        held = c.post("/api/reviews", headers=hdr(u), json={"order_item_id": o2.items[0].id, "rating": 5, "title": "굿",
                      "body": "더 싸게 사려면 카톡 오픈채팅으로 연락주세요 010-1234-5678"}).json()
        assert held["held"]
        assert c.get(f"/api/products/{p.id}").json()["review_count"] == 1      # still hidden from the public
        queue = c.get("/api/admin/reviews").json()
        assert queue[0]["status"] == "flagged" and {f["code"] for f in queue[0]["flags"]} >= {"PERSONAL_INFO", "LINK_OR_CONTACT"}
        c.post(f"/api/admin/reviews/{held['id']}/status", json={"status": "visible"})
        assert c.get(f"/api/products/{p.id}").json()["review_count"] == 2


def test_low_rating_defect_review_is_flagged_for_outreach_but_stays_public(db):
    u = make_user(db)
    p = make_product(db)
    o = make_order(db, u, [(p, 1)])
    db.commit()
    with TestClient(app) as c:
        r = c.post("/api/reviews", headers=hdr(u), json={"order_item_id": o.items[0].id, "rating": 1, "title": "별로",
                   "body": "표지가 찢어진 불량품이 왔어요. 환불 받고 싶습니다."}).json()
        assert not r["held"]
        top = c.get("/api/admin/reviews").json()[0]
        assert any(f["code"] == "CS_FOLLOW_UP" for f in top["flags"])


def test_demo_logistics_moves_an_order_and_late_delivery_is_paid(db):
    u = make_user(db)
    p = make_product(db)
    db.commit()
    with TestClient(app) as c:
        o = c.post("/api/orders", headers=hdr(u), json={"lines": [{"product_id": p.id, "qty": 1}], "receiver": "a", "address": "b"}).json()
        for _ in range(2):
            o = c.post(f"/api/orders/{o['id']}/advance", headers=hdr(u), json={}).json()
        assert o["status"] == "shipped"
        late = c.post(f"/api/orders/{o['id']}/advance", headers=hdr(u), json={"late_days": 8}).json()
        assert late["status"] == "delivered" and late["late_days"] >= 8
        claim = c.post("/api/claims", headers=hdr(u), json={"order_id": o["id"], "type": "compensation", "reason": "late_delivery"}).json()
        assert claim["status"] == "completed" and claim["compensation_paid"] == 3_000
        assert c.get("/api/me", headers=hdr(u)).json()["points"] == 3_000


# ------------------------------------------------------------------ copilot
def _inquiry(c, u, order, message, subject="문의"):
    r = c.post("/api/inquiries", headers=hdr(u), json={"subject": subject, "message": message, "order_id": order.id if order else None})
    assert r.status_code == 201, r.text
    return r.json()


def test_customer_inquiry_hides_internal_analysis_and_agent_sees_grounded_drafts(db):
    u = make_user(db)
    o = make_order(db, u, [(make_product(db, price=20_000), 1)], delivered_days_ago=15)
    from app import claims
    cl = claims.create_claim(db, u, order_id=o.id, type="return", reason="defect", items=None, claimed_amount=None,
                             unsealed=False, evidence_count=1, description="")
    db.commit()
    with TestClient(app) as c:
        inq = _inquiry(c, u, o, "표지가 찢어져서 반품 보냈어요. 환불은 언제 되나요? 010-1234-5678 로 연락 주세요")
        assert set(inq["messages"][0]) == {"id", "role", "text", "created_at"}   # no analysis, drafts or facts for customers
        conv = c.get(f"/api/admin/conversations/{inq['id']}").json()
        a = conv["messages"][0]["analysis"]
        assert a["classification"]["pii_masked"] == ["phone"] and a["classification"]["category"] in {"refund", "defect"}
        assert a["facts"]["claims"][0]["id"] == cl.id and len(a["drafts"]) == 3
        assert all(d["validation"]["passed"] for d in a["drafts"])
        assert any("환불" in d["reply"] and "18,000" in d["reply"].replace(" ", "") or "20,500" in d["reply"] or "원이 환불" in d["reply"] for d in a["drafts"])
        assert "KB-REF-01#2" in {s["id"] for s in a["sources"]}                  # the rule the decision cited is in the sources
        assert conv["claims"][0]["abuse"] is not None                            # agents do see the internal block


def test_agent_cannot_send_a_refund_promise_the_system_rejected(db):
    u = make_user(db)
    o = make_order(db, u, [(make_product(db), 1)], delivered_days_ago=12)
    from app import claims
    cl = claims.create_claim(db, u, order_id=o.id, type="return", reason="change_of_mind", items=None, claimed_amount=None,
                             unsealed=False, evidence_count=0, description="")
    assert cl.status == "rejected"
    db.commit()
    with TestClient(app) as c:
        conv = _inquiry(c, u, o, "반품이 거절됐어요 왜죠? 환불해 주세요!!")
        bad = c.post(f"/api/admin/conversations/{conv['id']}/agent-messages",
                     json={"text": "안녕하세요 고객님. 불편을 드려 죄송합니다. 요청하신 금액 16,200원을 환불해 드리겠습니다.\n감사합니다."})
        assert bad.status_code == 422
        codes = {f["code"] for f in bad.json()["detail"]["validation"]["findings"]}
        assert "contradicts_decision" in codes
        draft = c.get(f"/api/admin/conversations/{conv['id']}").json()["messages"][0]["analysis"]["drafts"][1]
        assert draft["validation"]["passed"] and "접수가 어렵" in draft["reply"] and "환불해 드리겠습니다" not in draft["reply"]
        ok = c.post(f"/api/admin/conversations/{conv['id']}/agent-messages", json={"text": draft["reply"], "draft_style": draft["style"], "draft_text": draft["reply"]})
        assert ok.status_code == 201
        assert c.get(f"/api/inquiries/{conv['id']}", headers=hdr(u)).json()["answered"] is True
        kpi = c.get("/api/admin/kpi").json()
        assert kpi["accepted_as_is"] == 1


def test_inquiry_must_link_to_own_order(db):
    u, other = make_user(db), make_user(db, "박서준")
    o = make_order(db, other, [(make_product(db), 1)])
    db.commit()
    with TestClient(app) as c:
        r = c.post("/api/inquiries", headers=hdr(u), json={"subject": "x", "message": "내 주문이에요", "order_id": o.id})
        assert r.status_code == 422


def test_claim_sentences_state_the_decision_without_promising_more():
    claim = {"id": 7, "type": "return", "status": "needs_review", "reasons": [], "expected_refund": 0}
    text = " ".join(claim_sentences(claim))
    assert "환불" not in text and "확인" in text


def test_draft_answers_about_the_claim_the_customer_named(db):
    from app import claims
    u = make_user(db)
    mug = make_product(db, "이름 새김 머그컵 (주문제작)", price=16_000, category="goods", returnable=False, discount=0.0)
    shirt = make_product(db, "개발자 티셔츠 고양이 로고", price=25_000, category="goods", discount=0.0)
    o = make_order(db, u, [(mug, 1), (shirt, 1)], delivered_days_ago=2)
    claims.create_claim(db, u, order_id=o.id, type="return", reason="change_of_mind", items=[{"order_item_id": o.items[0].id, "qty": 1}],
                        claimed_amount=None, unsealed=False, evidence_count=0, description="")
    claims.create_claim(db, u, order_id=o.id, type="exchange", reason="defect", items=[{"order_item_id": o.items[1].id, "qty": 1}],
                        claimed_amount=None, unsealed=False, evidence_count=1, description="")
    db.commit()
    with TestClient(app) as c:
        inq = _inquiry(c, u, o, "이름 새김 머그컵 반품이 거절됐어요. 이유가 뭔가요?")
        drafts = c.get(f"/api/admin/conversations/{inq['id']}").json()["messages"][0]["analysis"]["drafts"]
        assert all("접수가 어렵" in d["reply"] and "검수" not in d["reply"] for d in drafts)   # about the mug, not the shirt
        bad = c.post(f"/api/admin/conversations/{inq['id']}/agent-messages",
                     json={"text": "안녕하세요 고객님. 머그컵 16,000원을 환불해 드리겠습니다.\n감사합니다."})
        assert bad.status_code == 422
        assert "contradicts_decision" in {f["code"] for f in bad.json()["detail"]["validation"]["findings"]}
