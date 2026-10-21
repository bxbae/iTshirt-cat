"""Demo data created on first start (SEED_DEMO=0 to disable).

Everything below goes through the real services (checkout math, claim engine, receiving, copilot) with the
clock set to the past where needed, so the demo shows what the system actually decides, not canned results.
Titles, authors and publishers are fictional.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import claims, clock, cs, shop
from .models import Order, OrderItem, Product, Review, User

# category, title, author, publisher, list price, discount, stock, returnable, custom, hue, description
PRODUCTS = [
    ("book", "밤의 도서관에서 만난 고양이", "윤서하", "달빛출판", 15800, 0.10, 40, True, False, 262, "퇴근 후 문을 닫은 도서관에서 매일 밤 책을 고르는 고양이와 사서의 이야기. 따뜻한 연작 소설."),
    ("book", "코드 한 줄이 바꾼 서비스", "한도윤", "비트북스", 28000, 0.10, 25, True, False, 205, "작은 코드 변경이 서비스 장애와 개선으로 이어진 열두 가지 현장 기록."),
    ("book", "혼자 배우는 SQL 첫걸음", "민지안", "비트북스", 24000, 0.10, 60, True, False, 168, "데이터가 처음인 사람을 위한 그림 중심 입문서. 실습 파일 제공."),
    ("book", "하루 10분 한국사 노트", "서지후", "새봄미디어", 17500, 0.10, 35, True, False, 28, "한 장에 한 사건. 연표와 지도를 곁들인 가벼운 한국사."),
    ("book", "작은 가게의 숫자들", "오유진", "마루책방", 19800, 0.10, 20, True, False, 45, "동네 가게 사장님을 위한 매출·재고·세금 기초."),
    ("book", "느리게 걷는 제주 한 달", "강하람", "바람의서재", 16800, 0.10, 30, True, False, 190, "한 달 살기 동선, 시장, 책방, 오름 지도를 담은 여행 에세이."),
    ("book", "프로그래머의 책장 전집 (전 5권)", "비트북스 편집부", "비트북스", 150000, 0.10, 8, True, False, 215, "알고리즘, 데이터베이스, 네트워크, 운영체제, 설계 패턴을 묶은 한정 세트."),
    ("book", "별을 세는 아이", "정다온", "달빛출판", 13500, 0.10, 50, True, False, 285, "별자리를 외우던 아이가 할머니의 편지를 따라가는 그림책."),
    ("book", "오늘부터 주식 공부", "류태민", "마루책방", 18500, 0.10, 0, True, False, 12, "초보 투자자를 위한 용어와 리스크 관리. (재입고 예정)"),
    ("foreign_book", "The Quiet Library (영문판)", "Hana Seo", "Moonlight Press", 21000, 0.05, 15, True, False, 255, "Korean bestseller in English: a cat, a librarian and a closed library."),
    ("foreign_book", "Practical Data Structures", "D. Han", "Bit Books", 42000, 0.05, 12, True, False, 200, "Hands-on data structures with short, readable examples."),
    ("ebook", "밤의 도서관에서 만난 고양이 (전자책)", "윤서하", "달빛출판", 11000, 0.10, 9999, False, False, 262, "종이책과 같은 내용을 담은 전자책. 결제 후 바로 읽을 수 있습니다."),
    ("ebook", "혼자 배우는 SQL 첫걸음 (전자책)", "민지안", "비트북스", 16800, 0.10, 9999, False, False, 168, "PDF 실습 파일 포함. 다운로드 후 단순변심 환불이 불가합니다."),
    ("stationery", "고양이 발자국 노트 (A5, 무선)", "캣북스 디자인", "캣북스", 4800, 0.0, 120, True, False, 330, "120g 미색 용지, 줄 간격 7mm. 검정 하드커버."),
    ("stationery", "0.5 젤펜 10색 세트", "캣북스 디자인", "캣북스", 9800, 0.10, 80, True, False, 150, "번짐이 적은 젤 잉크. 10색 한 세트."),
    ("stationery", "만년필 입문 세트", "펜하우스", "펜하우스", 32000, 0.10, 18, True, False, 220, "만년필 1, 카트리지 6, 전용 케이스. 개봉 후 단순변심 환불 불가."),
    ("stationery", "책갈피 12종 세트", "캣북스 디자인", "캣북스", 5500, 0.0, 200, True, False, 90, "금속 책갈피 12종. 고양이, 달, 별 모양."),
    ("stationery", "독서대 (접이식, 우드)", "리딩랩", "리딩랩", 22000, 0.15, 14, True, False, 35, "각도 조절 3단. 접어서 가방에 쏙."),
    ("goods", "개발자 티셔츠 — 고양이 로고 (M)", "캣북스 굿즈", "캣북스", 25000, 0.0, 1, True, False, 300, "면 100%. 'git commit -m \"meow\"' 프린트."),
    ("goods", "개발자 티셔츠 — 고양이 로고 (L)", "캣북스 굿즈", "캣북스", 25000, 0.0, 12, True, False, 300, "면 100%. 'git commit -m \"meow\"' 프린트."),
    ("goods", "이름 새김 머그컵 (주문제작)", "캣북스 굿즈", "캣북스", 16000, 0.0, 30, False, True, 10, "원하는 이름을 새겨 주문 후 제작합니다. 제작 불량이 아니면 환불이 불가합니다."),
    ("goods", "고양이 에코백", "캣북스 굿즈", "캣북스", 12000, 0.0, 45, True, False, 60, "두꺼운 캔버스 천. 책 5권이 거뜬합니다."),
]

USERS = [("김민지", 3000), ("박서준", 0), ("이하은", 500), ("정도윤", 0), ("최유나", 1000)]
REVIEWERS = ["책벌레", "고양이집사", "밤샘독서", "문구덕후", "퇴근길독자"]

_seq = {"n": 0}


def _order(db: Session, user: User, lines: list[tuple[Product, int]], *, paid_days_ago: float, status: str = "delivered",
           delivered_days_ago: float | None = None, late_days: float = 0, points_used: int = 0, now: datetime) -> Order:
    items_total = sum(p.sale_price * q for p, q in lines)
    shipping = 0 if items_total >= 15000 or all(p.category == "ebook" for p, _ in lines) else 2500
    paid_at = now - timedelta(days=paid_days_ago)
    _seq["n"] += 1
    order = Order(order_no=f"{paid_at:%Y%m%d}-{900 + _seq['n']:04d}", user_id=user.id, status=status, items_total=items_total,
                  shipping_fee=shipping, points_used=points_used, paid_amount=items_total + shipping - points_used,
                  payment_method="card", receiver=user.name, address="서울특별시 마포구 (데모 주소)", paid_at=paid_at,
                  expected_delivery_at=paid_at + timedelta(days=2) if status != "cancelled" else None)
    if status in ("shipped", "delivered"):
        order.shipped_at = paid_at + timedelta(days=1)
    if status == "delivered":
        d = now - timedelta(days=delivered_days_ago if delivered_days_ago is not None else paid_days_ago - 2)
        order.delivered_at = d
        order.expected_delivery_at = d - timedelta(days=late_days)
    db.add(order)
    left = points_used
    for n, (p, q) in enumerate(lines):
        total = p.sale_price * q
        share = left if n == len(lines) - 1 else round(points_used * total / max(items_total, 1))
        share = min(share, total, left)
        left -= share
        order.items.append(OrderItem(product_id=p.id, title=p.title, category=p.category, unit_price=p.sale_price, qty=q,
                                     paid_amount=total - share, points_share=share, returnable=p.returnable))
        p.sales += q
    db.flush()
    return order


def _claim(db, user, order, *, at: datetime | None = None, **kw):
    args = dict(order_id=order.id, type="return", reason="change_of_mind", items=None, claimed_amount=None,
                unsealed=False, evidence_count=0, description="")
    args.update(kw)
    if at:
        clock.freeze(at)
    try:
        return claims.create_claim(db, user, **args)
    finally:
        clock.freeze(None)


def _receive(db, claim, *, hours_ago: float, inspection: str = "ok", now: datetime, note: str | None = None):
    clock.freeze(now - timedelta(hours=hours_ago))
    try:
        claims.receive_return(db, claim, inspection=inspection, note=note, agent="물류센터")
    finally:
        clock.freeze(None)


def seed_catalog(db: Session) -> dict[str, Product]:
    now = clock.now()
    out = {}
    for i, (cat, title, author, pub, price, disc, stock, ret, custom, hue, desc) in enumerate(PRODUCTS):
        p = Product(category=cat, title=title, author=author, publisher=pub, list_price=price, discount_rate=disc, stock=stock,
                    returnable=ret, custom_made=custom, hue=hue, description=desc, sales=0,
                    published_at=now - timedelta(days=5 + i * 9))
        db.add(p)
        out[title] = p
    db.flush()
    return out


def seed_demo(db: Session) -> None:
    now = clock.now()
    P = seed_catalog(db)
    book = lambda s: next(p for t, p in P.items() if t.startswith(s))  # noqa: E731
    users = {n: User(name=n, email=f"{n}@example.com", points=pts) for n, pts in USERS}
    for n in REVIEWERS:
        users[n] = User(name=n, email=f"{n}@example.com", points=0)
    db.add_all(users.values())
    db.flush()
    minji, seojun, haeun, doyun, yuna = (users[n] for n, _ in USERS)

    # --- sales history and verified reviews
    reviews = [
        ("책벌레", "밤의 도서관", 5, "문장이 조용하게 좋아요", "퇴근길에 읽다가 정류장을 지나칠 뻔했어요. 고양이 묘사가 특히 좋았습니다."),
        ("고양이집사", "밤의 도서관", 5, "선물용으로 샀어요", "포장도 깔끔하고 책 상태가 아주 좋았어요. 받는 분이 좋아하셨습니다."),
        ("밤샘독서", "코드 한 줄", 4, "현장감 있는 이야기", "장애 회고가 구체적이라 팀원들과 돌려 읽었습니다. 후반부가 조금 짧아요."),
        ("문구덕후", "고양이 발자국 노트", 5, "필기감 최고", "종이가 두껍고 뒷면 비침이 없어요. 두 권 더 주문했어요."),
        ("퇴근길독자", "0.5 젤펜", 3, "색은 예쁜데", "발색은 좋은데 노랑이 조금 약해요. 가격 생각하면 무난합니다."),
        ("책벌레", "혼자 배우는 SQL", 5, "입문자에게 딱", "그림이 많아서 진도가 잘 나가요. 실습 파일도 잘 열립니다."),
    ]
    for who, prefix, rating, title, body in reviews:
        o = _order(db, users[who], [(book(prefix), 1)], paid_days_ago=14, now=now)
        db.add(Review(product_id=o.items[0].product_id, user_id=users[who].id, order_item_id=o.items[0].id,
                      rating=rating, title=title, body=body, status="visible", flags=[],
                      helpful=(rating * 3) % 7, created_at=now - timedelta(days=8)))
    db.flush()

    # --- 김민지: live-demo orders (no claims yet; try them from the shop)
    o_minji = _order(db, minji, [(book("밤의 도서관"), 1), (book("고양이 발자국"), 2)], paid_days_ago=5, delivered_days_ago=3, now=now)
    _order(db, minji, [(book("코드 한 줄"), 1)], paid_days_ago=0.1, status="preparing", now=now)
    _order(db, minji, [(book("느리게 걷는"), 1)], paid_days_ago=6, status="shipped", now=now).expected_delivery_at = now - timedelta(days=4)

    # --- 박서준: damaged book, photo attached -> waiting for return -> arrived 6h ago, inspection ok
    o = _order(db, seojun, [(book("작은 가게"), 1)], paid_days_ago=6, delivered_days_ago=4, now=now)
    c = _claim(db, seojun, o, at=now - timedelta(days=3), reason="damaged", evidence_count=2, description="모서리가 심하게 구겨지고 표지가 찢어져 왔어요.")
    _receive(db, c, hours_ago=6, now=now)
    seojun_defect = c
    # --- 박서준: late delivery paid out automatically (5 days late)
    o = _order(db, seojun, [(book("하루 10분"), 1)], paid_days_ago=9, delivered_days_ago=2, late_days=5, now=now)
    _claim(db, seojun, o, at=now - timedelta(days=1), type="compensation", reason="late_delivery")
    # --- 박서준: a tote that is still on its way back (not yet at the warehouse)
    o = _order(db, seojun, [(book("고양이 에코백"), 1)], paid_days_ago=5, delivered_days_ago=3, now=now)
    _claim(db, seojun, o, at=now - timedelta(hours=8), reason="damaged", evidence_count=1, description="바느질이 뜯어져 있어요.")
    # --- 박서준: T-shirt exchange (stock is 1, shared with 최유나 below)
    o = _order(db, seojun, [(book("개발자 티셔츠 — 고양이 로고 (M)"), 1)], paid_days_ago=6, delivered_days_ago=4, now=now)
    c = _claim(db, seojun, o, at=now - timedelta(days=2), type="exchange", reason="defect", evidence_count=1, description="프린트가 갈라져 있어요.")
    _receive(db, c, hours_ago=2, now=now)

    # --- 최유나: custom mug change-of-mind (auto-rejected), T-shirt exchange arrived first, missing item
    o = _order(db, yuna, [(book("이름 새김"), 1), (book("개발자 티셔츠 — 고양이 로고 (M)"), 1)], paid_days_ago=6, delivered_days_ago=2, now=now)
    mug, shirt = o.items
    _claim(db, yuna, o, at=now - timedelta(days=1), items=[{"order_item_id": mug.id, "qty": 1}], description="마음이 바뀌었어요.")
    c = _claim(db, yuna, o, at=now - timedelta(days=1, hours=2), type="exchange", reason="defect", evidence_count=1,
               items=[{"order_item_id": shirt.id, "qty": 1}], description="목 부분이 올라가 있어요.")
    _receive(db, c, hours_ago=7, now=now)
    o = _order(db, yuna, [(book("책갈피"), 1), (book("0.5 젤펜"), 1)], paid_days_ago=5, delivered_days_ago=3, now=now)
    _claim(db, yuna, o, type="compensation", reason="missing_item", description="택배는 완료로 뜨는데 받은 적이 없어요.")
    # the T-shirt shelf is now one short; keep the demo stock honest
    book("개발자 티셔츠 — 고양이 로고 (M)").stock = 1

    # --- 이하은: window expired for change of mind, inspection mismatch held, amount above the receipt
    o = _order(db, haeun, [(book("만년필"), 1)], paid_days_ago=22, delivered_days_ago=20, now=now)
    _claim(db, haeun, o, at=now - timedelta(hours=20), description="그냥 안 쓸 것 같아요.")
    o = _order(db, haeun, [(book("독서대"), 1)], paid_days_ago=7, delivered_days_ago=5, now=now)
    c = _claim(db, haeun, o, at=now - timedelta(days=4), reason="defect", evidence_count=1, description="다리 한쪽이 흔들려요.")
    _receive(db, c, hours_ago=9, inspection="mismatch", note="사용 흔적과 스크래치가 있어 불량 사유와 다름", now=now)
    o = _order(db, haeun, [(book("별을 세는 아이"), 1)], paid_days_ago=3, delivered_days_ago=1, now=now)
    _claim(db, haeun, o, claimed_amount=90000, description="환불 90,000원 해주세요.")

    # --- 김민지: high-value defect over the automatic limit
    o = _order(db, minji, [(book("프로그래머의 책장"), 1)], paid_days_ago=8, delivered_days_ago=5, now=now)
    _claim(db, minji, o, at=now - timedelta(days=3), reason="defect", evidence_count=3, description="3권의 제본이 풀려 있습니다.")

    # --- 정도윤: five earlier claims that the rules rejected, then another one
    for k in range(5):
        o = _order(db, doyun, [(book("0.5 젤펜"), 1)], paid_days_ago=45 + k, delivered_days_ago=40 + k, now=now)
        _claim(db, doyun, o, at=now - timedelta(days=22 - 3 * k), description="변심")
    o = _order(db, doyun, [(book("하루 10분"), 1), (book("독서대"), 1)], paid_days_ago=4, delivered_days_ago=2, now=now)
    _claim(db, doyun, o, at=now - timedelta(hours=5), description="생각보다 별로예요.")

    # --- inquiries (through the copilot pipeline, linked to the orders above)
    cs.create_inquiry(db, seojun, subject="불량 책 환불은 언제 되나요?", order_id=seojun_defect.order_id,
                      message="표지가 찢어진 책을 반품 보냈는데 환불은 언제 되나요? 보상도 있다고 들었어요.")
    cs.create_inquiry(db, yuna, subject="머그컵 반품 거절 이유가 뭔가요", order_id=mug.order_id,
                      message="이름 새김 머그컵 반품이 거절됐어요!! 마음에 안 드는데 환불 안 되나요? 어이없네요.")
    cs.create_inquiry(db, minji, subject="책이 아직도 안 와요", order_id=db.scalars(select(Order).where(Order.user_id == minji.id, Order.status == "shipped")).first().id,
                      message="주문한 지 6일째인데 아직도 배송 중이에요. 언제쯤 도착하나요? 지연 보상은 없나요?")
    cs.create_inquiry(db, haeun, subject="재입고 문의", message="오늘부터 주식 공부 책 재입고 일정이 궁금해요.")
    # a customer follow-up on the first one is left unanswered on purpose; all four wait for an agent

    # --- reviews that exercise the screening
    o = _order(db, seojun, [(book("하루 10분"), 1)], paid_days_ago=9, delivered_days_ago=7, now=now)
    shop.create_review(db, seojun, order_item_id=o.items[0].id, rating=1, title="배송도 늦고 최악",
                       body="배송이 일주일 가까이 늦었고 포장도 엉망이었어요. 불량 같은 상태로 왔습니다.")
    o = _order(db, haeun, [(book("책갈피"), 1)], paid_days_ago=9, delivered_days_ago=7, now=now)
    shop.create_review(db, haeun, order_item_id=o.items[0].id, rating=5, title="좋아요",
                       body="좋아요! 더 싸게 사고 싶으면 카톡 오픈채팅 open.kakao.com/xyz 로 오세요 할인 코드 드립니다.")
    db.commit()


def ensure_seeded(db: Session) -> None:
    if db.scalar(select(func.count(Product.id))) == 0:
        seed_demo(db)
