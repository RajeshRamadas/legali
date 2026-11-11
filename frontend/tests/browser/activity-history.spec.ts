import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const record = "af1251c4-0979-4c1a-86aa-601d77e75601";
const categories = [{ value: "services", label: "Services" }, { value: "staff", label: "Staff & security" }, { value: "other", label: "Other recorded activity" }];
const row = (id: string, activity: string, actor = "Meera Fixture Administrator", category = "services") => ({ id, activity, actor, category, record_type: "Service", record_id: record, at: "2026-11-11T07:00:00Z" });

async function fixtures(context: BrowserContext, role = "admin", failInitial = false) {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "activity-browser-fixture-only"));
  const state = { queries: [] as Record<string, string>[], writes: [] as string[], failNext: failInitial };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, status, json });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (request.method() !== "GET") state.writes.push(path);
    if (path.endsWith("/auth/me")) return reply({ id: "fixture-staff", name: "Meera Fixture Administrator", role, mfa_enabled: true, available_for_calls: false });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path === "/api/v1/admin/activity") {
      const query = Object.fromEntries(url.searchParams); state.queries.push(query);
      if (state.failNext) { state.failNext = false; return reply({ detail: "Activity temporarily unavailable. Try again." }, 503); }
      const filtered = query.category === "services" || !!query.actor;
      const items = query.actor === "Nobody" ? [] : query.cursor ? [row("entry-old", "Service availability changed")] : filtered
        ? [row("entry-filtered", "Intake form published")]
        : [row("entry-new", "Intake form published"), row("entry-unknown", "Other recorded activity", "Unattributed · customer, system or former staff", "other")];
      return reply({ items, categories, checked_at: "2026-11-11T07:01:00Z", next_cursor: query.cursor || filtered ? null : "older-fixture-cursor" });
    }
    return reply({ detail: "No activity browser fixture" }, 503);
  });
  return state;
}

test("read-only activity history renders references with accessible responsive layout", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/activity");
  const entries = page.getByRole("region", { name: "Recorded activity", exact: true });
  await expect(entries.getByRole("heading", { name: "Intake form published", exact: true })).toBeVisible();
  await expect(entries.getByText("Unattributed · customer, system or former staff", { exact: false })).toBeVisible();
  await entries.locator("summary").first().click();
  await expect(entries.getByRole("article", { name: "Intake form published", exact: true }).getByText(record, { exact: true })).toBeVisible();
  await expect(entries).toContainText("IST");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("activity-history.png"), fullPage: true });
  expect(state.queries).toHaveLength(1); expect(state.writes).toHaveLength(0);
});

test("filters apply explicitly and combine staff name dates category and record reference", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/activity");
  const form = page.getByRole("form", { name: "Activity filters" });
  await expect(page.getByRole("heading", { name: "Intake form published", exact: true })).toBeVisible();
  await form.getByRole("combobox", { name: "Activity group", exact: true }).selectOption("services");
  await form.getByRole("textbox", { name: "Staff name", exact: true }).fill("Meera");
  await form.getByLabel("From date", { exact: true }).fill("2026-11-11"); await form.getByLabel("To date", { exact: true }).fill("2026-11-11");
  await form.locator("summary").click(); await form.getByRole("textbox", { name: "Record reference", exact: true }).fill(record);
  expect(state.queries).toHaveLength(1);
  await form.getByRole("button", { name: "Apply activity filters", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Activity refreshed" })).toBeFocused();
  expect(state.queries[1]).toEqual({ category: "services", actor: "Meera", from_date: "2026-11-11", to_date: "2026-11-11", record_id: record });
  await expect(page.locator(".activity-applied")).toContainText("Services · Staff name contains “Meera”");
  await expect(page.getByRole("button", { name: "Older activity", exact: true })).toBeDisabled();
  await form.getByRole("button", { name: "Clear activity filters", exact: true }).click();
  await expect(form.getByRole("textbox", { name: "Staff name", exact: true })).toHaveValue("");
  await expect.poll(() => state.queries.length).toBe(3); expect(state.queries[2]).toEqual({ category: "all" });
});

test("paging caches newer pages and keeps unapplied filter edits", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/activity");
  const name = page.getByRole("textbox", { name: "Staff name", exact: true }); await name.fill("Unapplied draft");
  await page.getByRole("button", { name: "Older activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Service availability changed", exact: true })).toBeVisible();
  await expect(name).toHaveValue("Unapplied draft"); expect(state.queries[1]).toEqual({ category: "all", cursor: "older-fixture-cursor" });
  await page.getByRole("button", { name: "Newer activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Intake form published", exact: true })).toBeVisible(); expect(state.queries).toHaveLength(2);
  await page.getByRole("button", { name: "Refresh activity", exact: true }).click();
  await expect.poll(() => state.queries.length).toBe(3); expect(state.queries[2]).toEqual({ category: "all" });
  await expect(name).toHaveValue("Unapplied draft"); await expect(page.getByText("Filter edits have not been applied. Refresh keeps your filter edits.", { exact: true })).toBeVisible();
});

test("failed refresh preserves the successful page and focuses the error until retry", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/activity");
  await page.getByRole("textbox", { name: "Staff name", exact: true }).fill("Keep this filter edit"); state.failNext = true;
  await page.getByRole("button", { name: "Refresh activity", exact: true }).click();
  const alert = page.getByRole("alert").filter({ hasText: "Could not load activity" });
  await expect(alert).toBeFocused(); await expect(alert).toContainText("The last successful page is still shown");
  await expect(page.getByRole("heading", { name: "Intake form published", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Staff name", exact: true })).toHaveValue("Keep this filter edit");
  await page.getByRole("button", { name: "Refresh activity", exact: true }).click();
  await expect(alert).toHaveCount(0); await expect(page.getByRole("textbox", { name: "Staff name", exact: true })).toHaveValue("Keep this filter edit");
});

test("failed filter application keeps the applied scope separate from edited fields", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/activity");
  await page.getByRole("textbox", { name: "Staff name", exact: true }).fill("Meera"); state.failNext = true;
  await page.getByRole("button", { name: "Apply activity filters", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Could not load activity" })).toBeVisible();
  await expect(page.locator(".activity-applied")).toContainText("All recorded actors");
  await page.getByRole("button", { name: "Apply activity filters", exact: true }).click();
  await expect(page.locator(".activity-applied")).toContainText("Staff name contains “Meera”");
});

test("empty filtered history has clear paging and can be reset", async ({ page, context }) => {
  await fixtures(context); await page.goto("/admin/activity");
  await page.getByRole("textbox", { name: "Staff name", exact: true }).fill("Nobody");
  await page.getByRole("button", { name: "Apply activity filters", exact: true }).click();
  await expect(page.getByText("No recorded activity matches these filters.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Older activity", exact: true })).toBeDisabled(); await expect(page.getByRole("button", { name: "Newer activity", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Clear activity filters", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Intake form published", exact: true })).toBeVisible();
});

test("initial error can be retried while keeping filter drafts", async ({ page, context }) => {
  const state = await fixtures(context, "admin", true); await page.goto("/admin/activity");
  await expect(page.getByRole("alert").filter({ hasText: "Could not load activity" })).toBeVisible();
  await page.getByRole("textbox", { name: "Staff name", exact: true }).fill("Keep initial edit");
  await page.getByRole("button", { name: "Refresh activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Intake form published", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Staff name", exact: true })).toHaveValue("Keep initial edit"); expect(state.queries[1]).toEqual({ category: "all" });
});

test("agents cannot read activity or see the administrator navigation link", async ({ page, context }) => {
  const state = await fixtures(context, "agent"); await page.goto("/admin/activity");
  await expect(page.getByRole("heading", { name: "Administrator access required", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Activity history", exact: true })).toHaveCount(0); expect(state.queries).toHaveLength(0); expect(state.writes).toHaveLength(0);
});
