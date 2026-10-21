"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { OrderItem } from "@/lib/types";
import { ErrorNote, Modal, Stars } from "./bits";

export function ReviewDialog({ item, onClose, onDone }: { item: OrderItem; onClose: () => void; onDone: (message: string) => void }) {
  const [rating, setRating] = useState(5);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.writeReview({ order_item_id: item.id, rating, title, body });
      onDone(r.message);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title="후기 쓰기" onClose={onClose}>
      <p className="mb-3 text-sm text-ink-700">{item.title}</p>
      <div className="mb-3 flex items-center gap-2" role="radiogroup" aria-label="별점">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} role="radio" aria-checked={rating === n} onClick={() => setRating(n)} className={`rounded-md border px-2.5 py-1 text-sm ${rating === n ? "border-brand-600 bg-brand-50 font-bold text-brand-700" : "border-ink-100"}`}>{n}점</button>
        ))}
        <Stars value={rating} />
      </div>
      <input className="field mb-2" placeholder="제목 (선택)" value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea className="field h-32 resize-none" placeholder="책과 상품에 대한 솔직한 후기를 10자 이상 남겨 주세요." value={body} onChange={(e) => setBody(e.target.value)} />
      <p className="mt-1 text-[11px] text-ink-500">개인정보·외부 링크·광고성 문구가 있으면 확인 후 공개됩니다. 후기 삭제를 조건으로 보상을 제안하지 않습니다.</p>
      <ErrorNote error={error} />
      <div className="mt-3 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose}>취소</button>
        <button className="btn-primary" disabled={busy || body.trim().length < 10} onClick={submit}>{busy ? "등록 중…" : "등록"}</button>
      </div>
    </Modal>
  );
}
