"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/shop/bits";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { won } from "@/lib/format";
import type { Me } from "@/lib/types";

const NOTES: Record<string, string> = {
  김민지: "새 주문·취소·지연 보상을 직접 해 볼 수 있는 계정",
  박서준: "반품 입고 대기·입고 완료 건이 있는 계정",
  이하은: "기간 경과 거절, 검수 불일치 보류 건이 있는 계정",
  정도윤: "반복 신청 이력이 있는 계정 (상담원 확인으로 넘어감)",
  최유나: "주문제작 머그컵 반품 거절 · 교환 재고 경쟁 건이 있는 계정",
};

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<Me[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.users().then(setUsers).catch(() => setError("서버에 연결할 수 없습니다. backend(포트 8000)가 실행 중인지 확인하세요."));
  }, []);

  return (
    <div className="mx-auto max-w-xl">
      <PageTitle title="데모 로그인" sub="가상 고객 중 한 명으로 들어가 쇼핑하고 환불·문의를 해 볼 수 있습니다. 비밀번호는 없습니다." />
      {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800">{error}</p>}
      <ul className="space-y-2">
        {users.map((u) => (
          <li key={u.id}>
            <button onClick={async () => { await login(u.id); router.push("/orders"); }}
              className={`flex w-full items-center gap-3 rounded-xl border bg-surface p-4 text-left transition hover:border-brand-500 ${user?.id === u.id ? "border-brand-600" : "border-ink-100"}`}>
              <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 font-bold text-brand-700">{u.name[0]}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{u.name}</span>
                <span className="block text-xs text-ink-500">{NOTES[u.name] ?? u.email}</span>
              </span>
              <span className="text-xs text-ink-500">적립금 {won(u.points)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
