import { ApiError } from "./apiError";
import type {
  AdminReview, CartPrice, Category, Claim, ClaimDetail, ClaimInput, ClaimStats, Conversation, ConversationListItem, Dashboard, Decision,
  Health, Inquiry, InquiryItem, Kpi, Me, Order, Product, ProductDetail, QueueRun, QueueView, Review, Summary, Validation,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USER_KEY = "catbooks.user";

export { ApiError };

export function storedUserId(): number | null {
  try {
    const v = localStorage.getItem(USER_KEY);
    return v ? Number(v) : null;
  } catch {
    return null; // storage blocked
  }
}
export function storeUserId(id: number | null) {
  try {
    if (id == null) localStorage.removeItem(USER_KEY);
    else localStorage.setItem(USER_KEY, String(id));
  } catch {
    /* session-only */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const uid = typeof window === "undefined" ? null : storedUserId();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(uid ? { "X-User-Id": String(uid) } : {}), ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* body was not JSON */
    }
    if (detail && typeof detail === "object" && "validation" in detail) {
      const d = detail as { message: string; validation: Validation };
      throw new ApiError(d.message, res.status, d.validation);
    }
    throw new ApiError(typeof detail === "string" ? detail : `요청 실패 (${res.status})`, res.status);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  // customer
  users: () => request<Me[]>("/api/users"),
  me: () => request<Me>("/api/me"),
  categories: () => request<Category[]>("/api/categories"),
  products: (p: { category?: string; q?: string; sort?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]).toString();
    return request<Product[]>(`/api/products${qs ? `?${qs}` : ""}`);
  },
  product: (id: number) => request<ProductDetail>(`/api/products/${id}`),
  helpful: (id: number) => post<{ helpful: number }>(`/api/reviews/${id}/helpful`),
  writeReview: (b: { order_item_id: number; rating: number; title: string; body: string }) =>
    post<Review & { held: boolean; message: string }>("/api/reviews", b),
  price: (lines: { product_id: number; qty: number }[]) => post<CartPrice>("/api/cart/price", lines),
  placeOrder: (b: { lines: { product_id: number; qty: number }[]; points_used: number; payment_method: string; receiver: string; address: string }) =>
    post<Order>("/api/orders", b),
  orders: () => request<Order[]>("/api/orders"),
  order: (id: number) => request<Order>(`/api/orders/${id}`),
  advance: (id: number, late_days = 0) => post<Order>(`/api/orders/${id}/advance`, { late_days }),
  previewClaim: (b: ClaimInput) => post<Decision>("/api/claims/preview", b),
  submitClaim: (b: ClaimInput) => post<Claim>("/api/claims", b),
  myClaims: () => request<Claim[]>("/api/claims"),
  addEvidence: (id: number, count = 1) => post<Claim>(`/api/claims/${id}/evidence`, { count }),
  withdrawClaim: (id: number) => post<Claim>(`/api/claims/${id}/withdraw`),
  inquiries: () => request<InquiryItem[]>("/api/inquiries"),
  inquiry: (id: number) => request<Inquiry>(`/api/inquiries/${id}`),
  newInquiry: (b: { subject: string; message: string; order_id?: number | null }) => post<Inquiry>("/api/inquiries", b),
  followUp: (id: number, text: string) => post<Inquiry>(`/api/inquiries/${id}/messages`, { text }),

  // agent console
  admin: {
    dashboard: (days = 14) => request<Dashboard>(`/api/admin/dashboard?days=${days}`),
    kpi: () => request<Kpi>("/api/admin/kpi"),
    kb: () => request<{ id: string; category: string; title: string; section: string; text: string }[]>("/api/admin/kb"),
    list: () => request<ConversationListItem[]>("/api/admin/conversations"),
    get: (id: number) => request<Conversation>(`/api/admin/conversations/${id}`),
    create: (b: { user_id: number; subject: string; message: string; order_id?: number | null }) => post<Conversation>("/api/admin/conversations", b),
    customerMessage: (id: number, text: string) => post<Conversation>(`/api/admin/conversations/${id}/customer-messages`, { text }),
    check: (id: number, text: string) => post<Validation>(`/api/admin/conversations/${id}/check`, { text }),
    send: (id: number, b: { text: string; draft_style?: string | null; draft_text?: string | null }) =>
      post<Conversation>(`/api/admin/conversations/${id}/agent-messages`, b),
    rejectDraft: (id: number, draft_style: string) => post<void>(`/api/admin/conversations/${id}/reject-draft`, { draft_style }),
    summary: (id: number) => post<Summary>(`/api/admin/conversations/${id}/summary`),
    setStatus: (id: number, status: string) => post<ConversationListItem>(`/api/admin/conversations/${id}/status`, { status }),
    orders: (user_id: number) => request<{ id: number; order_no: string; status: string; status_ko: string; title: string }[]>(`/api/admin/orders?user_id=${user_id}`),
    claims: (status?: string) => request<Claim[]>(`/api/admin/claims${status ? `?status=${status}` : ""}`),
    claimStats: () => request<ClaimStats>("/api/admin/claims/stats"),
    claim: (id: number) => request<ClaimDetail>(`/api/admin/claims/${id}`),
    approve: (id: number, note: string) => post<ClaimDetail>(`/api/admin/claims/${id}/approve`, { note }),
    reject: (id: number, note: string) => post<ClaimDetail>(`/api/admin/claims/${id}/reject`, { note }),
    receive: (id: number, inspection: string, note?: string) => post<ClaimDetail>(`/api/admin/claims/${id}/receive`, { inspection, note }),
    inspect: (id: number, inspection: string, note?: string) => post<ClaimDetail>(`/api/admin/claims/${id}/inspection`, { inspection, note }),
    queue: () => request<QueueView>("/api/admin/queue"),
    processQueue: (b: { limit?: number; claim_ids?: number[] } = {}) => post<QueueRun>("/api/admin/queue/process", b),
    reviews: () => request<AdminReview[]>("/api/admin/reviews"),
    setReview: (id: number, status: "visible" | "hidden") => post<AdminReview>(`/api/admin/reviews/${id}/status`, { status }),
  },
};
