"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, RequireLogin } from "@/components/shop/bits";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCart } from "@/lib/cart";
import { won } from "@/lib/format";
import type { CartPrice } from "@/lib/types";

export default function CheckoutPage() {
  const { user, ready, refresh } = useAuth();
  const cart = useCart();
  const router = useRouter();
  const [price, setPrice] = useState<CartPrice | null>(null);
  const [points, setPoints] = useState(0);
  const [method, setMethod] = useState("card");
  const [receiver, setReceiver] = useState("");
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = cart.lines.map((l) => `${l.id}:${l.qty}`).join(",");

  useEffect(() => { if (user && !receiver) setReceiver(user.name); }, [user, receiver]);
  useEffect(() => {
    if (!cart.lines.length) return;
    api.price(cart.lines.map((l) => ({ product_id: l.id, qty: l.qty }))).then(setPrice).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const maxPoints = Math.min(user?.points ?? 0, price?.total ?? 0);
  const pay = (price?.total ?? 0) - Math.min(points, maxPoints);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const order = await api.placeOrder({ lines: cart.lines.map((l) => ({ product_id: l.id, qty: l.qty })), points_used: Math.min(points, maxPoints), payment_method: method, receiver, address });
      cart.clear();
      await refresh();
      router.push(`/orders/${order.id}?placed=1`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <RequireLogin user={user} ready={ready}>
      <PageTitle title="주문·결제" />
      {!cart.lines.length ? <Empty>주문할 상품이 없습니다. <Link href="/products" className="font-semibold text-brand-600 underline">상품 보러 가기</Link></Empty> : (
        <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
          <div className="space-y-6">
            <section className="rounded-xl border border-ink-100 bg-surface p-5">
              <h2 className="mb-3 text-sm font-bold">받는 분</h2>
              <div className="grid gap-2.5 sm:grid-cols-2">
                <input className="field" placeholder="이름" value={receiver} onChange={(e) => setReceiver(e.target.value)} aria-label="받는 분 이름" />
                <input className="field sm:col-span-2" placeholder="주소 (데모: 아무 값이나 입력)" value={address} onChange={(e) => setAddress(e.target.value)} aria-label="주소" />
              </div>
            </section>
            <section className="rounded-xl border border-ink-100 bg-surface p-5">
              <h2 className="mb-3 text-sm font-bold">주문 상품</h2>
              <ul className="divide-y divide-ink-100 text-sm">
                {cart.lines.map((l) => <li key={l.id} className="flex justify-between gap-3 py-2"><span className="min-w-0 truncate">{l.title} × {l.qty}</span><span className="tabular-nums">{won(l.sale_price * l.qty)}</span></li>)}
              </ul>
            </section>
            <section className="rounded-xl border border-ink-100 bg-surface p-5">
              <h2 className="mb-3 text-sm font-bold">결제 수단 (데모)</h2>
              <div className="flex flex-wrap gap-2">
                {[["card", "카드"], ["transfer", "계좌이체"], ["easy_pay", "간편결제"]].map(([k, l]) => (
                  <button key={k} onClick={() => setMethod(k)} aria-pressed={method === k}
                    className={`chip py-2 text-sm ${method === k ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-700"}`}>{l}</button>
                ))}
              </div>
              <div className="mt-4 flex items-center gap-2 text-sm">
                <label className="text-ink-500" htmlFor="pts">적립금</label>
                <input id="pts" type="number" min={0} max={maxPoints} className="field w-32 py-1.5" value={points || ""} placeholder="0"
                  onChange={(e) => setPoints(Math.max(0, Math.min(maxPoints, Number(e.target.value) || 0)))} />
                <button className="btn-ghost py-1 text-xs" onClick={() => setPoints(maxPoints)}>모두 사용</button>
                <span className="text-xs text-ink-500">보유 {won(user?.points ?? 0)}</span>
              </div>
            </section>
          </div>
          <aside className="h-fit rounded-xl border border-ink-100 bg-surface p-5 text-sm">
            <dl className="space-y-2">
              <div className="flex justify-between"><dt className="text-ink-500">상품 금액</dt><dd className="tabular-nums">{price ? won(price.items_total) : "–"}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-500">배송비</dt><dd className="tabular-nums">{price ? (price.shipping_fee ? won(price.shipping_fee) : "무료") : "–"}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-500">적립금 사용</dt><dd className="tabular-nums text-accent">−{won(Math.min(points, maxPoints))}</dd></div>
              <div className="flex justify-between border-t border-ink-100 pt-3 text-base font-bold"><dt>최종 결제 금액</dt><dd className="tabular-nums">{price ? won(pay) : "–"}</dd></div>
            </dl>
            <ErrorNote error={error} />
            <button className="btn-primary mt-4 w-full py-3" disabled={busy || !price || !receiver.trim() || !address.trim()} onClick={submit}>{busy ? "결제 중…" : `${won(pay)} 결제하기`}</button>
            <p className="mt-2 text-[11px] text-ink-500">데모라 실제 결제는 일어나지 않습니다. 영수증은 주문 상세에서 확인할 수 있어요.</p>
          </aside>
        </div>
      )}
    </RequireLogin>
  );
}
