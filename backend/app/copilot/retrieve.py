"""Policy knowledge-base retrieval (Korean).

The KB is a folder of Markdown documents; each "## " section becomes one chunk with an id like
KB-REF-01#2. Ranking is BM25 over Korean word stems plus character bigrams, so it runs offline with
no model download and still matches inflected forms ("환불해주세요" ~ "환불"). The `Retriever`
interface is small on purpose: an embedding + pgvector retriever can replace it.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import settings

# Longest first, so "에서는" is removed before "는".
PARTICLES = sorted(
    "은 는 이 가 을 를 에 에서 에서는 에게 한테 께 으로 로 의 와 과 도 만 까지 부터 보다 처럼 이나 나 라도 밖에 "
    "인데 인가요 입니다 이에요 예요 이라서 이라고 해요 하고 했어요 했는데 하는데 해주세요 해주시나요 해 주세요 "
    "주세요 되나요 될까요 가능한가요 있나요 없나요 인가 인지 인데요 요".split(),
    key=len, reverse=True,
)
STOPWORDS = set("안녕하세요 감사합니다 문의 드립니다 합니다 있습니다 그리고 그런데 제가 저는 우리 이번 지금 정말 너무 좀 그냥 혹시 아직".split())

# Customers and policy describe the same thing in different words.
SYNONYMS = {
    "돈": ["환불"], "돌려": ["환불"], "환급": ["환불"], "반환": ["환불"], "취소": ["취소", "환불"],
    "안왔": ["배송", "미수령"], "안와": ["배송", "미수령"], "못받": ["배송", "미수령"], "도착": ["배송"], "택배": ["배송"],
    "늦": ["배송", "지연"], "지연": ["배송", "지연"], "언제": ["배송"], "송장": ["배송", "조회"],
    "찢": ["불량", "파손"], "깨": ["불량", "파손"], "구겨": ["불량", "파손"], "젖": ["불량", "파손"], "오염": ["불량", "파손"],
    "잘못": ["오배송"], "다른": ["오배송"], "누락": ["불량", "오배송"],
    "교환": ["교환", "반품"], "반품": ["반품", "환불"], "변심": ["단순변심", "반품"], "마음": ["단순변심"],
    "개봉": ["개봉", "환불불가"], "뜯": ["개봉", "환불불가"], "사용": ["개봉"],
    "두번": ["이중결제"], "두 번": ["이중결제"], "중복": ["이중결제"], "이중": ["이중결제"], "빠져": ["결제", "이중결제"],
    "포인트": ["적립금"], "쿠폰": ["적립금", "보상"], "보상": ["보상", "적립금"], "배상": ["보상"],
    "리뷰": ["후기"], "평점": ["후기"], "별점": ["후기"], "삭제": ["후기", "숨김"],
    "전자책": ["전자책", "환불불가"], "이북": ["전자책"], "ebook": ["전자책"],
    "재고": ["재고", "품절"], "품절": ["재고", "품절"], "입고": ["재고", "입고"], "재입고": ["재고", "입고"],
    "영수증": ["영수증"], "순서": ["처리순서", "입고"], "언제쯤": ["처리순서"],
}


@dataclass
class Chunk:
    id: str
    doc_id: str
    category: str
    title: str
    section: str
    text: str

    @property
    def tokens(self) -> list[str]:
        return tokenize(f"{self.title} {self.section} {self.text}")


def _strip_particle(word: str) -> str:
    for p in PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for w in re.findall(r"[가-힣]+|[a-z0-9]+", text.lower()):
        if re.match(r"[가-힣]", w):
            if w in STOPWORDS:
                continue
            stem = _strip_particle(w)
            tokens.append(stem)
            if len(stem) >= 2:  # bigrams catch compounds: "환불불가" ~ "환불", "불가"
                tokens.extend(stem[i:i + 2] for i in range(len(stem) - 1))
        else:
            tokens.append(w)
    return tokens


def expand_query(text: str) -> list[str]:
    tokens = tokenize(text)
    compact = re.sub(r"\s+", "", text.lower())
    for key, extra in SYNONYMS.items():
        if key.replace(" ", "") in compact:
            for e in extra:
                tokens.extend(tokenize(e))
    return tokens


def parse_kb(kb_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", raw, re.M).group(1).strip()
        doc_id = re.search(r"^id:\s*(\S+)", raw, re.M).group(1)
        category = re.search(r"^category:\s*(\S+)", raw, re.M).group(1)
        for n, part in enumerate(re.split(r"^## ", raw, flags=re.M)[1:], start=1):
            section, _, body = part.partition("\n")
            chunks.append(Chunk(id=f"{doc_id}#{n}", doc_id=doc_id, category=category, title=title,
                                section=section.strip(), text=" ".join(body.split())))
    return chunks


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(c.tokens) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        df = Counter(t for d in self.docs for t in d)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, top_k: int = 3, category_hint: str | None = None) -> list[dict]:
        q = expand_query(query)
        scored = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths):
            score = 0.0
            for t in q:
                tf = doc.get(t, 0)
                if tf:
                    score += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            if category_hint and chunk.category == category_hint:
                score *= 1.25  # the classifier's category is a soft prior, not a filter
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda s: -s[0])
        return [
            {"id": c.id, "doc_id": c.doc_id, "category": c.category, "title": c.title, "section": c.section,
             "text": c.text, "score": round(s, 3)}
            for s, c in scored[:top_k]
        ]


@lru_cache
def get_retriever() -> BM25Retriever:
    return BM25Retriever(parse_kb(settings.kb_dir))
