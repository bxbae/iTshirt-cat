import { OUTCOME_KO } from "@/lib/labels";
import { won } from "@/lib/format";
import type { Claim, Decision, Reason } from "@/lib/types";
import { IconAlert, IconCheck } from "../icons";

function norm(d: Decision | Claim) {
  if ("expected_refund" in d) {
    return { outcome: d.outcome ?? "needs_review", reasons: d.reasons, lines: d.lines, refund: d.expected_refund, points: d.points_back, comp: d.compensation };
  }
  return { outcome: d.outcome, reasons: d.reasons, lines: d.lines, refund: d.refund_cash, points: d.points_back, comp: d.compensation?.amount ?? 0 };
}

const HEAD: Record<string, { tone: string; text: string }> = {
  auto_approved: { tone: "bg-emerald-50 text-emerald-800", text: "바로 처리됩니다" },
  approved_pending_return: { tone: "bg-brand-50 text-brand-700", text: "승인 — 반품 상품이 입고·검수되면 지급됩니다" },
  needs_info: { tone: "bg-amber-50 text-amber-800", text: "사진을 첨부하면 이어서 처리됩니다" },
  needs_review: { tone: "bg-violet-50 text-violet-700", text: "상담원이 확인한 뒤 안내드립니다" },
  auto_rejected: { tone: "bg-red-50 text-red-800", text: "아래 사유로 접수할 수 없습니다" },
};

const LEVEL_STYLE: Record<Reason["level"], string> = {
  block: "text-red-800", review: "text-violet-700", warn: "text-amber-800", info: "text-ink-700",
};

/** Plain-language result of the rule engine: what happens, why, and how much. Used for the live preview and after submitting. */
export function DecisionPanel({ d, preview = false }: { d: Decision | Claim; preview?: boolean }) {
  const { outcome: view, reasons, lines, refund, points, comp } = norm(d);
  const head = HEAD[view];
  const ok = view === "auto_approved" || view === "approved_pending_return";
  return (
    <div className="rounded-xl border border-ink-100 bg-surface-2 p-4 text-sm" aria-live="polite">
      <div className={`flex items-center gap-2 rounded-lg px-3 py-2 font-semibold ${head.tone}`}>
        {ok ? <IconCheck size={16} /> : <IconAlert size={16} />}
        <span>{preview && <span className="mr-1 text-xs font-normal opacity-70">예상 결과 ·</span>}{head.text}</span>
      </div>
      {(refund > 0 || points > 0 || comp > 0) && (
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-lg bg-surface p-2"><dt className="text-[11px] text-ink-500">환불 예정(결제수단)</dt><dd className="mt-0.5 font-bold tabular-nums">{won(refund)}</dd></div>
          <div className="rounded-lg bg-surface p-2"><dt className="text-[11px] text-ink-500">적립금 반환</dt><dd className="mt-0.5 font-bold tabular-nums">{won(points)}</dd></div>
          <div className="rounded-lg bg-surface p-2"><dt className="text-[11px] text-ink-500">보상 적립금</dt><dd className="mt-0.5 font-bold tabular-nums text-accent">{won(comp)}</dd></div>
        </dl>
      )}
      {lines.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-ink-700">
          {lines.map((l) => (
            <li key={l.order_item_id} className="flex justify-between gap-2">
              <span className="min-w-0 truncate">{l.title} × {l.qty}{l.qty !== l.requested_qty && <span className="ml-1 text-amber-700">(신청 {l.requested_qty} → {l.qty}로 보정)</span>}</span>
              <span className="tabular-nums text-ink-500">{won(l.unit_price * l.qty)}</span>
            </li>
          ))}
        </ul>
      )}
      {reasons.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-ink-100 pt-3 text-xs leading-relaxed">
          {reasons.map((r, i) => <li key={i} className={LEVEL_STYLE[r.level]}>· {r.message}{r.rule && <span className="ml-1 font-mono text-[10px] text-ink-500">[{r.rule}]</span>}</li>)}
        </ul>
      )}
      <p className="mt-2 text-[11px] text-ink-500">{OUTCOME_KO[view]} · 금액은 영수증의 결제 금액·수량·적립금 사용 내역으로 계산합니다.</p>
    </div>
  );
}
