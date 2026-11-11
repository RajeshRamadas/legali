import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const item = (id: string, title: string, number: string, overdue = false) => ({ id, title, status: "open", source: "manual", due_at: overdue ? "2026-11-10T07:00:00Z" : null,
  overdue, assignee: { id: "fixture-staff", name: "Meera Fixture" },
  case: { ticket_number: number, status: "on_hold", status_label: "On hold", priority: "urgent", service_name: "Title Verification", customer_name: "Fixture Customer" } });

async function fixtures(context: BrowserContext, role = "admin", failInitial = false) {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "task-queue-browser-fixture-only"));
  const state = { queries: [] as Record<string,string>[], writes: [] as string[], failNext: failInitial, revoked: false, outOfRange: false };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (request.method() !== "GET") state.writes.push(path);
    if (path.endsWith("/auth/me")) return reply({ id: "fixture-staff", name: "Meera Fixture", role, mfa_enabled: true, available_for_calls: false });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path === "/api/v1/admin/task-queue") {
      const query = Object.fromEntries(url.searchParams); state.queries.push(query);
      if (state.failNext) { state.failNext = false; return reply({ detail: "Task queue temporarily unavailable." }, 503); }
      const page = Number(query.page || "1"), empty = state.revoked || query.q === "Missing", filtered = !!query.q || query.due !== "all" || query.priority !== "all";
      const items = empty || (state.outOfRange && page === 2) ? [] : page === 2 ? [item("later", "Review the older checklist", "HX-OLDER")]
        : filtered ? [item("filtered", "Review the filtered checklist", "HX-FILTERED", true)]
        : [item("first", "Review the transaction checklist", "HX-FIRST", true), item("second", "Confirm the pending record", "HX-SECOND")];
      return reply({ items, total: empty ? 0 : state.outOfRange || filtered ? 1 : 26, page, page_size: 25, checked_at: "2026-11-11T07:00:00Z",
        summary: empty ? { open:0, overdue:0, due_today:0, unscheduled:0 } : { open:26, overdue:4, due_today:7, unscheduled:3 } });
    }
    return reply({ detail: "No task queue browser fixture" }, 503);
  });
  return state;
}

test("staff task queue shows accessible deadlines and links without writing", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/tasks");
  const results = page.getByRole("region", { name: "Matching tasks", exact: true });
  await expect(results.getByRole("heading", { name: "Review the transaction checklist", exact: true })).toBeVisible();
  await expect(results.getByRole("link", { name: "Open case HX-FIRST", exact: true })).toHaveAttribute("href", "/admin/tickets/HX-FIRST");
  await expect(results.getByText("Case on hold · task due date stays as recorded.", { exact: true }).first()).toBeVisible();
  await expect(results).toContainText("IST");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0,0); });
  await page.screenshot({ path:test.info().outputPath("staff-task-queue.png"), fullPage:true });
  expect(state.queries).toHaveLength(1); expect(state.writes).toHaveLength(0);
});

test("administrator combines ownership status due priority and explicit search filters", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/tasks");
  const form = page.getByRole("form", { name: "Task queue filters" });
  await form.getByRole("textbox", { name: "Search tasks", exact: true }).fill("review");
  await form.getByRole("combobox", { name: "Task ownership", exact: true }).selectOption("all");
  await form.getByRole("combobox", { name: "Task status", exact: true }).selectOption("all");
  await form.getByRole("combobox", { name: "Task due date", exact: true }).selectOption("today");
  await form.getByRole("combobox", { name: "Case priority", exact: true }).selectOption("urgent"); expect(state.queries).toHaveLength(1);
  await form.getByRole("button", { name: "Apply task filters", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task queue loaded" })).toBeFocused();
  expect(state.queries[1]).toEqual({ assignee:"all", status:"all", due:"today", priority:"urgent", q:"review", page:"1", page_size:"25" });
  await expect(page.locator(".task-queue-applied")).toContainText("Everyone · All task statuses · Due today · Case priority: urgent · Search: “review”");
  await expect(page.getByRole("button", { name: "Next tasks", exact: true })).toBeDisabled();
});

test("paging and refresh use applied filters while keeping search edits", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/tasks");
  const search = page.getByRole("textbox", { name: "Search tasks", exact: true }); await search.fill("Unapplied search");
  await page.getByRole("button", { name: "Next tasks", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review the older checklist", exact: true })).toBeVisible();
  expect(state.queries[1].q).toBe(""); expect(state.queries[1].page).toBe("2"); await expect(search).toHaveValue("Unapplied search");
  await page.getByRole("button", { name: "Refresh tasks", exact: true }).click();
  await expect.poll(() => state.queries.length).toBe(3); expect(state.queries[2].page).toBe("2"); expect(state.queries[2].q).toBe("");
  await page.getByRole("button", { name: "Previous tasks", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review the transaction checklist", exact: true })).toBeVisible();
  await expect(search).toHaveValue("Unapplied search"); expect(state.queries[3].page).toBe("1");
});

test("failed refresh preserves results and filter drafts with focused feedback", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/tasks");
  await page.getByRole("textbox", { name: "Search tasks", exact: true }).fill("Keep this task search"); state.failNext = true;
  await page.getByRole("button", { name: "Refresh tasks", exact: true }).click();
  const error = page.getByRole("alert").filter({ hasText: "Could not load tasks" }); await expect(error).toBeFocused(); await expect(error).toContainText("last successful page");
  await expect(page.getByRole("heading", { name: "Review the transaction checklist", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Search tasks", exact: true })).toHaveValue("Keep this task search");
  await page.getByRole("button", { name: "Refresh tasks", exact: true }).click(); await expect(error).toHaveCount(0);
});

test("failed apply keeps the old scope until a reviewed retry succeeds", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/tasks");
  await page.getByRole("textbox", { name: "Search tasks", exact: true }).fill("review"); state.failNext = true;
  await page.getByRole("button", { name: "Apply task filters", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Could not load tasks" })).toBeVisible();
  await expect(page.locator(".task-queue-applied")).not.toContainText("Search:");
  await page.getByRole("button", { name: "Apply task filters", exact: true }).click();
  await expect(page.locator(".task-queue-applied")).toContainText("Search: “review”");
});

test("empty queue resets to mine and open tasks with clear filters", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/tasks");
  await page.getByRole("textbox", { name: "Search tasks", exact: true }).fill("Missing"); await page.getByRole("button", { name: "Apply task filters", exact: true }).click();
  await expect(page.getByText("No tasks match these filters in cases you can currently open.", { exact:true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next tasks", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Clear task filters", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review the transaction checklist", exact: true })).toBeVisible();
  expect(state.queries[2]).toEqual({ assignee:"me", status:"open", due:"all", priority:"all", q:"", page:"1", page_size:"25" });
});

test("agents have their own queue without administrator ownership options", async ({ page, context }) => {
  const state = await fixtures(context,"agent"); await page.goto("/admin/tasks");
  const scope = page.getByRole("combobox", { name:"Task ownership", exact:true });
  await expect(scope.locator("option")).toHaveCount(1); await expect(scope).toHaveValue("me");
  const menu = page.getByRole("button", { name:"Open navigation", exact:true });
  const mobile = await menu.isVisible(); if (mobile) await menu.click();
  await expect(page.getByRole("link", { name:"Task queue", exact:true })).toBeVisible();
  if (mobile) await page.getByRole("button", { name:"Close navigation", exact:true }).click();
  await expect(page.getByRole("heading", { name:"Review the transaction checklist", exact:true })).toBeVisible(); expect(state.queries[0].assignee).toBe("me");
});

test("initial failure can recover while retaining unapplied search", async ({ page, context }) => {
  await fixtures(context,"admin",true); await page.goto("/admin/tasks");
  await expect(page.getByRole("alert").filter({ hasText:"Could not load tasks" })).toBeVisible();
  await page.getByRole("textbox", { name:"Search tasks", exact:true }).fill("Keep initial search");
  await page.getByRole("button", { name:"Refresh tasks", exact:true }).click();
  await expect(page.getByRole("heading", { name:"Review the transaction checklist", exact:true })).toBeVisible();
  await expect(page.getByRole("textbox", { name:"Search tasks", exact:true })).toHaveValue("Keep initial search");
});

test("successful refresh removes tasks when current case access is revoked", async ({ page, context }) => {
  const state=await fixtures(context,"agent"); await page.goto("/admin/tasks");
  await expect(page.getByRole("link", { name:"Open case HX-FIRST", exact:true })).toBeVisible(); state.revoked=true;
  await page.getByRole("button", { name:"Refresh tasks", exact:true }).click();
  await expect(page.getByRole("link", { name:"Open case HX-FIRST", exact:true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name:"Matching tasks (0)", exact:true })).toBeVisible();
});

test("a shrinking last page offers previous navigation without discarding drafts", async ({ page, context }) => {
  const state=await fixtures(context); await page.goto("/admin/tasks");
  await page.getByRole("textbox", { name:"Search tasks", exact:true }).fill("Keep page search"); state.outOfRange=true;
  await page.getByRole("button", { name:"Next tasks", exact:true }).click();
  await expect(page.getByText("No tasks on this page. Choose Previous tasks or refresh.", { exact:true })).toBeVisible();
  await page.getByRole("button", { name:"Previous tasks", exact:true }).click();
  await expect(page.getByRole("heading", { name:"Review the transaction checklist", exact:true })).toBeVisible();
  await expect(page.getByRole("textbox", { name:"Search tasks", exact:true })).toHaveValue("Keep page search");
});
