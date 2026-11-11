import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const requestId = "316fb188-309e-4c19-94a4-e67d559219ce", alertId = "02508b7c-d6fe-453b-9fb3-233624c5c56c";
const admin = { id: "8e45ea9a-e6f5-43dc-8dbf-11018d46dc21", name: "Fixture Administrator", active: true };

async function fixtures(context: BrowserContext, mode: "normal" | "conflict" | "agent" | "pages" = "normal") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "support-alert-ui-fixture-only"));
  let acknowledged = false, revision = 1, conflicted = false;
  const state = { writes: [] as number[], alertReads: 0, details: 0, pages: [] as number[] };
  const target = "2026-11-09T08:00:00Z";
  const alert = () => ({ id: alertId, support_request_id: requestId, reference: "SR-"+requestId.replaceAll("-", "").toUpperCase(), kind: "complaint", revision,
    owner: admin, target_at: target, created_at: "2026-11-10T08:00:00Z", escalated_at: revision > 1 ? "2026-11-10T08:00:00Z" : null,
    acknowledged_at: acknowledged ? "2026-11-11T08:00:00Z" : null, acknowledged_by: acknowledged ? admin : null });
  const record = { id: requestId, reference: alert().reference, subject: "Synthetic response-target support request", details: "A synthetic concern for the browser regression suite.", kind: "complaint", status: "open", revision: 7,
    customer_update_revision: 0, customer_read_revision: 0, unread_replies: 0, ticket_number: null, created_at: target, updated_at: target, reply_due_at: target,
    resolved_at: null, overdue: true, assignee: admin, customer: { name: "Synthetic Customer", phone_last4: "0001" } };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path.endsWith("/auth/me")) return route.fulfill({ headers, json: { ...admin, role: mode === "agent" ? "agent" : "admin", email: "fixture@example.invalid", available_for_calls: false, mfa_enabled: true } });
    if (path.endsWith("/admin/urgent")) return route.fulfill({ headers, json: { items: [] } });
    if (path.endsWith("/admin/case-alerts")) return route.fulfill({ headers, json: { items: [], unacknowledged: 0 } });
    if (path.endsWith("/acknowledge")) {
      state.writes.push(request.postDataJSON().revision);
      if (mode === "conflict" && !conflicted) {
        conflicted = true; revision = 2;
        return route.fulfill({ headers, status: 409, json: { detail: "This support alert changed. Refresh before acknowledging it." } });
      }
      if (request.postDataJSON().revision !== revision) return route.fulfill({ headers, status: 409, json: { detail: "Stale alert revision" } });
      acknowledged = true; return route.fulfill({ headers, json: alert() });
    }
    if (path.endsWith("/support-requests/deadline-alerts")) {
      state.alertReads++;
      const page = Number(url.searchParams.get("page") || 1), include = url.searchParams.get("include_acknowledged") === "true";
      if (url.searchParams.has("page")) state.pages.push(page);
      const rows = mode === "pages" ? Array.from({ length: 26 }, (_, i) => ({ ...alert(), id: alertId.slice(0,-2)+(10+i), reference: `SR-PAGE-${i+1}` })) : [alert()];
      const visible = acknowledged && !include ? [] : rows;
      const size = Number(url.searchParams.get("page_size") || 25);
      return route.fulfill({ headers, json: { items: visible.slice((page-1)*size,page*size), total: visible.length, page, page_size: size, unacknowledged: acknowledged ? 0 : rows.length, escalated: revision > 1 && !acknowledged ? rows.length : 0, check_interval_seconds: 30 } });
    }
    if (path.endsWith("/support-requests/owners")) return route.fulfill({ headers, json: { items: [admin] } });
    if (path.endsWith("/assignments")) return route.fulfill({ headers, json: { items: [], total: 0, page: 1, page_size: 20 } });
    if (path.endsWith("/messages")) return route.fulfill({ headers, json: { items: [], total: 0, page: 1, page_size: 20 } });
    if (path.endsWith(`/support-requests/${requestId}`)) { state.details++; return route.fulfill({ headers, json: record }); }
    if (path.endsWith("/admin/support-requests")) return route.fulfill({ headers, json: { items: [record], total: 1, page: 1, page_size: 20, overdue: 1, filtered_overdue: 1 } });
    return route.fulfill({ headers, status: 503, json: { detail: "No support-alert browser fixture" } });
  });
  return state;
}

test("support acknowledgement updates the bell and preserves the response target", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/support/alerts");
  await expect(page.getByRole("button", { name: "Notifications (1)", exact: true })).toBeVisible();
  await expect(page.getByText("Response target missed", { exact: true })).toBeVisible();
  await expect(page.locator('.hx-sidebar a[aria-current="page"]')).toHaveCount(1);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(axe.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("support-alerts.png"), fullPage: true });
  await page.getByRole("button", { name: "Acknowledge support alert", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Support alert acknowledged" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "No unacknowledged support alerts" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Notifications (0)", exact: true })).toBeVisible();
  expect(state.writes).toEqual([1]);
  await page.getByRole("checkbox", { name: "Include acknowledged alerts" }).check();
  await expect(page.getByText(/Acknowledged by Fixture Administrator/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Acknowledge support alert", exact: true })).toHaveCount(0);
  await expect(page.getByText(/Target .*Owner: Fixture Administrator/)).toBeVisible();
});

test("a stale escalation requires explicit refresh before acknowledgement", async ({ page, context }) => {
  const state = await fixtures(context, "conflict"); await page.goto("/admin/support/alerts");
  await page.getByRole("button", { name: "Acknowledge support alert", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "This support alert changed" })).toContainText("Refresh before acknowledging");
  await expect(page.getByRole("status").filter({ hasText: "Support alert acknowledged" })).toHaveCount(0);
  await page.getByRole("button", { name: "Refresh alerts", exact: true }).click();
  await expect(page.getByText("Escalated response target", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Acknowledge support alert", exact: true }).click();
  await expect(page.getByRole("heading", { name: "No unacknowledged support alerts" })).toBeVisible();
  expect(state.writes).toEqual([1,2]);
});

test("alert links open the exact support conversation with draft-safe editing", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/support/alerts");
  await page.getByRole("link", { name: "Open support request", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`request=${requestId}`));
  await expect(page.getByRole("region", { name: "Selected support request" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "Synthetic response-target support request", exact: true })).toBeVisible();
  const reply = page.getByRole("textbox", { name: "Reply shown to customer", exact: true });
  await reply.fill("This is an unsent response draft after following the alert.");
  await page.getByRole("button", { name: "Refresh list", exact: true }).click();
  await expect(reply).toHaveValue("This is an unsent response draft after following the alert.");
  expect(state.details).toBeGreaterThan(0);
});

test("support alerts paginate without dropping the acknowledgement filter", async ({ page, context }) => {
  const state = await fixtures(context, "pages"); await page.goto("/admin/support/alerts");
  await expect(page.getByText("SR-PAGE-1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next alerts", exact: true }).click();
  await expect(page.getByText("SR-PAGE-26", { exact: true })).toBeVisible();
  await expect(page.getByText("SR-PAGE-1", { exact: true })).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Include acknowledged alerts" }).check();
  await expect(page.getByText("SR-PAGE-1", { exact: true })).toBeVisible();
  expect(state.pages).toContain(2);
});

test("agents do not fetch private support alert data or see its bell badge", async ({ page, context }) => {
  const state = await fixtures(context, "agent"); await page.goto("/admin/support/alerts");
  await expect(page.getByText("Administrator access is required to review support alerts.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Acknowledge support alert", exact: true })).toHaveCount(0);
  expect(state.alertReads).toBe(0);
});
