import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page, type Locator } from "@playwright/test";

const profile = { name: "Asha Customer", phone: "+919876543210", email: null, contact: "+919876543210" };

// UI fixtures exercise real page components without contacting providers or a live database.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/account") return route.fulfill({ headers, json: { profile, requests: [], bookings: [], payments: [], payments_mode: "off" } });
    if (path === "/auth/me") return route.fulfill({ headers, json: { id: "browser-staff", name: "Meera Admin", role: "admin", email: "staff@example.invalid", phone: null, available_for_calls: false, mfa_enabled: true } });
    if (path === "/admin/urgent") return route.fulfill({ headers, json: { items: [] } });
    if (path === "/admin/case-alerts") return route.fulfill({ headers, json: { items: [], total: 0, unacknowledged: 0, escalated: 0, page: 1, page_size: 25 } });
    if (path === "/tickets" && route.request().method() === "POST") return route.fulfill({ headers, status: 201, json: { ticket_number: "HX-BROWSER-0001", message: "A specialist will contact you." } });
    return route.fulfill({ headers, status: 503, json: { detail: `No browser fixture for ${path}` } });
  });
});

async function customer(page: Page) {
  await page.addInitScript(value => localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "browser-fixture-only", profile: value })), profile);
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: /Asha/ })).toBeVisible();
}

async function staff(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "browser-fixture-only"));
  await page.goto("/admin/alerts");
  await expect(page.getByRole("heading", { name: "No unacknowledged deadline alerts" })).toBeVisible();
}

async function accessible(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  await test.info().attach("axe-accessibility.json", { body: Buffer.from(JSON.stringify(result, null, 2)), contentType: "application/json" });
  expect(result.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
}

async function contained(page: Page, dialog: Locator) {
  const first = dialog.locator('button,a[href],input,select,textarea').filter({ visible: true }).first();
  await first.focus();
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Tab");
  await expect(first).toBeFocused();
}

for (const path of ["/", "/services", "/account", "/documents", "/bookings", "/request", "/admin"]) {
  test(`public ${path}: main landmark, skip link, accessibility and viewport`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("#main-content")).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await accessible(page);
  });
}

test("public mobile navigation supports keyboard entry, Escape and outside dismissal", async ({ page }, info) => {
  test.skip(info.project.name === "desktop", "Mobile disclosure only");
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "Open navigation" });
  await expect(toggle).toBeEnabled();
  await toggle.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await page.mouse.click(4, 600); // Below the dropdown, away from page links.
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "All services" }).click();
  await expect(page).toHaveURL(/\/services$/);
  await expect(page.getByRole("button", { name: "Open navigation" })).toHaveAttribute("aria-expanded", "false");
});

test("callback confirmation contains focus, blocks the background and restores its trigger", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Full name", { exact: true }).fill("Asha Customer");
  await page.getByLabel("Phone number", { exact: true }).fill("9876543210");
  await page.getByLabel("Property location", { exact: true }).fill("Bengaluru");
  const submit = page.getByRole("button", { name: "Request free callback" });
  await submit.click();
  const dialog = page.getByRole("dialog", { name: "Thanks, Asha." });
  await expect(dialog).toBeVisible();
  await contained(page, dialog);
  await submit.evaluate(node => (node as HTMLElement).focus());
  expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
  await accessible(page);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(submit).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
});

test("assistant opens at its input and returns focus on Escape", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Need help?" });
  await trigger.click();
  await expect(page.getByRole("textbox", { name: "Type your question" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(page.getByRole("region", { name: "Homexo Legal assistant" })).not.toBeVisible();
});

test("sample report supports keyboard dismissal and focus restoration", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "See a sample report" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: /A finding. The evidence./ });
  await expect(dialog).toBeVisible();
  await contained(page, dialog);
  await accessible(page);
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

for (const [area, load] of [["Customer portal", customer], ["Staff workspace", staff]] as const) {
  test(`${area}: landmark, mobile drawer, search and notification keyboard behavior`, async ({ page }, info) => {
    await load(page);
    await expect(page.getByRole("main")).toHaveCount(1);
    await accessible(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    if (info.project.name !== "desktop") {
      const toggle = page.getByRole("button", { name: "Open navigation" });
      await toggle.click();
      const drawer = page.getByRole("dialog", { name: `${area} navigation` });
      await expect(drawer).toBeVisible();
      await contained(page, drawer);
      await accessible(page);
      await page.keyboard.press("Escape");
      await expect(toggle).toBeFocused();
      await expect(drawer).not.toBeVisible();

      const search = page.getByRole("button", { name: "Open search" });
      await search.click();
      const searchDialog = page.getByRole("dialog", { name: "Search workspace" });
      await expect(searchDialog.getByRole("textbox")).toBeFocused();
      await contained(page, searchDialog);
      await page.keyboard.press("Escape");
      await expect(search).toBeFocused();

      // Leaving the mobile breakpoint must dismiss the modal and release scroll locking.
      const viewport = page.viewportSize()!;
      await toggle.click();
      await expect(drawer).toBeVisible();
      await page.setViewportSize({ width: 1440, height: 1000 });
      await expect(drawer).not.toBeVisible();
      await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
      await expect(page.getByRole("navigation", { name: area, exact: true })).toBeVisible();
      await page.setViewportSize(viewport);
    }
    await page.keyboard.press("Control+k");
    const query = page.getByRole("textbox", { name: /Search requests|Search tickets/ });
    await expect(query).toBeFocused();
    await page.keyboard.press("Escape");
    const bell = page.getByRole("button", { name: "Notifications (0)" });
    await bell.click();
    await expect(page.getByRole("region", { name: "Notifications" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(bell).toBeFocused();
    await expect(bell).toHaveAttribute("aria-expanded", "false");
    await bell.click();
    await expect(page.getByRole("region", { name: "Notifications" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(bell).toHaveAttribute("aria-expanded", "false");
  });
}

test("reduced motion disables smooth scrolling and callback jumps", async ({ page }) => {
  await page.goto("/");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
  await page.evaluate(() => {
    const callback = document.getElementById("callback")!;
    callback.scrollIntoView = options => {
      callback.dataset.scrollBehavior = typeof options === "object" ? options.behavior : undefined;
    };
  });
  await page.getByRole("button", { name: "Start property review", exact: true }).first().click();
  await expect(page.locator("#callback")).toHaveAttribute("data-scroll-behavior", "auto");
});
