import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

async function fixtures(context: BrowserContext, role = "admin") {
  let conflict = false;
  const record = { id: "refund-fixture", provider_refund_id: "rfnd_synthetic", provider_payment_id: "pay_synthetic", amount_paise: 10050, currency: "INR", status: "processed", review_code: null, revision: 2, internal_note: "Earlier follow-up", updated_at: "2026-11-10T00:00:00Z" };
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "refund-browser-fixture-only"));
  await context.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", ""), method = route.request().method();
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,PATCH,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ status, headers, json });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/auth/me") return reply({ id: "fixture", name: "Refund Reviewer", role, mfa_enabled: true, available_for_calls: false });
    if (path === "/admin/urgent") return reply({ items: [] });
    if (path === "/admin/case-alerts") return reply({ items: [], total: 0, unacknowledged: 0, escalated: 0 });
    if (path === "/admin/refunds") return reply({ items: [{ id: "payment-fixture", ticket_number: "HX-SYNTHETIC", customer_name: "Synthetic Customer", provider: "razorpay", provider_payment_id: "pay_synthetic", provider_order_id: "order_synthetic", status: "refund_due", amount_paise: 150000, currency: "INR", refunded_paise: 10050, pending_paise: 0, remaining_paise: 139950, review_reason: null }], counts: { needs_action: 1, pending: 0, completed: 0, review: 0 }, unmatched: 1, total: 1, page: 1, page_size: 20 });
    if (path === "/admin/refunds/payments/payment-fixture" || path === "/admin/refunds/unmatched") return reply({ items: [record], total: 1, page: 1, page_size: 20 });
    if (path === "/admin/refunds/refund-fixture/note" && method === "PATCH") {
      if (conflict) { conflict = false; record.revision++; return reply({ detail: "This refund changed. Reload its history before saving a note." }, 409); }
      const body = route.request().postDataJSON(); record.internal_note = body.internal_note; record.revision++; return reply(record);
    }
    return reply({ detail: "No refund fixture for this request." }, 503);
  });
  return { record, conflictNextSave: () => { conflict = true; } };
}

test("refund queue preserves paise and offers accessible follow-up history", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/admin/refunds");
  await expect(page.getByRole("heading", { name: "HX-SYNTHETIC", exact: true })).toBeVisible();
  await expect(page.locator("dd").filter({ hasText: "₹100.50" })).toBeVisible();
  await expect(page.locator("dd").filter({ hasText: "₹1,399.50" })).toBeVisible();
  await page.getByRole("button", { name: "View refund history" }).click();
  const note = page.getByLabel("Internal follow-up note");
  await note.fill("Synthetic follow-up note");
  await page.getByRole("button", { name: "Save internal note" }).click();
  await expect(note).toHaveValue("Synthetic follow-up note");
  await expect.poll(() => state.record.internal_note).toBe("Synthetic follow-up note");
  const report = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(report.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await test.info().attach("refund-queue", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
  await page.getByRole("button", { name: "Unmatched provider refunds (1)" }).click();
  await expect(page.getByRole("heading", { name: "Unmatched provider refunds", exact: true })).toBeVisible();
});

test("a stale follow-up keeps the draft until explicit reload", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/admin/refunds");
  await page.getByRole("button", { name: "View refund history" }).click();
  const note = page.getByLabel("Internal follow-up note");
  await note.fill("Keep this unsaved follow-up"); state.conflictNextSave();
  await page.getByRole("button", { name: "Save internal note" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "This refund changed" })).toBeVisible();
  await expect(note).toHaveValue("Keep this unsaved follow-up");
  await page.getByRole("button", { name: "Reload history (replaces note)" }).click();
  await expect(note).toHaveValue("Earlier follow-up");
});

test("agent cannot open the administrator refund queue", async ({ page, context }) => {
  await fixtures(context, "agent"); await page.goto("/admin/refunds");
  await expect(page.getByText("Administrator access is required.")).toBeVisible();
  await expect(page.getByLabel("Internal follow-up note")).toHaveCount(0);
});

test("customer sees exact partial amounts and a review message for uncertain records", async ({ page, context }) => {
  const profile = { name: "Synthetic Customer", phone: "+919999900001", contact: "+919999900001", email: null };
  await context.addInitScript(value => localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "synthetic-customer", profile: value })), profile);
  await context.route("**/api/v1/**", async route => {
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type" };
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    const payment = { amount: 1500, status: "refund_due", refunded_paise: 10050, refund_pending_paise: 0, paid_at: null, method: null, reference: null, can_pay: false, when: "2026-11-10T00:00:00Z", description: "Synthetic consultation" };
    if (new URL(route.request().url()).pathname === "/api/v1/account") return route.fulfill({ headers, json: { profile, requests: [], bookings: [], payments_mode: "off", payments: [{ ...payment, ticket_number: "HX-PARTIAL" }, { ...payment, ticket_number: "HX-REVIEW", refund_review_required: true }] } });
    return route.fulfill({ status: 503, headers, json: { detail: "No customer refund fixture" } });
  });
  await page.goto("/account");
  await expect(page.locator("#payments")).toContainText("₹100.50 refunded · partial refund");
  await expect(page.locator("#payments")).toContainText("Refund details under review");
  await expect(page.locator("#payments")).not.toContainText("on its way");
});
