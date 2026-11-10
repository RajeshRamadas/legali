import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

async function fixtures(context: BrowserContext, failFirst = false) {
  const profile = { name: "Synthetic Customer", phone: "+919999900001", contact: "+919999900001", email: null };
  const review = { id: "review-fixture", lawyer_name: "Synthetic Advocate", ticket_number: "HX-REVIEW-FIXTURE", rating: 1,
    comment: "The advice could have been clearer. <script>plain text</script>", created_at: "2026-11-10T00:00:00Z", status: "published", withdrawn_at: null as string | null };
  let withdrawals = 0, failed = false;
  await context.addInitScript(value => localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "withdrawal-browser-fixture-only", profile: value })), profile);
  await context.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, status, json });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/api/v1/account") return reply({ profile, requests: [], bookings: [], payments: [], payments_mode: "off" });
    if (path === "/api/v1/account/reviews" && method === "GET") return reply({ items: [review], total: 1, page: 1, page_size: 20 });
    if (path === "/api/v1/account/reviews/review-fixture/withdraw" && method === "POST") {
      expect(route.request().postDataJSON()).toEqual({ confirmed: true });
      withdrawals++;
      if (failFirst && !failed) { failed = true; return reply({ detail: "Withdrawal could not be recorded. Please retry." }, 503); }
      review.status = "withdrawn"; review.withdrawn_at = "2026-11-10T01:00:00Z";
      return reply(review);
    }
    return reply({ detail: "No customer-review browser fixture" }, 503);
  });
  return { review, withdrawals: () => withdrawals };
}

test("customer confirms withdrawal, retains private feedback and receives keyboard focus", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/account/reviews");
  const card = page.getByRole("article", { name: "Synthetic Advocate" });
  const withdraw = card.getByRole("button", { name: "Withdraw review", exact: true });
  await withdraw.click();
  await expect(card.getByRole("heading", { name: "Withdraw this review?" })).toBeFocused();
  expect(state.withdrawals()).toBe(0);
  await card.getByRole("button", { name: "Keep review" }).click();
  await expect(withdraw).toBeFocused();
  expect(state.withdrawals()).toBe(0);
  await withdraw.click();
  await expect(card.getByRole("region", { name: "Confirm review withdrawal" })).toContainText("kept privately");
  await card.getByRole("button", { name: "Confirm withdrawal", exact: true }).click();
  await expect(card.getByRole("status")).toContainText("Your review has been withdrawn");
  await expect(card.getByRole("heading", { name: "Synthetic Advocate", exact: true })).toBeFocused();
  await expect(card.getByRole("button", { name: "Withdraw review", exact: true })).toHaveCount(0);
  await expect(card).toContainText("The advice could have been clearer");
  expect(state.withdrawals()).toBe(1);
  const report = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(report.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await test.info().attach("customer-review-withdrawal", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
  await page.reload();
  await expect(page.getByText("Withdrawn by you", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Withdraw review", exact: true })).toHaveCount(0);
});

test("a failed withdrawal keeps the confirmation available for a deliberate retry", async ({ page, context }) => {
  const state = await fixtures(context, true);
  await page.goto("/account/reviews"); await page.getByRole("button", { name: "Withdraw review", exact: true }).click();
  await page.getByRole("button", { name: "Confirm withdrawal", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Withdrawal could not be recorded" })).toBeVisible();
  expect(state.review.status).toBe("published");
  await expect(page.getByRole("button", { name: "Confirm withdrawal", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Confirm withdrawal", exact: true }).click();
  await expect(page.getByText("Withdrawn by you", { exact: true })).toBeVisible();
  expect(state.withdrawals()).toBe(2);
});

test("signed-out customers see sign-in rather than review controls", async ({ page }) => {
  await page.goto("/account/reviews");
  await expect(page.getByRole("heading", { name: "Sign in with your phone" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Withdraw review", exact: true })).toHaveCount(0);
  await expect(page.getByRole("main")).toHaveCount(1);
});

test("moderators can inspect but cannot republish customer-withdrawn feedback", async ({ page, context }) => {
  const review = { id: "review-fixture", rating: 1, comment: "Synthetic private feedback.", reviewer_name: "Asha S.",
    created_at: "2026-11-10T00:00:00Z", updated_at: "2026-11-10T01:00:00Z", status: "withdrawn", withdrawn_at: "2026-11-10T01:00:00Z", revision: 2,
    ticket_number: "HX-REVIEW-FIXTURE", lawyer: { id: "lawyer-fixture", name: "Synthetic Advocate" } };
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "withdrawal-moderator-fixture"));
  await context.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type" };
    const reply = (json: unknown) => route.fulfill({ headers, json });
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/api/v1/auth/me") return reply({ id: "moderator-fixture", name: "Synthetic Moderator", role: "admin", mfa_enabled: true, available_for_calls: false });
    if (path === "/api/v1/admin/urgent") return reply({ items: [] });
    if (path === "/api/v1/admin/case-alerts") return reply({ items: [], unacknowledged: 0, escalated: 0, total: 0 });
    if (path === "/api/v1/admin/reviews") return reply({ items: [review], counts: { pending: 0, published: 0, hidden: 0, withdrawn: 1 }, total: 1, page: 1, page_size: 20 });
    if (path === "/api/v1/admin/reviews/review-fixture") return reply({ review, history: [], total: 0, page: 1, page_size: 20 });
    return route.fulfill({ headers, status: 503, json: { detail: "No moderation withdrawal fixture" } });
  });
  await page.goto("/admin/reviews");
  await page.getByRole("combobox", { name: "Review status", exact: true }).selectOption("withdrawn");
  await page.getByRole("button", { name: "Review feedback" }).click();
  await expect(page.getByText(/The customer withdrew this feedback/)).toContainText("cannot be republished");
  await expect(page.getByRole("combobox", { name: "Publication decision", exact: true })).toHaveCount(0);
});
