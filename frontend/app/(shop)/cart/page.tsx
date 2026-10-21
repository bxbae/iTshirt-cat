"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle } from "@/components/shop/bits";
import { Cover } from "@/components/shop/Cover";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { won } from "@/lib/format";
import type { CartPrice } from "@/lib/types";

export default function CartPage() {
  const cart = useCart();
  const [price, setPrice] = useState<CartPrice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = cart.lines.map((l) => `${l.id}:${l.qty}`).join(",");

  useEffect(() => {
    if (!cart.lines.length) { setPrice(null); return; }
    api.price(cart.lines.map((l) => ({ product_id: l.id, qty: l.qty }))).then((p) => { setPrice(p); setError(null); }).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!cart.lines.length) return <><PageTitle title="장바구니" /><Empty>담아 둔 상품이 없습니다. <Link href="/products" className="font-semibold text-brand-600 underline">상품 보러 가기</Link></Empty></>;

  return (
    <div>
      <PageTitle title="장바구니" sub={`${cart.count}권`} />
      <ErrorNote error={error} />
      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <ul className="divide-y divide-ink-100 rounded-xl border border-ink-100 bg-surface">
          {cart.lines.map((l) => (
            <li key={l.id} className="flex gap-4 p-4">
              <Link href={`/products/${l.id}`} className="w-20 shrink-0"><Cover title={l.title} hue={l.hue} category={l.category} compact /></Link>
              <div className="min-w-0 flex-1">
                <Link href={`/products/${l.id}`} className="line-clamp-2 break-keep text-sm font-semibold hover:underline">{l.title}</Link>
                <p className="text-xs text-ink-500">{l.author}</p>
                <div className="mt-2 flex items-center gap-3">
                  <div className="flex items-center rounded-full border border-ink-300 text-sm">
                    <button className="px-2.5 py-1" onClick={() => cart.setQty(l.id, l.qty - 1)} aria-label="수량 줄이기">−</button>
                    <span className="w-7 text-center tabular-nums">{l.qty}</span>
                    <button className="px-2.5 py-1" onClick={() => cart.setQty(l.id, l.qty + 1)} aria-label="수량 늘리기">＋</button>
                  </div>
                  <button className="text-xs text-ink-500 hover:text-ink-900" onClick={() => cart.remove(l.id)}>삭제</button>
                </div>
              </div>
              <p className="text-right text-sm font-bold tabular-nums">{won(l.sale_price * l.qty)}</p>
            </li>
          ))}
        </ul>
        <aside className="h-fit rounded-xl border border-ink-100 bg-surface p-5 text-sm">
          <dl className="space-y-2">
            <div className="flex justify-between"><dt className="text-ink-500">상품 금액</dt><dd className="tabular-nums">{price ? won(price.items_total) : "–"}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-500">배송비</dt><dd className="tabular-nums">{price ? (price.shipping_fee ? won(price.shipping_fee) : "무료") : "–"}</dd></div>
            <div className="flex justify-between border-t border-ink-100 pt-3 text-base font-bold"><dt>결제 예정 금액</dt><dd className="tabular-nums">{price ? won(price.total) : "–"}</dd></div>
          </dl>
          {price && price.free_shipping_gap > 0 && <p className="mt-2 text-xs text-accent">{won(price.free_shipping_gap)} 더 담으면 무료배송</p>}
          <Link href="/checkout" className="btn-primary mt-4 w-full py-3" aria-disabled={!price}>주문하기</Link>
        </aside>
      </div>
    </div>
  );
}
