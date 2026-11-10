import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

async function fixtures(context: BrowserContext, role = "admin", ownProfile = false) {
  const review = { id: "review-fixture", rating: 1, comment: "The advice could have been clearer. <script>not executable</script>", reviewer_name: "Asha S.",
    created_at: "2026-11-10T00:00:00Z", updated_at: "2026-11-10T00:00:00Z", status: "pending", revision: 1,
    ticket_number: "HX-REVIEW-FIXTURE", lawyer: { id: ownProfile ? "moderator-fixture" : "lawyer-fixture", name: "Synthetic Advocate" } };
  const history: Record<string, unknown>[] = [];
  let conflict = false, saves = 0;
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "review-browser-fixture-only"));
  await context.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url()), path = url.pathname.replace("/api/v1", ""), method = route.request().method();
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,PATCH,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, status, json });
    if (method === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path === "/auth/me") return reply({ id: "moderator-fixture", name: "Synthetic Moderator", role, mfa_enabled: true, available_for_calls: false });
    if (path === "/admin/urgent") return reply({ items: [] });
    if (path === "/admin/case-alerts") return reply({ items: [], total: 0, unacknowledged: 0, escalated: 0 });
    if (path === "/admin/reviews") {
      const matches = ["all", review.status].includes(url.searchParams.get("status") || "pending");
      return reply({ items: matches ? [review] : [], counts: { pending: review.status === "pending" ? 1 : 0, published: review.status === "published" ? 1 : 0, hidden: review.status === "hidden" ? 1 : 0 }, total: matches ? 1 : 0, page: 1, page_size: 20 });
    }
    if (path === "/admin/reviews/review-fixture" && method === "GET") return reply({ review, history, total: history.length, page: 1, page_size: 20 });
    if (path === "/admin/reviews/review-fixture" && method === "PATCH") {
      saves++;
      if (conflict) { conflict = false; review.revision++; review.status = "hidden"; return reply({ detail: "This review changed. Reload before deciding." }, 409); }
      const body = route.request().postDataJSON();
      expect(body.revision).toBe(review.revision);
      expect(body.reviewed).toBe(true);
      expect(body).not.toHaveProperty("comment"); expect(body).not.toHaveProperty("rating");
      history.unshift({ id: `history-${review.revision}`, from_status: review.status, to_status: body.status, reason: body.reason, note: body.note, revision: ++review.revision, actor: "Synthetic Moderator", created_at: review.updated_at });
      review.status = body.status;
      return reply(review);
    }
    return reply({ detail: "No review browser fixture for this request." }, 503);
  });
  return { review, history, conflictNext: () => { conflict = true; }, saves: () => saves };
}

test("an administrator can publish critical feedback and hide it with a private decision trail", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/admin/reviews");
  await page.getByRole("button", { name: "Review feedback" }).click();
  const note = page.getByLabel("Private decision note");
  await note.fill("Checked against publication policy, including privacy.");
  await expect(page.getByRole("button", { name: "Save moderation decision" })).toBeDisabled();
  await page.getByRole("checkbox", { name: "I reviewed this feedback" }).check();
  await page.getByRole("button", { name: "Save moderation decision" }).click();
  await expect(page.getByText(/Published · editing revision 2/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review decision", exact: true })).toBeFocused();
  await expect(page.getByRole("status").filter({ hasText: "Moderation decision saved" })).toBeVisible();
  expect(state.review.rating).toBe(1);
  expect(state.review.comment).toContain("<script>not executable</script>");
  await page.getByLabel("Private decision note").fill("Withheld while checking confidential case details.");
  await page.getByRole("checkbox", { name: "I reviewed this feedback" }).check();
  await page.getByRole("button", { name: "Save moderation decision" }).click();
  await expect(page.getByText(/Not published · editing revision 3/)).toBeVisible();
  expect(state.history).toHaveLength(2);
  const report = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(report.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await test.info().attach("review-moderation", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
});

test("a conflicting decision keeps the private draft until the administrator reloads", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/admin/reviews"); await page.getByRole("button", { name: "Review feedback" }).click();
  const note = page.getByLabel("Private decision note");
  await note.fill("Keep this unsaved private decision.");
  await page.getByRole("checkbox", { name: "I reviewed this feedback" }).check(); state.conflictNext();
  await page.getByRole("button", { name: "Save moderation decision" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "This review changed" })).toContainText("Your draft is kept here");
  await expect(note).toHaveValue("Keep this unsaved private decision.");
  await page.getByRole("button", { name: "Reload review (replaces draft)" }).click();
  await expect(note).toHaveValue(""); await expect(page.getByText(/editing revision 2/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review decision", exact: true })).toBeFocused();
});

test("agents cannot open moderation controls", async ({ page, context }) => {
  const state = await fixtures(context, "agent"); await page.goto("/admin/reviews");
  await expect(page.getByText("Administrator access is required.")).toBeVisible();
  await expect(page.getByLabel("Private decision note")).toHaveCount(0);
  expect(state.saves()).toBe(0);
});

test("administrators cannot moderate feedback about their own lawyer profile", async ({ page, context }) => {
  const state = await fixtures(context, "admin", true); await page.goto("/admin/reviews");
  await page.getByRole("button", { name: "Review feedback" }).click();
  await expect(page.getByText("Another administrator must moderate reviews of your own profile.")).toBeVisible();
  await expect(page.getByLabel("Private decision note")).toHaveCount(0);
  expect(state.saves()).toBe(0);
});

test("the customer sees publication status without internal moderation notes", async ({ page, context }) => {
  const profile = { name: "Synthetic Customer", phone: "+919999900001", contact: "+919999900001", email: null };
  const booking = { ticket_number: "HX-REVIEW-FIXTURE", status: "completed", status_label: "Completed", issue: "Synthetic consultation", fee: null,
    lawyer: { name: "Synthetic Advocate", initials: "SA", slug: null, headline: "Property law" },
    meeting: { id: "meeting-fixture", status: "completed", starts_at: "2026-01-01T09:00:00Z", ends_at: "2026-01-01T09:30:00Z", when: "1 January, 2:30 pm", meet_link: null },
    can_change: false, can_review: false, payment: null, review: { rating: 1, comment: "The advice could have been clearer.", reviewer_name: "Synthetic C.", at: "2026-01-01T10:00:00Z", moderation_status: "pending" } };
  await context.addInitScript(value => localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "synthetic-customer", profile: value })), profile);
  await context.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/api/v1/account") return route.fulfill({ headers, json: { profile, requests: [], bookings: [booking], payments: [], payments_mode: "off" } });
    if (path === "/api/v1/bookings/lookup") return route.fulfill({ headers, json: booking });
    return route.fulfill({ headers, status: 503, json: { detail: "No customer browser fixture" } });
  });
  await page.goto("/bookings");
  await expect(page.getByRole("status").filter({ hasText: "Waiting for review" })).toContainText("private until it is published");
  await expect(page.getByText("Private decision history")).toHaveCount(0);
  booking.review.moderation_status = "hidden";
  await page.reload();
  await expect(page.getByRole("status").filter({ hasText: "Not published" })).toBeVisible();
});
