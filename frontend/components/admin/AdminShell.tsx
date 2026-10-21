"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";
import { IconBell, IconBook, IconBox, IconChat, IconDashboard, IconReceipt, IconSearch, IconStar } from "../icons";
import { ThemeToggle } from "../ThemeToggle";

const NAV = [
  { href: "/admin", label: "대시보드", Icon: IconDashboard },
  { href: "/admin/console", label: "상담 콘솔", Icon: IconChat },
  { href: "/admin/claims", label: "클레임 판정", Icon: IconReceipt },
  { href: "/admin/queue", label: "보상 큐", Icon: IconBox },
  { href: "/admin/reviews", label: "후기 관리", Icon: IconStar },
  { href: "/admin/kb", label: "지식베이스", Icon: IconBook },
];

const isActive = (path: string, href: string) => (href === "/admin" ? path === "/admin" : path.startsWith(href));

function LogoMark() {
  return (
    <svg width="34" height="30" viewBox="0 0 34 30" aria-hidden="true">
      <path d="M5 28V8l7 5h10l7-5v20Z" fill="rgb(var(--brand-600))" />
      <circle cx="17" cy="20" r="3.4" fill="rgb(var(--accent))" />
    </svg>
  );
}

/** Agent console frame: left icon rail + underline tabs, inside a rounded container on the canvas. */
export function AdminShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)); }, []);
  const mock = health?.llm_provider === "mock";

  return (
    <div className="flex h-screen bg-canvas p-3 text-ink-900 lg:p-6">
      <div className="flex min-w-0 flex-1 overflow-hidden rounded-[28px] bg-app shadow-[0_20px_60px_-30px_rgba(30,30,60,0.35)]">
        <nav className="flex w-[76px] shrink-0 flex-col items-center gap-2 border-r border-ink-100 py-6" aria-label="주 메뉴">
          <Link href="/admin" className="mb-6" aria-label="캣북스 상담원 홈"><LogoMark /></Link>
          {NAV.map(({ href, label, Icon }) => {
            const on = isActive(path, href);
            return (
              <Link key={href} href={href} title={label} aria-label={label} aria-current={on ? "page" : undefined}
                className={`relative flex h-11 w-11 items-center justify-center rounded-xl transition ${on ? "text-brand-600" : "text-ink-500 hover:bg-ink-100 hover:text-ink-900"}`}>
                {on && <span className="absolute -left-[16px] h-6 w-1 rounded-r bg-accent" />}
                <Icon size={20} />
              </Link>
            );
          })}
          <div className="mt-auto flex flex-col items-center gap-3"><ThemeToggle vertical /></div>
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-[72px] shrink-0 items-center gap-6 overflow-x-auto px-8">
            <span className="mr-2 shrink-0 text-[15px] font-semibold tracking-tight">캣북스 CS</span>
            {NAV.map(({ href, label }) => {
              const on = isActive(path, href);
              return (
                <Link key={href} href={href} aria-current={on ? "page" : undefined}
                  className={`relative shrink-0 py-2 text-sm transition ${on ? "font-semibold text-ink-900" : "text-ink-500 hover:text-ink-900"}`}>
                  {label}
                  {on && <span className="absolute -bottom-0.5 left-0 right-0 h-0.5 rounded bg-ink-900" />}
                </Link>
              );
            })}
            <div className="ml-auto flex shrink-0 items-center gap-4 text-ink-700">
              {health && (
                <span title={mock ? "API 키 없이 오프라인 규칙으로 답변 초안을 만듭니다. 환불 판정은 항상 규칙 엔진이 합니다." : `LLM: ${health.llm_provider}`}
                  className={`chip hidden xl:inline-flex ${mock ? "bg-amber-50 text-amber-700" : "bg-brand-50 text-brand-700"}`}>답변 초안 {mock ? "mock" : health.llm_provider}</span>
              )}
              <Link href="/admin/console" title="문의 찾기" aria-label="문의 찾기"><IconSearch size={20} /></Link>
              <IconBell size={20} />
              <Link href="/" className="rounded-full border border-ink-100 px-3 py-1.5 text-xs font-medium hover:bg-ink-100">쇼핑몰 보기 ↗</Link>
            </div>
          </header>
          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
    </div>
  );
}
