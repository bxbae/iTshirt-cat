"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, ProductCard } from "@/components/shop/bits";
import { api } from "@/lib/api";
import type { Category, Product } from "@/lib/types";

const SORTS = [
  { key: "popular", label: "판매량순" },
  { key: "new", label: "신상품순" },
  { key: "price_asc", label: "낮은 가격순" },
  { key: "price_desc", label: "높은 가격순" },
];

export default function ProductsPage() {
  return (
    <Suspense>
      <List />
    </Suspense>
  );
}

function List() {
  const params = useSearchParams();
  const router = useRouter();
  const category = params.get("category") ?? "";
  const q = params.get("q") ?? "";
  const sort = params.get("sort") ?? "popular";
  const [items, setItems] = useState<Product[] | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.categories().then(setCats).catch(() => undefined); }, []);
  useEffect(() => {
    setItems(null);
    api.products({ category, q, sort }).then(setItems).catch(() => setError("상품을 불러오지 못했습니다."));
  }, [category, q, sort]);

  const go = (next: Record<string, string>) => {
    const sp = new URLSearchParams({ ...(category && { category }), ...(q && { q }), sort, ...next });
    for (const [k, v] of [...sp.entries()]) if (!v) sp.delete(k);
    router.push(`/products?${sp.toString()}`);
  };
  const title = q ? `‘${q}’ 검색 결과` : cats.find((c) => c.key === category)?.label ?? "전체 상품";

  return (
    <div>
      <PageTitle title={title} sub={items ? `${items.length}개 상품` : undefined}
        right={
          <label className="flex items-center gap-2 text-sm text-ink-500">정렬
            <select className="field w-auto py-1.5" value={sort} onChange={(e) => go({ sort: e.target.value })}>
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
        } />
      <div className="mb-6 flex flex-wrap gap-2">
        <Link href={`/products?sort=${sort}`} className={`chip py-1.5 text-xs ${!category ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-700"}`}>전체</Link>
        {cats.map((c) => (
          <Link key={c.key} href={`/products?category=${c.key}&sort=${sort}`}
            className={`chip py-1.5 text-xs ${category === c.key ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-700"}`}>{c.label} {c.count}</Link>
        ))}
      </div>
      <ErrorNote error={error} />
      {items && !items.length && <Empty>조건에 맞는 상품이 없습니다.</Empty>}
      <div className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-5">
        {(items ?? []).map((p) => <ProductCard key={p.id} p={p} />)}
      </div>
    </div>
  );
}
