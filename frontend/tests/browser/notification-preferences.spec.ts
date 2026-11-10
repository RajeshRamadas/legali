import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

async function fixtures(context: BrowserContext, failure = "") {
  const profile = { name: "Synthetic Customer", phone: "+919999900001", contact: "+919999900001", email: null };
  let saved = { email: true, sms: true, whatsapp: true, revision: 0, updated_at: null as string | null };
  let writes = 0, failed = false, reads = 0;
  await context.addInitScript(profile => localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "preferences-browser-fixture-only", profile })), profile);
  await context.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,PUT,OPTIONS", "access-control-expose-headers": "retry-after" };
    const reply = (json: unknown, status = 200, extra = {}) => route.fulfill({ headers: { ...headers, ...extra }, status, json });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/api/v1/account") return reply({ profile, requests: [], bookings: [], payments: [], payments_mode: "off" });
    if (path === "/api/v1/account/notification-preferences") {
      if (method === "GET") {
        reads++;
        if (failure === "load" && reads === 1) return reply({ detail: "Could not load saved choices." }, 503);
        return reply(saved);
      }
      if (method === "PUT") {
        writes++;
        expect(route.request().headers()["content-type"]).toContain("application/json");
        const choices = route.request().postDataJSON();
        expect(Object.keys(choices).sort()).toEqual(["email", "revision", "sms", "whatsapp"]);
        if (!failed && failure && failure !== "load") {
          failed = true;
          if (failure === "conflict") { saved = { ...saved, sms: false, revision: 1, updated_at: "2026-11-10T05:00:00Z" }; return reply({ detail: "Your choices changed on another device. Reload saved choices." }, 409); }
          if (failure === "rate") return reply({ detail: "Please wait before saving again." }, 429, { "retry-after": "3" });
          return reply({ detail: "Your choices could not be saved. Please retry." }, 503);
        }
        expect(choices.revision).toBe(saved.revision);
        saved = { ...choices, revision: saved.revision + 1, updated_at: "2026-11-10T05:00:00Z" };
        return reply(saved);
      }
    }
    return reply({ detail: "No notification-preferences fixture" }, 503);
  });
  return { writes: () => writes };
}

test("customers save all-channel opt-out, retain sign-in access and see persisted choices", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/account/notifications");
  for (const label of ["Email alerts", "SMS alerts", "WhatsApp alerts"]) {
    await expect(page.getByRole("checkbox", { name: label })).toBeChecked();
    await page.getByRole("checkbox", { name: label }).uncheck();
  }
  expect(state.writes()).toBe(0);
  await expect(page.getByText(/Save to turn off all automated alert channels/)).toBeVisible();
  await expect(page.getByText(/Sign-in codes still arrive/)).toBeVisible();
  await page.getByRole("button", { name: "Save preferences", exact: true }).click();
  const success = page.getByRole("status").filter({ hasText: "Your notification preferences are saved" });
  await expect(success).toBeFocused();
  await expect(page.getByText(/All automated alert channels are off/)).toBeVisible();
  expect(state.writes()).toBe(1);
  await expect(page.getByRole("button", { name: "Save preferences", exact: true })).toBeDisabled();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await test.info().attach("notification-preferences", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
  await page.reload();
  for (const label of ["Email alerts", "SMS alerts", "WhatsApp alerts"]) await expect(page.getByRole("checkbox", { name: label })).not.toBeChecked();
});

test("another-device conflict preserves the draft until explicit reload", async ({ page, context }) => {
  await fixtures(context, "conflict"); await page.goto("/account/notifications");
  await page.getByRole("checkbox", { name: "Email alerts" }).uncheck();
  await page.getByRole("button", { name: "Save preferences", exact: true }).click();
  await expect(page.getByRole("region", { name: "Automated alert choices" }).getByRole("alert")).toBeFocused();
  await expect(page.getByRole("checkbox", { name: "Email alerts" })).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "SMS alerts" })).toBeChecked();
  await expect(page.getByRole("button", { name: "Save preferences", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Reload saved choices", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Email alerts" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "SMS alerts" })).not.toBeChecked();
});

for (const failure of ["retry", "rate"]) test(`${failure}: failed save retains the chosen channels for a deliberate retry`, async ({ page, context }) => {
  const state = await fixtures(context, failure); await page.goto("/account/notifications");
  await page.getByRole("checkbox", { name: "SMS alerts" }).uncheck();
  await page.getByRole("button", { name: "Save preferences", exact: true }).click();
  await expect(page.getByRole("region", { name: "Automated alert choices" }).getByRole("alert")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "SMS alerts" })).not.toBeChecked();
  if (failure === "rate") await expect(page.getByRole("button", { name: /Try again in \d+s/ })).toBeDisabled();
  const save = page.getByRole("button", { name: "Save preferences", exact: true });
  await expect(save).toBeEnabled(); await save.click();
  await expect(page.getByRole("status").filter({ hasText: "Your notification preferences are saved" })).toBeVisible();
  expect(state.writes()).toBe(2);
});

test("failed initial load has an explicit retry and cannot submit defaults", async ({ page, context }) => {
  await fixtures(context, "load"); await page.goto("/account/notifications");
  await expect(page.getByRole("region", { name: "Automated alert choices" }).getByRole("alert")).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry loading choices", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Email alerts" })).toBeChecked();
});

test("signed-out visitors see sign-in without private settings", async ({ page }) => {
  await page.goto("/account/notifications");
  await expect(page.getByRole("heading", { name: "Sign in with your phone" })).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(page.getByRole("main")).toHaveCount(1);
});
