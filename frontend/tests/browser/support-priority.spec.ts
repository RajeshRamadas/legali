import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const id = "616fb188-309e-4c19-94a4-e67d559219ce";
const owner = { id: "8e45ea9a-e6f5-43dc-8dbf-11018d46dc21", name: "Fixture Administrator", active: true };
const record = { id, reference: "SR-PRIORITY-FIXTURE", subject: "Oldest unanswered support request", details: "Synthetic support conversation for queue prioritization.",
  kind: "documents", status: "in_progress", revision: 3, customer_update_revision: 0, customer_read_revision: 0, unread_replies: 0,
  ticket_number: null, created_at: "2026-11-08T06:00:00Z", updated_at: "2026-11-11T06:00:00Z", reply_due_at: "2026-11-10T06:00:00Z", resolved_at: null, overdue: true,
  assignee: owner, customer: { name: "Synthetic Customer", phone_last4: "0001" } };

async function fixtures(context: BrowserContext, mode: "normal" | "slow" | "failure" = "normal") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "queue-priority-fixture-only"));
  let release = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  const state = { queries: [] as URLSearchParams[], writes: 0, release: () => release() };
  await context.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (request.method() !== "GET") { state.writes++; return reply({ detail: "Unexpected fixture write" }, 400); }
    if (path.endsWith("/auth/me")) return reply({ ...owner, role: "admin", email: "fixture@example.invalid", available_for_calls: false, mfa_enabled: true });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path.endsWith("/support-requests/owners")) return reply({ items: [owner] });
    if (path.endsWith("/messages")) return reply({ items: [], total: 0, page: 1, page_size: 20 });
    if (path.endsWith(`/support-requests/${id}`)) return reply(record);
    if (path.endsWith("/admin/support-requests")) {
      state.queries.push(url.searchParams);
      const target = url.searchParams.get("response_target");
      if (mode === "slow" && target === "overdue") await gate;
      if (mode === "failure" && target === "overdue" && state.queries.length === 2) return reply({ detail: "Queue temporarily unavailable" }, 503);
      const empty = target === "due_soon" || target === "none";
      const currentPage = Number(url.searchParams.get("page") || 1);
      return reply({ items: empty ? [] : [{ ...record, subject: currentPage === 1 ? record.subject : "Second page support request" }],
        total: empty ? 0 : 21, page: currentPage, page_size: 20, overdue: 8, filtered_overdue: empty ? 0 : 3, response_target_as_of: "2026-11-11T06:00:00Z" });
    }
    return reply({ detail: "No priority browser fixture" }, 503);
  });
  return state;
}

test("priority filters reset paging, compose with owner/category/search and preserve conversation drafts", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto(`/admin/support?request=${id}`);
  await expect(page.getByRole("combobox", { name: "Queue order", exact: true })).toHaveValue("response_target");
  await expect(page.getByText(/Targets checked/)).toBeVisible();
  await expect(page.locator(".support-list")).toContainText("Team target");
  const reply = page.getByRole("textbox", { name: "Reply shown to customer", exact: true }), note = page.getByRole("textbox", { name: "Internal note (administrators only)", exact: true });
  await reply.fill("Keep this unsent reply while prioritizing work."); await note.fill("Keep this private draft too.");
  await page.getByRole("combobox", { name: "Request status", exact: true }).selectOption("waiting_for_customer");
  await page.getByRole("button", { name: "Next requests", exact: true }).click();
  await expect(page.getByText("Page 2", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("overdue");
  await expect(page.getByText("Page 1", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Owner", exact: true }).selectOption("me");
  await page.getByRole("combobox", { name: "Category", exact: true }).selectOption("documents");
  await page.getByLabel("Subject or reference").fill("Oldest"); await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect.poll(() => state.queries.at(-1)?.get("q")).toBe("Oldest");
  const query = state.queries.at(-1)!;
  expect(query.get("response_target")).toBe("overdue"); expect(query.get("page")).toBe("1");
  expect(query.get("kind")).toBe("documents"); expect(query.get("assignee")).toBe("me");
  await page.getByRole("combobox", { name: "Queue order", exact: true }).selectOption("updated");
  await expect.poll(() => state.queries.at(-1)?.get("sort")).toBe("updated");
  await page.getByRole("button", { name: "Refresh list", exact: true }).click();
  await expect(reply).toHaveValue("Keep this unsent reply while prioritizing work."); await expect(note).toHaveValue("Keep this private draft too.");
  await expect(page.getByRole("combobox", { name: "Request status", exact: true })).toHaveValue("waiting_for_customer");
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("due_soon");
  await expect(page.getByText("No support requests found.")).toBeVisible();
  await expect(page.getByRole("heading", { name: record.subject, exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("none");
  await expect.poll(() => state.queries.at(-1)?.get("response_target")).toBe("none");
  await expect(page.getByText("No support requests found.")).toBeVisible();
  await expect(reply).toHaveValue("Keep this unsent reply while prioritizing work.");
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(scan.violations.map(row => ({ id: row.id, nodes: row.nodes.map(node => node.target) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("overdue");
  await expect(page.locator(".support-list")).toBeVisible();
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("support-queue-priority.png"), fullPage: true });
  expect(state.writes).toBe(0);
});

test("a delayed target filter cannot overwrite the latest queue selection", async ({ page, context }) => {
  const state = await fixtures(context, "slow"); await page.goto("/admin/support");
  await expect(page.locator(".support-list")).toBeVisible();
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("overdue");
  await expect.poll(() => state.queries.at(-1)?.get("response_target")).toBe("overdue");
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("due_soon");
  await expect(page.getByText("No support requests found.")).toBeVisible();
  const old = page.waitForResponse(response => new URL(response.url()).searchParams.get("response_target") === "overdue");
  state.release(); await old;
  await expect(page.getByText("No support requests found.")).toBeVisible();
  await expect(page.locator(".support-list")).toHaveCount(0);
  expect(state.writes).toBe(0);
});

test("queue failure and explicit refresh preserve an open conversation draft", async ({ page, context }) => {
  const state = await fixtures(context, "failure"); await page.goto(`/admin/support?request=${id}`);
  const reply = page.getByRole("textbox", { name: "Reply shown to customer", exact: true }); await reply.fill("Retain this draft on queue failure.");
  await page.getByRole("combobox", { name: "Response target", exact: true }).selectOption("overdue");
  await expect(page.getByRole("alert").filter({ hasText: "Queue temporarily unavailable" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh list", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Queue temporarily unavailable" })).toHaveCount(0);
  await expect(reply).toHaveValue("Retain this draft on queue failure.");
  expect(state.writes).toBe(0);
});
