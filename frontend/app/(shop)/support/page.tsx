"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Empty, ErrorNote, PageTitle, RequireLogin } from "@/components/shop/bits";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, shortDateTime } from "@/lib/format";
import type { Inquiry, InquiryItem, Order } from "@/lib/types";

export default function SupportPage() {
  return <Suspense><Support /></Suspense>;
}

const FAQ = [
  ["단순변심 반품은 언제까지 가능한가요?", "상품을 받은 날부터 7일 이내, 미개봉·미사용 상태일 때 가능하며 반품 배송비 3,000원이 환불에서 차감됩니다."],
  ["책이 찢어져서 왔어요.", "받은 날부터 30일 이내에 사진과 함께 반품·교환을 신청하세요. 배송비는 무료이고, 반품이 입고·검수되면 보상 적립금 2,000원이 지급됩니다."],
  ["환불은 언제 되나요?", "반품 상품이 물류센터에 입고되어 검수가 끝나면 입고된 순서대로 처리합니다."],
  ["배송이 늦어요.", "배송 예정일보다 3일 이상 늦으면 적립금 1,000원, 7일 이상이면 3,000원을 드립니다. 주문 상세에서 바로 신청할 수 있어요."],
];

function Support() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const wantedOrder = Number(params.get("order")) || null;
  const openId = Number(params.get("id")) || null;
  const [list, setList] = useState<InquiryItem[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [open, setOpen] = useState<Inquiry | null>(null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [orderId, setOrderId] = useState<number | null>(wantedOrder);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const [l, o] = await Promise.all([api.inquiries(), api.orders()]);
    setList(l);
    setOrders(o);
  }, []);
  useEffect(() => { if (user) load().catch((e) => setError(e.message)); }, [user, load]);
  useEffect(() => { if (user && openId) api.inquiry(openId).then(setOpen).catch((e) => setError(e.message)); else setOpen(null); }, [user, openId]);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [open?.messages.length]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <RequireLogin user={user} ready={ready}>
      <PageTitle title="고객센터" sub="자주 묻는 질문을 먼저 확인하고, 해결되지 않으면 1:1 문의를 남겨 주세요." />
      <ErrorNote error={error} />
      {open ? (
        <div className="mx-auto max-w-2xl">
          <button className="mb-3 text-sm text-ink-500 hover:text-ink-900" onClick={() => router.push("/support")}>‹ 문의 목록</button>
          <h2 className="text-lg font-bold">{open.subject}</h2>
          <p className="mb-4 text-xs text-ink-500">{open.answered ? "답변이 도착했습니다" : "상담원이 확인하고 있습니다"} · 문의 #{open.id}{open.order_id && <button className="ml-2 underline" onClick={() => router.push(`/orders/${open.order_id}`)}>연결된 주문 보기</button>}</p>
          <div className="space-y-3 rounded-xl border border-ink-100 bg-surface p-4">
            {open.messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === "customer" ? "justify-end" : "justify-start"}`}>
                <div className="max-w-[85%]">
                  <div className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === "customer" ? "rounded-tr-sm bg-brand-600 text-white" : "rounded-tl-sm bg-surface-2"}`}>{m.text}</div>
                  <p className={`mt-1 text-[10px] text-ink-500 ${m.role === "customer" ? "text-right" : ""}`}>{m.role === "customer" ? "나" : "캣북스 고객센터"} · {shortDateTime(m.created_at)}</p>
                </div>
              </div>
            ))}
            <div ref={end} />
          </div>
          <div className="mt-3 flex gap-2">
            <textarea className="field h-20 flex-1 resize-none" placeholder="추가로 궁금한 점을 남겨 주세요." value={reply} onChange={(e) => setReply(e.target.value)} />
            <button className="btn-primary self-end" disabled={busy || !reply.trim()} onClick={() => run(async () => { setOpen(await api.followUp(open.id, reply)); setReply(""); await load(); })}>{busy ? "보내는 중…" : "보내기"}</button>
          </div>
        </div>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="min-w-0 space-y-8">
            <section>
              <h2 className="mb-3 text-sm font-bold">내 문의</h2>
              {!list.length && <Empty>남긴 문의가 없습니다.</Empty>}
              <ul className="space-y-2">
                {list.map((i) => (
                  <li key={i.id}>
                    <button onClick={() => router.push(`/support?id=${i.id}`)} className="flex w-full items-center gap-3 rounded-xl border border-ink-100 bg-surface p-4 text-left hover:border-brand-500">
                      <span className={`chip ${i.answered ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{i.answered ? "답변 완료" : "확인 중"}</span>
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{i.subject}</span><span className="block truncate text-xs text-ink-500">{i.preview}</span></span>
                      <span className="text-xs text-ink-500">{ago(i.updated_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h2 className="mb-3 text-sm font-bold">자주 묻는 질문</h2>
              <div className="divide-y divide-ink-100 rounded-xl border border-ink-100 bg-surface">
                {FAQ.map(([q, a]) => (
                  <details key={q} className="group px-4 py-3"><summary className="cursor-pointer text-sm font-medium">{q}</summary><p className="mt-2 text-sm leading-relaxed text-ink-700">{a}</p></details>
                ))}
              </div>
            </section>
          </div>
          <aside className="h-fit min-w-0 rounded-xl border border-ink-100 bg-surface p-5">
            <h2 className="mb-3 text-sm font-bold">1:1 문의하기</h2>
            <label className="mb-2 block text-xs text-ink-500">관련 주문 (선택)
              <select className="field mt-1 max-w-full truncate" value={orderId ?? ""} onChange={(e) => setOrderId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">선택 안 함</option>
                {orders.map((o) => <option key={o.id} value={o.id}>{o.order_no} · {o.items[0].title.slice(0, 16)}</option>)}
              </select>
            </label>
            <input className="field mb-2" placeholder="제목" value={subject} onChange={(e) => setSubject(e.target.value)} />
            <textarea className="field h-32 resize-none" placeholder="문의 내용을 적어 주세요. 주문을 선택하면 영수증 기준으로 더 빠르게 안내드려요." value={message} onChange={(e) => setMessage(e.target.value)} />
            <p className="mt-1 text-[11px] text-ink-500">카드번호·비밀번호는 적지 마세요. 전화번호 등 개인정보는 자동으로 가려서 처리합니다.</p>
            <button className="btn-primary mt-3 w-full" disabled={busy || !subject.trim() || !message.trim()}
              onClick={() => run(async () => { const c = await api.newInquiry({ subject, message, order_id: orderId }); setSubject(""); setMessage(""); await load(); router.push(`/support?id=${c.id}`); })}>
              {busy ? "접수 중…" : "문의 접수"}
            </button>
          </aside>
        </div>
      )}
    </RequireLogin>
  );
}
