import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

test.use({ timezoneId: "Asia/Kolkata" });
const user = { id: "staff-fixture", name: "Synthetic Administrator", email: "staff@example.invalid", role: "admin", account_status: "active", available_for_calls: false };
const period = { id: "period-fixture", starts_at: "2030-01-02T03:30:00Z", ends_at: "2030-01-02T12:30:00Z", reason: "Synthetic private planned absence.", cancelled_at: null as string | null };

async function fixtures(context: BrowserContext, conflict = false, role = "admin") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "time-off-ui-fixture"));
  let saved: typeof period | null = null;
  const writes: Record<string, unknown>[] = [];
  await context.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path === "/api/v1/auth/me") return route.fulfill({ headers, json: { ...user, role } });
    if (path === "/api/v1/admin/urgent") return route.fulfill({ headers, json: { items: [] } });
    if (path === "/api/v1/admin/case-alerts") return route.fulfill({ headers, json: { items: [], unacknowledged: 0 } });
    if (path === "/api/v1/admin/staff") return route.fulfill({ headers, json: { items: [user, { ...user, id: "other-fixture", name: "Synthetic Advocate" }] } });
    if (path === "/api/v1/admin/time-off" && request.method() === "GET") return route.fulfill({ headers, json: { items: saved ? [saved] : [], total: saved ? 1 : 0, page_size: 20, timezone: "Asia/Kolkata", name: url.searchParams.has("user_id") ? "Synthetic Advocate" : user.name } });
    if (path === "/api/v1/admin/time-off" && request.method() === "POST") {
      const body = request.postDataJSON(); writes.push(body);
      if (conflict) return route.fulfill({ headers, status: 409, json: { detail: "A scheduled meeting overlaps this period. Move or cancel it first." } });
      saved = { ...period, starts_at: body.starts_at, ends_at: body.ends_at, reason: body.reason };
      return route.fulfill({ headers, status: 201, json: saved });
    }
    if (path.endsWith("/cancel")) {
      saved = { ...saved!, cancelled_at: new Date().toISOString() };
      return route.fulfill({ headers, json: saved });
    }
    return route.fulfill({ headers, status: 503, json: { detail: "No time-off UI fixture" } });
  });
  return writes;
}

test("confirmed time off saves device timezone correctly and cancellation requires confirmation", async ({ page, context }) => {
  const writes = await fixtures(context);
  await page.goto("/admin/time-off");
  await expect(page.getByText("No time off recorded.")).toBeVisible();
  await page.getByLabel("Unavailable from").fill("2030-01-02T09:00");
  await page.getByLabel("Available again").fill("2030-01-02T18:00");
  await page.getByRole("textbox", { name: "Private reason", exact: true }).fill(period.reason);
  const submit = page.getByRole("button", { name: "Save time off", exact: true });
  await expect(submit).toBeDisabled();
  await page.getByRole("checkbox").check(); await submit.click();
  await expect(page.getByRole("status").filter({ hasText: "Time off saved." })).toBeFocused();
  expect(writes).toHaveLength(1); expect(writes[0].starts_at).toBe("2030-01-02T03:30:00.000Z");
  await expect(page.getByText(period.reason, { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("time-off.png"), fullPage: true });
  await page.getByRole("button", { name: "Cancel time off", exact: true }).click();
  await page.getByRole("button", { name: "Keep time off", exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirm cancellation" })).toHaveCount(0);
  await page.getByRole("button", { name: "Cancel time off", exact: true }).click();
  await page.getByRole("button", { name: "Confirm cancellation" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Time off cancelled." })).toBeFocused();
  await expect(page.getByRole("button", { name: "Cancel time off", exact: true })).toHaveCount(0);
});

test("overlap failure keeps the private draft and confirmation", async ({ page, context }) => {
  await fixtures(context, true); await page.goto("/admin/time-off");
  await expect(page.getByText("No time off recorded.")).toBeVisible();
  await page.getByLabel("Unavailable from").fill("2030-01-02T09:00");
  await page.getByLabel("Available again").fill("2030-01-02T18:00");
  await page.getByRole("textbox", { name: "Private reason", exact: true }).fill(period.reason);
  await page.getByRole("checkbox").check(); await page.getByRole("button", { name: "Save time off", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Move or cancel it first" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Private reason", exact: true })).toHaveValue(period.reason);
  await expect(page.getByRole("checkbox")).toBeChecked();
});

test("agents manage their own time off without a staff selector", async ({ page, context }) => {
  await fixtures(context, false, "agent"); await page.goto("/admin/time-off");
  await expect(page.getByText("No time off recorded.")).toBeVisible();
  await expect(page.getByLabel("Staff member", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save time off", exact: true })).toBeDisabled();
});
