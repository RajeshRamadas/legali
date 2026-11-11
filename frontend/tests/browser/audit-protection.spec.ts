import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

async function fixtures(context: BrowserContext, initial: "configured" | "missing" | "unsupported" | "legacy" = "configured", role = "admin") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "audit-guard-browser-fixture-only"));
  const state = { protection: initial, fail: false, reads: 0, writes: [] as string[] };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const headers = { "access-control-allow-origin":"*", "access-control-allow-headers":"authorization,content-type", "access-control-allow-methods":"GET,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status:204 });
    if (request.method() !== "GET") state.writes.push(path);
    if (path.endsWith("/auth/me")) return reply({ id:"fixture-admin", name:"Fixture Administrator", role, mfa_enabled:true, available_for_calls:false });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items:[], unacknowledged:0 });
    if (path.endsWith("/admin/operations")) {
      state.reads++;
      if (state.fail) return reply({ detail:"Synthetic operations lookup unavailable." },503);
      return reply({ checked_at:"2026-11-11T07:00:00Z", status:state.protection === "configured" || state.protection === "legacy" ? "healthy" : "attention", database:"ready", queue_warn_minutes:10,
        audit_history:state.protection === "legacy" ? undefined : { state:state.protection }, workers:[], channels:[],
        documents:{ pending:0, delayed:0, failed:0, infected:0 }, deadlines:{ unacknowledged:0, escalated:0 }, research:{ failed_24h:0 },
        support:{ overdue_requests:0, unacknowledged:0, escalated:0 } });
    }
    return reply({ detail:"No audit protection browser fixture" },503);
  });
  return state;
}

test("installed audit guards have accessible read-only health status", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/operations");
  const card = page.getByRole("region", { name:"Audit history protection", exact:true });
  await expect(card.getByText("Database guards installed", { exact:true })).toBeVisible();
  await expect(card.getByRole("link", { name:"Review activity history", exact:false })).toHaveAttribute("href","/admin/activity");
  await expect(page.getByRole("region", { name:"Overall health", exact:true })).toContainText("Checks look healthy");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({ path:test.info().outputPath("audit-history-protection.png"), fullPage:true });
  expect(state.writes).toHaveLength(0);
});

for (const condition of ["missing","unsupported","legacy"] as const) test(`${condition} protection needs operator attention`, async ({ page, context }) => {
  await fixtures(context,condition); await page.goto("/admin/operations");
  const card = page.getByRole("region", { name:"Audit history protection", exact:true });
  await expect(card.getByText("Audit guards need attention", { exact:true })).toBeVisible();
  await expect(card).toContainText(condition === "unsupported" ? "does not support" : "missing or changed");
  await expect(page.getByRole("region", { name:"Overall health", exact:true })).toContainText("Attention needed");
});

test("refresh reports missing guards and retains a labelled snapshot on failure", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/operations");
  await expect(page.getByText("Database guards installed", { exact:true })).toBeVisible(); state.protection="missing";
  await page.getByRole("button", { name:"Refresh checks", exact:true }).click();
  await expect(page.getByText("Audit guards need attention", { exact:true })).toBeVisible(); state.fail=true;
  await page.getByRole("button", { name:"Refresh checks", exact:true }).click();
  await expect(page.getByRole("alert").filter({ hasText:"Could not refresh checks" })).toContainText("last successful snapshot");
  await expect(page.getByRole("region", { name:"Overall health", exact:true })).toContainText("Refresh needed");
});

test("agents cannot read administrator audit protection checks", async ({ page, context }) => {
  const state = await fixtures(context,"configured","agent"); await page.goto("/admin/operations");
  await expect(page.getByText("Administrator access is required to view operational checks.", { exact:true })).toBeVisible();
  await expect(page.getByRole("region", { name:"Audit history protection", exact:true })).toHaveCount(0); expect(state.reads).toBe(0);
});
