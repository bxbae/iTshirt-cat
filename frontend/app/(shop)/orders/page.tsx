"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, RequireLogin } from "@/components/shop/bits";
import { Cover } from "@/components/shop/Cover";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateStr, won } from "@/lib/format";
import type { Claim, Order } from "@/lib/types";
import { CLAIM_STATUS_KO, CLAIM_STATUS_TONE, CLAIM_TYPE_KO } from "@/lib/labels";

const TONE: Record<string, string> = {
  paid: "bg-ink-100 text-ink-700", preparing: "bg-amber-50 text-amber-700", shipped: "bg-brand-50 text-brand-700",
  delivered: "bg-emerald-50 text-emerald-700", cancelled: "bg-red-50 text-red-700",
};

export default function OrdersPage() {
  const { user, ready } = useAuth();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    Promise.all([api.orders(), api.myClaims()]).then(([o, c]) => { setOrders(o); setClaims(c); }).catch((e) => setError(e.message));
  }, [user]);

  return (
    <RequireLogin user={user} ready={ready}>
      <PageTitle title="주문·배송" sub="영수증 확인, 취소·반품·교환, 후기 작성은 주문 상세에서 할 수 있어요." right={<Link href="/support" className="btn-ghost text-sm">1:1 문의</Link>} />
      <ErrorNote error={error} />
      {claims.filter((c) => !["completed", "rejected", "withdrawn"].includes(c.status)).length > 0 && (
        <section className="mb-8">
          <h2 className="mb-2 text-sm font-bold">진행 중인 신청</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {claims.filter((c) => !["completed", "rejected", "withdrawn"].includes(c.status)).map((c) => (
              <li key={c.id}>
                <Link href={`/orders/${c.order_id}`} className="flex items-center gap-3 rounded-xl border border-ink-100 bg-surface p-3 text-sm hover:border-brand-500">
                  <span className={`chip ${CLAIM_STATUS_TONE[c.status]}`}>{CLAIM_STATUS_KO[c.status]}</span>
                  <span className="min-w-0 flex-1 truncate">{CLAIM_TYPE_KO[c.type]} · 주문 {c.order_no}</span>
                  {c.expected_refund > 0 && <span className="text-xs tabular-nums text-ink-500">{won(c.expected_refund)}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      {orders && !orders.length && <Empty>주문 내역이 없습니다. <Link href="/products" className="font-semibold text-brand-600 underline">쇼핑하러 가기</Link></Empty>}
      <ul className="space-y-3">
        {(orders ?? []).map((o) => (
          <li key={o.id}>
            <Link href={`/orders/${o.id}`} className="flex flex-wrap items-center gap-4 rounded-xl border border-ink-100 bg-surface p-4 transition hover:border-brand-500">
              <div className="flex -space-x-3">
                {o.items.slice(0, 3).map((i) => <div key={i.id} className="w-12 ring-2 ring-surface"><Cover title={i.title} hue={i.hue} category={i.category} compact /></div>)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{o.items[0].title}{o.items.length > 1 && ` 외 ${o.items.length - 1}건`}</p>
                <p className="mt-0.5 text-xs text-ink-500">주문번호 {o.order_no} · {dateStr(o.paid_at)}</p>
              </div>
              <div className="flex items-center gap-3">
                {!!o.open_claims && <span className="chip bg-violet-50 text-violet-700">신청 {o.open_claims}건 진행</span>}
                <span className={`chip ${TONE[o.status]}`}>{o.status_ko}</span>
                <span className="w-24 text-right text-sm font-bold tabular-nums">{won(o.paid_amount)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </RequireLogin>
  );
}
