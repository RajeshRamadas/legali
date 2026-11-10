import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const id = "694e5e08-ae26-4db8-9eea-6e43ce7be654";
const profile = { name: "Asha Fixture", phone: "+919999900001", contact: "+919999900001", email: null };
const subject = "Please review this support question";

async function fixtures(context: BrowserContext, { race = false, failOnce = false } = {}) {
  await context.addInitScript(profile => localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "unread-support-fixture", profile })), profile);
  let updates = 1, read = 0, failures = failOnce ? 1 : 0;
  const marks: number[] = [];
  const record = () => ({ id, reference: "SR-FIXTURE", kind: "complaint", subject,
    details: "Synthetic original description for the support team.", status: "in_progress", revision: updates+1,
    ticket_number: null, created_at: "2026-11-10T08:00:00Z", updated_at: "2026-11-10T09:00:00Z", reply_due_at: null, overdue: false, resolved_at: null,
    customer_update_revision: updates, customer_read_revision: read, unread_replies: updates-read });
  await context.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path === "/api/v1/account") return route.fulfill({ headers, json: { profile, requests: [], bookings: [], payments: [], payments_mode: "off" } });
    if (path.endsWith("/support-requests/unread")) return route.fulfill({ headers, json: { requests: updates > read ? 1 : 0, unread_replies: updates-read } });
    if (path.endsWith("/read")) {
      const revision = request.postDataJSON().through_revision; marks.push(revision);
      if (failures) { failures--; return route.fulfill({ headers, status: 503, json: { detail: "Read status could not be saved." } }); }
      if (race) updates = 2;
      read = Math.max(read, revision);
      return route.fulfill({ headers, json: record() });
    }
    if (path.endsWith(`/${id}/messages`)) return route.fulfill({ headers, json: {
      items: Array.from({ length: updates }, (_, index) => ({ id: `reply-${index}`, body: `Synthetic visible staff response ${index+1}.`, author_type: "staff", visibility: "customer", created_at: `2026-11-10T09:0${index}:00Z` })),
      total: updates, page: 1, page_size: 20, customer_update_revision: updates,
    } });
    if (path.endsWith(`/${id}`)) return route.fulfill({ headers, json: record() });
    if (path.endsWith("/support-requests")) return route.fulfill({ headers, json: { items: [record()], total: 1, page: 1, page_size: 20 } });
    return route.fulfill({ headers, status: 503, json: { detail: "No unread-support browser fixture" } });
  });
  return marks;
}

test("customer sees unread alerts and read receipt preserves an unsent reply", async ({ page, context }) => {
  const marks = await fixtures(context);
  await page.goto("/account/support");
  await expect(page.getByRole("button", { name: "Notifications (1)", exact: true })).toBeVisible();
  await page.getByRole("button", { name: new RegExp(subject) }).click();
  await expect(page.getByText("Synthetic visible staff response 1.", { exact: true })).toBeVisible();
  expect(marks).toEqual([]); // Viewing a request alone cannot erase unread replies.
  const draft = page.getByRole("textbox", { name: "Your reply", exact: true });
  await draft.fill("Keep this unsent customer reply while marking read.");
  await page.getByRole("button", { name: "Mark request as read", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Support replies marked as read" })).toBeFocused();
  await expect(draft).toHaveValue("Keep this unsent customer reply while marking read.");
  await expect(page.getByRole("button", { name: "Notifications (0)", exact: true })).toBeVisible();
  expect(marks).toEqual([1]);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("support-read.png"), fullPage: true });
});

test("new response during read stays unread until explicitly reloaded", async ({ page, context }) => {
  const marks = await fixtures(context, { race: true });
  await page.goto("/account/support");
  await page.getByRole("button", { name: new RegExp(subject) }).click();
  const draft = page.getByRole("textbox", { name: "Your reply", exact: true });
  await draft.fill("Keep this draft while a newer response arrives.");
  await page.getByRole("button", { name: "Mark request as read", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Newer replies remain unread" })).toBeVisible();
  await expect(draft).toHaveValue("Keep this draft while a newer response arrives.");
  await expect(page.getByRole("button", { name: "Mark request as read", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Notifications (1)", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reload conversation", exact: true }).click();
  await expect(page.getByText("Synthetic visible staff response 2.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Mark request as read", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Support replies marked as read" })).toBeVisible();
  expect(marks).toEqual([1,2]);
});

test("failed read receipt keeps badge, draft and retry watermark", async ({ page, context }) => {
  const marks = await fixtures(context, { failOnce: true });
  await page.goto("/account/support"); await page.getByRole("button", { name: new RegExp(subject) }).click();
  const draft = page.getByRole("textbox", { name: "Your reply", exact: true });
  await draft.fill("This reply must survive a failed read receipt.");
  const read = page.getByRole("button", { name: "Mark request as read", exact: true });
  await read.click();
  await expect(page.getByRole("alert").filter({ hasText: "Read status could not be saved" })).toBeVisible();
  await expect(draft).toHaveValue("This reply must survive a failed read receipt.");
  await expect(page.getByRole("button", { name: "Notifications (1)", exact: true })).toBeVisible();
  await read.click();
  await expect(page.getByRole("status").filter({ hasText: "Support replies marked as read" })).toBeVisible();
  expect(marks).toEqual([1,1]);
});
