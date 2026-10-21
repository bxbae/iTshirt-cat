"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, Price, ProductCard, Stars } from "@/components/shop/bits";
import { Cover } from "@/components/shop/Cover";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { dateStr, won } from "@/lib/format";
import type { ProductDetail } from "@/lib/types";

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const cart = useCart();
  const [p, setP] = useState<ProductDetail | null>(null);
  const [qty, setQty] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    setP(null);
    api.product(Number(id)).then(setP).catch(() => setError("상품을 찾을 수 없습니다."));
  }, [id]);

  if (error) return <ErrorNote error={error} />;
  if (!p) return <div className="py-20 text-center text-sm text-ink-500">불러오는 중…</div>;

  const shipLeft = Math.max(0, 15000 - p.sale_price * qty);
  const isEbook = p.category === "ebook";
  const total = Object.values(p.rating_distribution).reduce((a, b) => a + b, 0);

  return (
    <div>
      <nav className="mb-4 text-xs text-ink-500" aria-label="경로">
        <Link href="/" className="hover:underline">홈</Link> › <Link href={`/products?category=${p.category}`} className="hover:underline">{p.category_ko}</Link>
      </nav>
      <div className="grid gap-8 md:grid-cols-[320px_1fr]">
        <div className="rounded-xl bg-surface-2 p-8"><Cover title={p.title} hue={p.hue} category={p.category} className="mx-auto max-w-[240px]" /></div>
        <div>
          <p className="text-xs font-semibold text-brand-600">{p.category_ko}</p>
          <h1 className="mt-1 break-keep text-2xl font-bold leading-snug">{p.title}</h1>
          <p className="mt-1 text-sm text-ink-500">{p.author} · {p.publisher} · {dateStr(p.published_at)}</p>
          <div className="mt-3 flex items-center gap-2 text-sm"><Stars value={p.rating} /><b>{p.rating ?? "–"}</b><a href="#reviews" className="text-ink-500 underline">후기 {p.review_count}개</a></div>
          <div className="mt-4 border-y border-ink-100 py-4">
            <Price p={p} big />
            <p className="mt-1 text-xs text-ink-500">{p.discount_pct > 0 ? `정가 ${won(p.list_price)} 대비 ${p.discount_pct}% 할인` : "정가 판매"} · {isEbook ? "결제 즉시 이용" : "결제 후 2일 이내 도착 예정 · 15,000원 이상 무료배송"}</p>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-ink-700">{p.description}</p>

          {!p.returnable && (
            <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800" role="note">
              {p.custom_made ? "주문 후 제작되는 상품이라 제작 불량이 아니면 단순변심 환불이 되지 않습니다." : "전자책은 다운로드 후 단순변심 환불이 되지 않습니다."}
            </p>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <div className="flex items-center rounded-full border border-ink-300">
              <button className="px-3 py-2 text-lg" onClick={() => setQty((q) => Math.max(1, q - 1))} aria-label="수량 줄이기">−</button>
              <span className="w-8 text-center text-sm font-semibold tabular-nums" aria-live="polite">{qty}</span>
              <button className="px-3 py-2 text-lg" onClick={() => setQty((q) => Math.min(20, q + 1))} aria-label="수량 늘리기">＋</button>
            </div>
            <button className="btn btn-ghost px-6 py-2.5 text-sm" disabled={p.sold_out} onClick={() => { cart.add(p, qty); setAdded(true); setTimeout(() => setAdded(false), 1800); }}>
              {added ? "담았어요 ✓" : "장바구니"}
            </button>
            <button className="btn-primary px-8 py-2.5" disabled={p.sold_out} onClick={() => { cart.add(p, qty); router.push("/cart"); }}>
              {p.sold_out ? "일시품절" : "바로구매"}
            </button>
          </div>
          {!p.sold_out && !isEbook && shipLeft > 0 && <p className="mt-2 text-xs text-ink-500">{won(shipLeft)} 더 담으면 무료배송</p>}
          {!p.sold_out && p.stock <= 5 && <p className="mt-2 text-xs font-medium text-accent">남은 수량 {p.stock}개</p>}
        </div>
      </div>

      <section id="reviews" className="mt-14">
        <h2 className="text-lg font-bold">구매 후기 <span className="text-ink-500">{total}</span></h2>
        {total > 0 && (
          <div className="mt-3 grid max-w-md gap-1 text-xs">
            {[5, 4, 3, 2, 1].map((s) => (
              <div key={s} className="flex items-center gap-2">
                <span className="w-6 text-ink-500">{s}점</span>
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-ink-100"><span className="block h-full bg-brand-500" style={{ width: `${(p.rating_distribution[s] / total) * 100}%` }} /></span>
                <span className="w-5 text-right tabular-nums text-ink-500">{p.rating_distribution[s]}</span>
              </div>
            ))}
          </div>
        )}
        <ul className="mt-4 divide-y divide-ink-100">
          {p.reviews.map((r) => (
            <li key={r.id} className="py-4">
              <div className="flex items-center gap-2 text-xs text-ink-500">
                <Stars value={r.rating} size={13} /><b className="text-ink-700">{r.user}</b>
                {r.verified && <span className="chip bg-brand-50 text-brand-700">구매 인증</span>}
                <span>{dateStr(r.created_at)}</span>
              </div>
              {r.title && <p className="mt-1.5 text-sm font-semibold">{r.title}</p>}
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-ink-700">{r.body}</p>
              <button className="mt-2 text-xs text-ink-500 hover:text-ink-900"
                onClick={async () => { const { helpful } = await api.helpful(r.id); setP((cur) => cur && { ...cur, reviews: cur.reviews.map((x) => (x.id === r.id ? { ...x, helpful } : x)) }); }}>
                도움돼요 {r.helpful}
              </button>
            </li>
          ))}
        </ul>
        {!p.reviews.length && <p className="mt-3 text-sm text-ink-500">아직 후기가 없습니다. 상품을 받으신 뒤 <Link href="/orders" className="underline">주문 상세</Link>에서 후기를 남길 수 있어요.</p>}
        <p className="mt-3 text-xs text-ink-500">후기는 상품을 받은 구매자만 쓸 수 있고, 개인정보·외부 링크·광고성 내용은 확인 후 공개됩니다.</p>
      </section>

      {p.related.length > 0 && (
        <section className="mt-14">
          <h2 className="mb-4 text-lg font-bold">같은 분류의 다른 상품</h2>
          <div className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-4">{p.related.map((r) => <ProductCard key={r.id} p={r} />)}</div>
        </section>
      )}
    </div>
  );
}
