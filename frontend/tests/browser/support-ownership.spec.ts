import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const me = "8e45ea9a-e6f5-43dc-8dbf-11018d46dc21", other = "1e1dd5cc-55ef-4a64-8854-c39cd9155531";
const id = "316fb188-309e-4c19-94a4-e67d559219ce", subject = "Ownership fixture support request";
const people = [{ id: me, name: "Fixture Administrator" }, { id: other, name: "Second Administrator" }];

async function fixtures(context: BrowserContext, mode: "normal" | "conflict" | "assigned" | "agent" = "normal") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "support-ownership-ui-fixture"));
  let record = { id, reference: "SR-OWNER-FIXTURE", subject, details: "Synthetic request details, never live customer information.", kind: "complaint", status: "open", revision: 1,
    ticket_number: null, created_at: "2026-11-10T08:00:00Z", updated_at: "2026-11-10T08:00:00Z", reply_due_at: "2026-11-09T08:00:00Z", resolved_at: null,
    overdue: true, customer: { name: "Synthetic Customer", phone_last4: "0001" }, assignee: mode === "assigned" ? { ...people[0], active: true } : null as { id: string; name: string; active: boolean } | null };
  const assignments: { id: string; actor: string; at: string; revision: number; previous_owner: { id: string; name: string } | null; owner: { id: string; name: string } | null }[] = [];
  const state = { ownerWrites: [] as { revision: number; assignee_user_id: string | null }[], replyRevisions: [] as number[], filters: [] as string[], rosterReads: 0 };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,PATCH,OPTIONS" };
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path === "/api/v1/auth/me") return route.fulfill({ headers, json: { ...people[0], role: mode === "agent" ? "agent" : "admin", email: "staff@example.invalid", account_status: "active", available_for_calls: false, mfa_enabled: true } });
    if (path.endsWith("/admin/urgent")) return route.fulfill({ headers, json: { items: [] } });
    if (path.endsWith("/admin/case-alerts")) return route.fulfill({ headers, json: { items: [], unacknowledged: 0 } });
    if (path.endsWith("/support-requests/owners")) { state.rosterReads++; return route.fulfill({ headers, json: { items: people } }); }
    if (path.endsWith("/assignments")) return route.fulfill({ headers, json: { items: assignments, total: assignments.length, page: 1, page_size: 20 } });
    if (path.endsWith("/assignment")) {
      const body = request.postDataJSON(); state.ownerWrites.push(body);
      if (mode === "conflict") {
        record = { ...record, assignee: { ...people[1], active: true }, revision: 2 };
        return route.fulfill({ headers, status: 409, json: { detail: "This request or its ownership changed. Reload the latest request." } });
      }
      if (body.revision !== record.revision) return route.fulfill({ headers, status: 409, json: { detail: "Stale ownership revision" } });
      const person = people.find(person => person.id === body.assignee_user_id) ?? null;
      assignments.unshift({ id: `assignment-${assignments.length}`, actor: people[0].name, at: record.created_at, revision: record.revision+1, previous_owner: record.assignee, owner: person });
      record = { ...record, assignee: person ? { ...person, active: true } : null, revision: record.revision+1 };
      return route.fulfill({ headers, json: record });
    }
    if (path.endsWith(`/${id}`) && request.method() === "PATCH") {
      const body = request.postDataJSON(); state.replyRevisions.push(body.revision);
      if (body.revision !== record.revision) return route.fulfill({ headers, status: 409, json: { detail: "Stale reply revision" } });
      record = { ...record, revision: record.revision+1, status: body.status };
      return route.fulfill({ headers, json: record });
    }
    if (path.endsWith("/messages")) return route.fulfill({ headers, json: { items: [], total: 0, page: 1, page_size: 20 } });
    if (path.endsWith(`/${id}`)) return route.fulfill({ headers, json: record });
    if (path.endsWith("/admin/support-requests")) {
      const filter = url.searchParams.get("assignee") || "all"; state.filters.push(filter);
      const visible = filter === "all" || (filter === "unassigned" ? !record.assignee : record.assignee?.id === (filter === "me" ? me : filter));
      return route.fulfill({ headers, json: { items: visible ? [record] : [], total: visible ? 1 : 0, page: 1, page_size: 20, overdue: 1, filtered_overdue: visible ? 1 : 0 } });
    }
    return route.fulfill({ headers, status: 503, json: { detail: "No support ownership fixture" } });
  });
  return state;
}

test("assignment keeps reply/private-note drafts and advances the saved review revision", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/support");
  await page.getByRole("button", { name: new RegExp(subject) }).click();
  const reply = page.getByRole("textbox", { name: "Reply shown to customer", exact: true });
  const note = page.getByRole("textbox", { name: "Internal note (administrators only)", exact: true });
  await reply.fill("Keep this unsent response when ownership changes."); await note.fill("Keep this private administrator note as well.");
  await page.getByRole("button", { name: "Assign to me", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Support owner saved" })).toBeFocused();
  await expect(reply).toHaveValue("Keep this unsent response when ownership changes.");
  await expect(note).toHaveValue("Keep this private administrator note as well.");
  expect(state.ownerWrites).toEqual([{ revision: 1, assignee_user_id: me }]);
  await page.locator(".support-assignment summary").click();
  await expect(page.locator(".support-assignment-history")).toContainText("Unassigned → Fixture Administrator");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("support-owner.png"), fullPage: true });
  await page.getByRole("button", { name: "Save support update", exact: true }).click();
  await expect.poll(() => state.replyRevisions).toEqual([2]);
});

test("ownership conflict keeps the selection and conversation draft until explicit reload", async ({ page, context }) => {
  await fixtures(context, "conflict"); await page.goto("/admin/support");
  await page.getByRole("button", { name: new RegExp(subject) }).click();
  const owner = page.getByRole("combobox", { name: "Assign support owner", exact: true });
  await owner.selectOption(me);
  const reply = page.getByRole("textbox", { name: "Reply shown to customer", exact: true });
  await reply.fill("A draft which must not vanish after an ownership conflict.");
  await page.getByRole("button", { name: "Save support owner", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "ownership changed" })).toBeVisible();
  await expect(owner).toHaveValue(me); await expect(reply).toHaveValue("A draft which must not vanish after an ownership conflict.");
  await page.getByRole("button", { name: "Reload latest request", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Assign support owner", exact: true })).toHaveValue(other);
});

test("owner queue filters show owned and unassigned work independently", async ({ page, context }) => {
  const state = await fixtures(context, "assigned"); await page.goto("/admin/support");
  await expect(page.getByRole("button", { name: new RegExp(subject) })).toBeVisible();
  await page.getByRole("combobox", { name: "Owner", exact: true }).selectOption("unassigned");
  await expect(page.getByText("No support requests found.")).toBeVisible();
  await page.getByRole("combobox", { name: "Owner", exact: true }).selectOption("me");
  await expect(page.getByRole("button", { name: new RegExp(subject) })).toBeVisible();
  expect(state.filters).toContain("unassigned"); expect(state.filters).toContain("me");
  await page.getByRole("combobox", { name: "Owner", exact: true }).selectOption(other);
  await expect(page.getByText("No support requests found.")).toBeVisible();
  expect(state.filters).toContain(other);
});

test("agents cannot open ownership controls or fetch administrator choices", async ({ page, context }) => {
  const state = await fixtures(context, "agent"); await page.goto("/admin/support");
  await expect(page.getByText("Administrator access is required to review support requests.")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Assign support owner", exact: true })).toHaveCount(0);
  expect(state.rosterReads).toBe(0);
});
