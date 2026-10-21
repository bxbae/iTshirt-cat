"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ClaimDialog, availableTypes } from "@/components/shop/ClaimDialog";
import { DecisionPanel } from "@/components/shop/DecisionPanel";
import { ErrorNote, RequireLogin } from "@/components/shop/bits";
import { Cover } from "@/components/shop/Cover";
import { ReviewDialog } from "@/components/shop/ReviewDialog";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateStr, shortDateTime, won } from "@/lib/format";
import { CLAIM_REASON_KO, CLAIM_STATUS_KO, CLAIM_STATUS_TONE, CLAIM_TYPE_KO, INSPECTION_KO, PAYMENT_KO } from "@/lib/labels";
import type { Claim, ClaimType, Order, OrderItem } from "@/lib/types";
import { IconCheck, IconTruck } from "@/components/icons";

const STEPS = [["paid", "결제완료"], ["preparing", "상품준비중"], ["shipped", "배송중"], ["delivered", "배송완료"]] as const;

export default function OrderPage() {
  return <Suspense><Detail /></Suspense>;
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const placed = useSearchParams().get("placed") === "1";
  const { user, ready, refresh } = useAuth();
  const [o, setO] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [claimFor, setClaimFor] = useState<ClaimType | null>(null);
  const [reviewItem, setReviewItem] = useState<OrderItem | null>(null);
  const [note, setNote] = useState<string | null>(placed ? "주문이 완료되었습니다. 영수증을 확인해 보세요." : null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setO(await api.order(Number(id))); setError(null); } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { if (user) load(); }, [user, load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try { await fn(); await load(); await refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <RequireLogin user={user} ready={ready}>
      <ErrorNote error={error} />
      {note && <p role="status" className="mb-4 rounded-lg bg-brand-50 px-3 py-2 text-sm font-medium text-brand-700">{note}</p>}
      {o && (
        <div>
          <nav className="mb-3 text-xs text-ink-500"><Link href="/orders" className="hover:underline">주문·배송</Link> › {o.order_no}</nav>
          <div className="flex flex-wrap items-end gap-3">
            <h1 className="text-2xl font-bold tracking-tight">주문 {o.order_no}</h1>
            <span className="text-sm text-ink-500">{dateStr(o.paid_at)} 결제</span>
            <div className="ml-auto flex flex-wrap gap-2">
              {availableTypes(o).includes("cancel") && <button className="btn-ghost text-sm" onClick={() => setClaimFor("cancel")}>주문 취소</button>}
              {availableTypes(o).includes("return") && <button className="btn-ghost text-sm" onClick={() => setClaimFor("return")}>반품·교환 신청</button>}
              {availableTypes(o).includes("compensation") && o.status !== "paid" && <button className="btn-ghost text-sm" onClick={() => setClaimFor("compensation")}>지연·미수령 보상</button>}
              <Link href={`/support?order=${o.id}`} className="btn-primary text-sm">이 주문 문의하기</Link>
            </div>
          </div>

          {o.status !== "cancelled" ? (
            <ol className="mt-6 grid grid-cols-4 gap-2" aria-label="배송 단계">
              {STEPS.map(([k, label], i) => {
                const at = STEPS.findIndex(([s]) => s === o.status);
                const done = i <= at;
                return (
                  <li key={k} className="text-center text-xs">
                    <div className={`mx-auto flex h-8 w-8 items-center justify-center rounded-full ${done ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-500"}`}>{done ? <IconCheck size={16} /> : i + 1}</div>
                    <p className={`mt-1 ${i === at ? "font-bold" : "text-ink-500"}`}>{label}</p>
                  </li>
                );
              })}
            </ol>
          ) : <p className="mt-5 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800">취소된 주문입니다.</p>}

          <p className="mt-3 text-center text-xs text-ink-500">
            배송 예정일 {dateStr(o.expected_delivery_at)}{o.delivered_at && ` · 도착 ${dateStr(o.delivered_at)}`}
            {o.late_days >= 3 && o.status !== "cancelled" && <b className="ml-1 text-accent">· 예정일보다 {Math.floor(o.late_days)}일 늦어졌어요</b>}
          </p>

          {(o.status === "paid" || o.status === "preparing" || o.status === "shipped") && (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-ink-300 bg-surface-2 px-3 py-2 text-xs text-ink-500">
              <IconTruck size={16} /><span>데모 도구 — 물류 시스템 대신 배송 단계를 직접 진행합니다.</span>
              <button className="btn-ghost py-1 text-xs" disabled={busy} onClick={() => act(() => api.advance(o.id))}>다음 단계로</button>
              {o.status === "shipped" && <button className="btn-ghost py-1 text-xs" disabled={busy} onClick={() => act(() => api.advance(o.id, 4))}>4일 늦게 도착시키기</button>}
            </div>
          )}

          <section className="mt-8 rounded-xl border border-ink-100 bg-surface">
            <h2 className="border-b border-ink-100 px-5 py-3 text-sm font-bold">영수증</h2>
            <table className="w-full text-sm">
              <thead className="text-xs text-ink-500"><tr className="text-left"><th className="px-5 py-2 font-medium">상품</th><th className="px-2 py-2 text-right font-medium">단가</th><th className="px-2 py-2 text-right font-medium">수량</th><th className="px-2 py-2 text-right font-medium">결제(적립금 제외)</th><th className="px-5 py-2" /></tr></thead>
              <tbody>
                {o.items.map((i) => (
                  <tr key={i.id} className="border-t border-ink-100 align-middle">
                    <td className="px-5 py-3"><div className="flex items-center gap-3"><div className="w-10 shrink-0"><Cover title={i.title} hue={i.hue} category={i.category} compact /></div>
                      <div className="min-w-0"><Link href={`/products/${i.product_id}`} className="line-clamp-2 break-keep font-medium hover:underline">{i.title}</Link>
                        {i.refunded_qty > 0 && <span className="text-xs text-red-700">{i.refunded_qty}권 환불됨</span>}
                        {!i.returnable && <span className="ml-1 text-[11px] text-amber-700">환불 제한 상품</span>}</div></div></td>
                    <td className="px-2 py-3 text-right tabular-nums">{won(i.unit_price)}</td>
                    <td className="px-2 py-3 text-right tabular-nums">{i.qty}</td>
                    <td className="px-2 py-3 text-right tabular-nums">{won(i.paid_amount)}{i.points_share > 0 && <span className="block text-[11px] text-ink-500">+ 적립금 {won(i.points_share)}</span>}</td>
                    <td className="px-5 py-3 text-right">{i.can_review ? <button className="btn-ghost py-1 text-xs" onClick={() => setReviewItem(i)}>후기 쓰기</button> : i.reviewed ? <span className="text-xs text-ink-500">후기 작성함</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <dl className="space-y-1.5 border-t border-ink-100 px-5 py-4 text-sm sm:ml-auto sm:max-w-sm">
              <div className="flex justify-between"><dt className="text-ink-500">상품 금액</dt><dd className="tabular-nums">{won(o.items_total)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-500">배송비</dt><dd className="tabular-nums">{o.shipping_fee ? won(o.shipping_fee) : "무료"}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-500">적립금 사용</dt><dd className="tabular-nums">−{won(o.points_used)}</dd></div>
              <div className="flex justify-between border-t border-ink-100 pt-2 font-bold"><dt>결제 금액 ({PAYMENT_KO[o.payment_method]})</dt><dd className="tabular-nums">{won(o.paid_amount)}</dd></div>
              {o.refunded_amount > 0 && <div className="flex justify-between text-red-700"><dt>환불 완료</dt><dd className="tabular-nums">−{won(o.refunded_amount)}</dd></div>}
            </dl>
            <p className="border-t border-ink-100 px-5 py-3 text-xs text-ink-500">받는 분 {o.receiver} · {o.address}</p>
          </section>

          <section className="mt-8">
            <h2 className="mb-3 text-sm font-bold">신청 내역 <span className="font-normal text-ink-500">{o.claims?.length ?? 0}건</span></h2>
            {!o.claims?.length && <p className="rounded-xl border border-dashed border-ink-300 px-4 py-8 text-center text-sm text-ink-500">이 주문에 접수된 취소·반품·교환·보상 신청이 없습니다.</p>}
            <ul className="space-y-4">
              {(o.claims ?? []).map((c) => <ClaimCard key={c.id} c={c} busy={busy} onEvidence={() => act(() => api.addEvidence(c.id, 1))} onWithdraw={() => act(() => api.withdrawClaim(c.id))} />)}
            </ul>
          </section>
        </div>
      )}
      {o && claimFor && <ClaimDialog order={o} initialType={claimFor} onClose={() => setClaimFor(null)} onDone={() => { load(); refresh(); }} />}
      {reviewItem && <ReviewDialog item={reviewItem} onClose={() => setReviewItem(null)} onDone={(m) => { setReviewItem(null); setNote(m); load(); }} />}
    </RequireLogin>
  );
}

function ClaimCard({ c, busy, onEvidence, onWithdraw }: { c: Claim; busy: boolean; onEvidence: () => void; onWithdraw: () => void }) {
  return (
    <li className="rounded-xl border border-ink-100 bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className={`chip ${CLAIM_STATUS_TONE[c.status]}`}>{CLAIM_STATUS_KO[c.status]}</span>
        <span className="text-sm font-semibold">{CLAIM_TYPE_KO[c.type]} · {CLAIM_REASON_KO[c.reason]}</span>
        <span className="text-xs text-ink-500">#{c.id} · {shortDateTime(c.created_at)}</span>
        <div className="ml-auto flex gap-2">
          {c.status === "needs_info" && <button className="btn-primary py-1 text-xs" disabled={busy} onClick={onEvidence}>사진 추가하기 (데모)</button>}
          {["needs_info", "needs_review", "awaiting_return"].includes(c.status) && <button className="btn-ghost py-1 text-xs" disabled={busy} onClick={onWithdraw}>신청 철회</button>}
        </div>
      </div>
      <DecisionPanel d={c} />
      <div className="mt-3 grid gap-2 text-xs text-ink-700 sm:grid-cols-2">
        {c.tracking && c.status === "awaiting_return" && <p className="rounded-lg bg-brand-50 px-3 py-2 text-brand-700">반품 송장번호 <b className="font-mono">{c.tracking}</b> — 이 번호로 상품을 보내 주세요.</p>}
        {c.return_received_at && <p className="rounded-lg bg-surface-2 px-3 py-2">반품 입고 {shortDateTime(c.return_received_at)} · 검수 {INSPECTION_KO[c.inspection ?? "pending"]}</p>}
        {c.status === "completed" && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-emerald-800">처리 완료 {shortDateTime(c.processed_at)} · 환불 {won(c.refund)} · 적립금 반환 {won(c.points_returned)} · 보상 {won(c.compensation_paid)}</p>}
        {c.exchange_shipment && <p className="rounded-lg bg-surface-2 px-3 py-2">교환 상품 발송 · 송장 <b className="font-mono">{c.exchange_shipment.tracking}</b></p>}
      </div>
    </li>
  );
}
