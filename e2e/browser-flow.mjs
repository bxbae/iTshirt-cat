import { chromium } from "playwright";
import assert from "node:assert/strict";
// Browser walk-through of the main flows against a running stack (fresh demo data).
//   backend: uvicorn app.main:app --port 8000   frontend: npm run build && npm start
//   npm i --no-save playwright   (set CHROME_PATH to use an installed Chromium instead of the bundled one)
//   node e2e/browser-flow.mjs
// It changes the demo data (orders, claims, points), so restart the backend with a fresh DB to run it again.
const exe = process.env.CHROME_PATH || undefined;
const B = process.env.WEB_URL || "http://localhost:3000", A = process.env.API_URL || "http://localhost:8000";
const api = (path, uid, opts = {}) => fetch(A + path, { ...opts, headers: { "Content-Type": "application/json", ...(uid ? { "X-User-Id": String(uid) } : {}) } }).then((r) => r.json());
const browser = await chromium.launch({ executablePath: exe, args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, locale: "ko-KR" });
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
const step = async (name, fn) => { try { await fn(); console.log("PASS", name); } catch (e) { console.log("FAIL", name, "\n   ", e.message.split("\n").slice(0, 4).join("\n    "));  process.exitCode = 1; } };
// SHOTS=dir saves a screenshot at the key moments
const shot = (n) => (process.env.SHOTS ? page.screenshot({ path: `${process.env.SHOTS}/${n}.png`, fullPage: true }) : Promise.resolve());
const T = { timeout: 8000 };

await page.goto(B + "/login");
await page.getByRole("button", { name: /^김민지/ }).click();
await page.waitForURL("**/orders");
const orders = await api("/api/orders", 1);
const byStatus = (s) => orders.find((o) => o.status === s);

await step("A 지연 배송 → 보상 신청 (영수증 기준 1,000원)", async () => {
  const o = byStatus("shipped");
  await page.goto(`${B}/orders/${o.id}`);
  await page.getByRole("button", { name: "4일 늦게 도착시키기" }).click();
  await page.getByText(/예정일보다 4일 늦어졌어요/).waitFor(T);
  await page.getByRole("button", { name: "지연·미수령 보상" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByText("바로 처리됩니다").waitFor(T);
  await shot("claim-late-preview");
  await dlg.getByRole("button", { name: "신청하기" }).click();
  await dlg.getByText("신청이 접수되었습니다").waitFor(T);
  await dlg.getByRole("button", { name: "확인" }).click();
  await page.getByText(/처리 완료/).first().waitFor(T);
  const me = await api("/api/me", 1);
  assert.equal(me.points, 4000);
  await page.getByText(/적립금 4,000원/).first().waitFor(T);
});

await step("B 출고 전 주문 취소 → 즉시 환불", async () => {
  const o = byStatus("preparing");
  await page.goto(`${B}/orders/${o.id}`);
  await page.getByRole("button", { name: "주문 취소" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByText("바로 처리됩니다").waitFor(T);
  await dlg.getByRole("button", { name: "신청하기" }).click();
  await dlg.getByText("신청이 접수되었습니다").waitFor(T);
  await dlg.getByRole("button", { name: "확인" }).click();
  await page.getByText("취소된 주문입니다.").waitFor(T);
  const fresh = await api(`/api/orders/${o.id}`, 1);
  assert.equal(fresh.status, "cancelled"); assert.ok(fresh.refunded_amount > 0);
});

let returnClaimId;
await step("C 단순변심 반품: 배송비 차감 미리보기, 개봉 시 거절, 정상 신청 시 송장 발급", async () => {
  const o = orders.find((x) => x.status === "delivered" && x.items.some((i) => i.title.startsWith("고양이 발자국")));
  await page.goto(`${B}/orders/${o.id}`);
  await page.getByRole("button", { name: "반품·교환 신청" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByText(/반품 배송비 3,000원 차감/).waitFor(T);
  await dlg.getByLabel("상품을 개봉했거나 사용했습니다", { exact: false }).or(dlg.getByText("상품을 개봉했거나 사용했습니다")).first().click();
  await dlg.getByText("아래 사유로 접수할 수 없습니다").waitFor(T);
  await dlg.getByText(/개봉·사용한 .*단순변심 반품이 불가/).first().waitFor(T);
  await shot("claim-unsealed-preview");
  await dlg.getByText("상품을 개봉했거나 사용했습니다").click();
  await dlg.getByText(/승인 — 반품 상품이 입고·검수되면 지급됩니다/).waitFor(T);
  await dlg.getByRole("button", { name: "신청하기" }).click();
  await dlg.getByText(/반품 송장번호/).first().waitFor(T);
  const claims = await api("/api/claims", 1);
  returnClaimId = claims.find((c) => c.status === "awaiting_return" && c.type === "return").id;
  await dlg.getByRole("button", { name: "확인" }).click();
});

await step("D 관리자: 입고 처리 → 보상 큐 순서 처리 → 고객에게 환불 반영", async () => {
  await page.goto(`${B}/admin/queue`);
  await page.getByText("처리 순서").waitFor(T);
  const row = page.locator("li", { hasText: "김민지" }).filter({ hasText: `신청 #${returnClaimId}` });
  await row.getByRole("button", { name: "입고 · 검수 정상" }).click();
  await page.locator("ol > li", { hasText: `신청 #${returnClaimId}` }).waitFor(T);
  const before = await api("/api/admin/queue");
  const mine = before.queue.find((e) => e.claim_id === returnClaimId);
  const positions = before.queue.map((e) => e.claim_id);
  assert.equal(positions.at(-1), returnClaimId, "방금 입고된 건은 줄의 맨 뒤여야 함");
  assert.ok(mine.ready);
  await shot("admin-queue-after-receive");
  await page.getByRole("button", { name: /준비된 \d+건 순서대로 처리/ }).click();
  await page.getByText(/방금 처리: 지급/).waitFor(T);
  const after = await api("/api/claims", 1);
  const c = after.find((x) => x.id === returnClaimId);
  assert.equal(c.status, "completed"); assert.equal(c.refund, c.expected_refund);
});

await step("E 구매 → 결제 → 배송 단계 진행 → 후기 (연락처 포함 시 보류)", async () => {
  await page.goto(B + "/login");
  await page.getByRole("button", { name: /^이하은/ }).click();
  await page.waitForURL("**/orders");
  await page.goto(B + "/products/14");
  await page.getByRole("button", { name: "장바구니" }).click();
  await page.goto(B + "/cart");
  await page.getByText("결제 예정 금액").waitFor(T);
  await page.getByRole("link", { name: "주문하기" }).click();
  await page.getByLabel("주소").fill("서울시 마포구 테스트로 1");
  await page.getByRole("button", { name: "모두 사용" }).click();
  await page.getByRole("button", { name: /결제하기/ }).click();
  await page.getByText("주문이 완료되었습니다").waitFor(T);
  for (const next of ["다음 단계로", "다음 단계로", "다음 단계로"]) {
    await page.getByRole("button", { name: next }).first().click();
    await page.waitForTimeout(400);
  }
  await page.getByRole("button", { name: "후기 쓰기" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByPlaceholder(/솔직한 후기/).fill("좋아요 연락주시면 싸게 드려요 010-2222-3333 카톡 주세요");
  await dlg.getByRole("button", { name: "등록" }).click();
  await page.getByText(/운영 정책 확인 후 공개/).waitFor(T);
  const queue = await api("/api/admin/reviews");
  assert.ok(queue.some((r) => r.status === "flagged" && r.flags.some((f) => f.code === "PERSONAL_INFO")));
});

await step("F 상담 콘솔: 근거 있는 초안 전송, 판정과 모순된 답변은 차단", async () => {
  const convs = await api("/api/admin/conversations");
  const defect = convs.find((c) => c.customer_name === "박서준");
  const mug = convs.find((c) => c.customer_name === "최유나");
  await page.goto(`${B}/admin/console?id=${defect.id}`);
  await page.getByText("답변 초안").first().waitFor(T);
  await page.getByRole("button", { name: "이 초안 사용" }).nth(1).click();
  const box = page.getByLabel("답변 입력");
  await page.waitForFunction(() => /입고/.test(document.querySelector('textarea[aria-label="답변 입력"]').value), null, T);
  await shot("admin-console-draft");
  await page.getByRole("button", { name: "답변 보내기" }).click();
  await page.getByText(/상담원 · /).first().waitFor(T);

  await page.goto(`${B}/admin/console?id=${mug.id}`);
  await page.getByText("답변 초안").first().waitFor(T);
  await page.getByLabel("답변 입력").fill("안녕하세요 고객님. 불편을 드려 죄송합니다. 16,000원을 환불해 드리겠습니다.\n감사합니다.");
  await page.getByText(/시스템이 거절한 신청/).waitFor(T);
  assert.equal(await page.getByRole("button", { name: "답변 보내기" }).isDisabled(), true);
  await shot("admin-console-blocked");
});

await step("G 관리자 화면 스크린샷", async () => {
  await page.goto(B + "/admin/claims"); await page.getByText("자동 판정 근거").or(page.getByText("클레임을 선택")).first().waitFor(T);
  await shot("admin-claims-list");
  await page.goto(B + "/admin/reviews"); await page.getByText("후기 관리").first().waitFor(T); await shot("admin-reviews");
});

console.log("browser console errors:", errors.length ? errors : "none");
await browser.close();
