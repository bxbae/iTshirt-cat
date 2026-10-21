"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CLAIM_REASON_KO, CLAIM_TYPE_KO } from "@/lib/labels";
import { won } from "@/lib/format";
import type { Claim, ClaimInput, ClaimReason, ClaimType, Decision, Order } from "@/lib/types";
import { DecisionPanel } from "./DecisionPanel";
import { ErrorNote, Modal } from "./bits";

const REASONS: Record<ClaimType, ClaimReason[]> = {
  cancel: ["change_of_mind"],
  return: ["change_of_mind", "defect", "wrong_item", "damaged", "other"],
  exchange: ["defect", "wrong_item", "damaged", "change_of_mind", "other"],
  compensation: ["late_delivery", "missing_item", "other"],
};

export function availableTypes(o: Order): ClaimType[] {
  if (o.status === "cancelled") return [];
  if (o.status === "paid" || o.status === "preparing") return ["cancel", "compensation"];
  if (o.status === "shipped") return ["compensation"];
  return ["return", "exchange", "compensation"];
}

export function ClaimDialog({ order, initialType, onClose, onDone }: { order: Order; initialType?: ClaimType; onClose: () => void; onDone: () => void }) {
  // Fixed when the dialog opens: cancelling the whole order flips its status, which must not close the confirmation.
  const [types] = useState(() => availableTypes(order));
  const [type, setType] = useState<ClaimType>(initialType && types.includes(initialType) ? initialType : types[0]);
  const [reason, setReason] = useState<ClaimReason>(REASONS[type][0]);
  const open = order.items.filter((i) => i.remaining_qty > 0);
  const [picked, setPicked] = useState<Record<number, number>>(() => Object.fromEntries(open.map((i) => [i.id, i.remaining_qty])));
  const [on, setOn] = useState<Record<number, boolean>>(() => Object.fromEntries(open.map((i) => [i.id, true])));
  const [unsealed, setUnsealed] = useState(false);
  const [photos, setPhotos] = useState(0);
  const [amount, setAmount] = useState("");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<Decision | null>(null);
  const [result, setResult] = useState<Claim | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsItems = type !== "compensation";
  const body: ClaimInput = useMemo(() => ({
    order_id: order.id, type, reason,
    items: needsItems ? open.filter((i) => on[i.id]).map((i) => ({ order_item_id: i.id, qty: Math.max(1, Math.min(i.remaining_qty, picked[i.id] ?? 1)) })) : undefined,
    claimed_amount: amount.trim() ? Number(amount.replace(/[^0-9]/g, "")) : null,
    unsealed, evidence_count: photos, description: text,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [order.id, type, reason, on, picked, amount, unsealed, photos, text, needsItems]);

  useEffect(() => { if (!REASONS[type].includes(reason)) setReason(REASONS[type][0]); }, [type, reason]);
  // Live preview: the same rules the server runs on submit, nothing is saved.
  useEffect(() => {
    if (result || (needsItems && !body.items?.length)) { setPreview(null); return; }
    const t = setTimeout(() => api.previewClaim(body).then((d) => { setPreview(d); setError(null); }).catch((e) => setError(e.message)), 250);
    return () => clearTimeout(t);
  }, [body, result, needsItems]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.submitClaim(body));
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!types.length) return null;
  const sellerFault = ["defect", "wrong_item", "damaged"].includes(reason);

  return (
    <Modal title="취소·반품·교환·보상 신청" onClose={onClose} wide>
      {result ? (
        <div className="space-y-3">
          <p className="text-sm font-semibold">신청이 접수되었습니다 <span className="font-normal text-ink-500">(#{result.id})</span></p>
          <DecisionPanel d={result} />
          {result.tracking && <p className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">반품 송장번호 <b className="font-mono">{result.tracking}</b> — 상품을 포장해 이 번호로 보내 주세요. 물류센터에 도착하면 입고 순서대로 처리됩니다.</p>}
          {result.status === "needs_info" && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">주문 상세의 신청 내역에서 사진을 추가하면 바로 이어서 처리됩니다.</p>}
          <button className="btn-primary" onClick={onClose}>확인</button>
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          <div className="space-y-4 text-sm">
            <fieldset>
              <legend className="mb-1.5 text-xs font-semibold text-ink-500">신청 종류</legend>
              <div className="flex flex-wrap gap-2">
                {types.map((t) => (
                  <button key={t} aria-pressed={type === t} onClick={() => setType(t)}
                    className={`chip py-1.5 text-sm ${type === t ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-700"}`}>{CLAIM_TYPE_KO[t]}</button>
                ))}
              </div>
            </fieldset>
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold text-ink-500">사유</span>
              <select className="field" value={reason} onChange={(e) => setReason(e.target.value as ClaimReason)}>
                {REASONS[type].map((r) => <option key={r} value={r}>{CLAIM_REASON_KO[r]}</option>)}
              </select>
            </label>
            {needsItems && (
              <fieldset>
                <legend className="mb-1.5 text-xs font-semibold text-ink-500">상품과 수량 (영수증 기준 남은 수량까지)</legend>
                <ul className="space-y-1.5">
                  {order.items.map((i) => (
                    <li key={i.id} className="flex items-center gap-2 rounded-lg border border-ink-100 p-2">
                      <input type="checkbox" disabled={i.remaining_qty <= 0} checked={!!on[i.id]} onChange={(e) => setOn((c) => ({ ...c, [i.id]: e.target.checked }))} aria-label={`${i.title} 선택`} />
                      <span className="min-w-0 flex-1 truncate text-xs">{i.title}{i.remaining_qty <= 0 && <span className="ml-1 text-ink-500">(신청 불가: 환불·처리 중)</span>}</span>
                      <input type="number" min={1} max={Math.max(1, i.remaining_qty)} disabled={i.remaining_qty <= 0 || !on[i.id]} value={picked[i.id] ?? 1}
                        onChange={(e) => setPicked((c) => ({ ...c, [i.id]: Number(e.target.value) }))} className="field w-16 py-1 text-center text-xs" aria-label={`${i.title} 수량`} />
                      <span className="w-12 text-right text-[11px] text-ink-500">/ {i.remaining_qty}권</span>
                    </li>
                  ))}
                </ul>
              </fieldset>
            )}
            {(type === "return" || type === "exchange") && reason === "change_of_mind" && (
              <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={unsealed} onChange={(e) => setUnsealed(e.target.checked)} />상품을 개봉했거나 사용했습니다</label>
            )}
            {sellerFault && type !== "compensation" && (
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-ink-500">상태 사진 (데모: 파일은 올라가지 않고 개수만 반영)</span>
                <input type="file" accept="image/*" multiple className="text-xs" onChange={(e) => setPhotos(e.target.files?.length ?? 0)} aria-label="상태 사진 첨부" />
                <span className="mt-1 block text-[11px] text-ink-500">첨부 {photos}장 · 불량·파손·오배송은 사진이 있어야 접수됩니다.</span>
              </label>
            )}
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold text-ink-500">환불·보상 받고 싶은 금액 (선택)</span>
              <input className="field" inputMode="numeric" placeholder="비워 두면 영수증 기준으로 계산" value={amount} onChange={(e) => setAmount(e.target.value)} />
              <span className="mt-1 block text-[11px] text-ink-500">영수증·규정과 다르면 자동으로 보정되고, 영수증 금액을 넘으면 상담원이 확인합니다.</span>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold text-ink-500">상세 내용 (선택)</span>
              <textarea className="field h-20 resize-none" value={text} onChange={(e) => setText(e.target.value)} />
            </label>
          </div>
          <div className="space-y-3">
            <p className="text-xs font-semibold text-ink-500">신청 전 미리보기</p>
            {preview ? <DecisionPanel d={preview} preview /> : <p className="rounded-xl border border-dashed border-ink-300 p-6 text-center text-xs text-ink-500">상품을 선택하면 환불액이 계산됩니다.</p>}
            <p className="text-[11px] text-ink-500">결제 금액 {won(order.paid_amount)} (적립금 {won(order.points_used)} 사용) · 이미 환불된 금액 {won(order.refunded_amount)}</p>
            <ErrorNote error={error} />
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={onClose}>닫기</button>
              <button className="btn-primary" disabled={busy || (needsItems && !body.items?.length)} onClick={submit}>{busy ? "접수 중…" : "신청하기"}</button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
