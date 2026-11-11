import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const standard = "Standard title checks confirmed by the team before proceeding.";
const published = "Reviewed title checks with literal <img src=x onerror=alert(1)> text, scope confirmed by an advocate. " + "Reference".repeat(25);
const privateReason = "PRIVATE synthetic editorial publication review.";
const service = { id: "service-description-fixture", slug: "title-verification", name: "Title Verification", category: "Buyers", property_types: ["apartment"],
  description: standard, default_description: standard, description_revision: 1, description_customized: false, active: true, paused: false, revision: 1 };

async function fixtures(context: BrowserContext, mode: "normal" | "conflict" | "other_copy" | "history_error" | "public_error" | "agent" = "normal") {
  let current = { ...service }, publicReads = 0, historyReads = 0, empty = false;
  const history: { id: string; at: string; actor: string; previous_description: string; description: string; uses_standard: boolean; revision: number; reason: string }[] = [];
  const state = { publications: [] as { revision: number; description: string | null; standard_description: string | null; confirmed: boolean; reason: string }[], availability: [] as { revision: number }[],
    empty: () => { empty = true; }, pause: () => { current = { ...current, paused: true }; }, historyReads: () => historyReads };
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "catalogue-editor-browser-fixture-only"));
  await context.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,PATCH,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path.endsWith("/auth/me")) return reply({ id: "editor-staff", name: "Fixture Editor", role: mode === "agent" ? "agent" : "admin", mfa_enabled: true, available_for_calls: false });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path === "/api/v1/admin/services") return reply({ items: [current] });
    if (path.endsWith("/description/history")) {
      historyReads++;
      if (mode === "history_error" && historyReads === 1) return reply({ detail: "Publication history unavailable" }, 503);
      const page = Number(url.searchParams.get("page") || 1);
      const rows = mode === "history_error" ? Array.from({ length: 21 }, (_, index) => ({ id: `history-${index}`, at: "2026-11-11T10:00:00Z", actor: "Fixture Editor", previous_description: standard, description: `Synthetic publication ${index}`, uses_standard: false, revision: index+2, reason: privateReason })) : history;
      return reply({ items: rows.slice((page-1)*20, page*20), total: rows.length, page, page_size: 20 });
    }
    if (path.endsWith("/title-verification/history")) return reply({ items: [], total: 0, page: 1, page_size: 20 });
    if (path.endsWith("/title-verification/description") && request.method() === "PATCH") {
      const body = request.postDataJSON(); state.publications.push(body);
      if (mode === "conflict" && state.publications.length === 1) current = { ...current, description_revision: 2, description: "Another administrator published this current copy.", description_customized: true };
      if (body.revision !== current.description_revision) return reply({ detail: "This description changed. Reload the catalogue to review the latest copy." }, 409);
      const previous = current.description;
      current = { ...current, description: body.description ?? standard, description_customized: body.description !== null, description_revision: current.description_revision+1 };
      history.unshift({ id: `publication-${history.length}`, at: "2026-11-11T10:00:00Z", actor: "Fixture Editor", previous_description: previous, description: current.description, uses_standard: body.description === null, revision: current.description_revision, reason: body.reason });
      return reply(current);
    }
    if (path.endsWith("/title-verification") && request.method() === "PATCH") {
      const body = request.postDataJSON(); state.availability.push(body);
      if (mode === "other_copy") current = { ...current, description: "A concurrent administrator published a different description.", description_revision: 2, description_customized: true };
      current = { ...current, paused: body.paused, revision: current.revision+1 }; return reply(current);
    }
    if (path === "/api/v1/services") {
      publicReads++;
      if (mode === "public_error" && publicReads === 1) return reply({ detail: "Catalogue unavailable" }, 503);
      const publicRow = ({ slug, name, category, description, property_types }: typeof service) => ({ slug, name, category, description, property_types });
      return reply({ items: empty ? [] : [...(current.paused ? [] : [publicRow(current)]), publicRow({ ...service, slug: "certified-copy-ec", name: "Certified Copies", category: "Documents", description: "Help coordinating eligible certified document copies." })] });
    }
    return reply({ detail: "No catalogue description fixture" }, 503);
  });
  return state;
}

async function draft(page: import("@playwright/test").Page) {
  const editor = page.getByRole("region", { name: "Service description editor" });
  await editor.getByRole("textbox", { name: "Public description", exact: true }).fill(published);
  await editor.getByRole("textbox", { name: "Private publication reason", exact: true }).fill(privateReason);
  await editor.getByRole("button", { name: "Review description", exact: true }).click();
  return editor;
}

test("reviewed publication and standard restoration preserve the independent availability draft", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/services");
  const availabilityReason = page.getByRole("textbox", { name: "Private operational reason", exact: true });
  await availabilityReason.fill("Keep this unsaved capacity decision.");
  const editor = await draft(page);
  expect(state.publications).toHaveLength(0);
  await expect(editor.locator(".service-description-preview")).toBeFocused();
  await expect(editor.locator(".service-description-preview")).toContainText(published);
  await expect(editor.locator(".service-description-preview img")).toHaveCount(0);
  await editor.getByRole("button", { name: "Publish reviewed description", exact: true }).click();
  await expect(editor.getByRole("status").filter({ hasText: "Description published" })).toBeFocused();
  await expect(availabilityReason).toHaveValue("Keep this unsaved capacity decision.");
  expect(state.publications[0]).toMatchObject({ revision: 1, description: published, confirmed: true });
  expect(state.historyReads()).toBe(0);
  await editor.locator("summary").click(); await expect(editor.getByText(`Private reason: ${privateReason}`, { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Use standard description", exact: true }).click();
  await editor.getByRole("textbox", { name: "Private publication reason", exact: true }).fill("Restore standard copy after editorial review.");
  await editor.getByRole("button", { name: "Review description", exact: true }).click();
  await expect(editor.locator(".service-description-preview")).toContainText(standard); expect(state.publications).toHaveLength(1);
  await editor.getByRole("button", { name: "Publish reviewed description", exact: true }).click();
  await expect(editor.getByText(/Standard catalogue · description revision 3/)).toBeVisible();
  expect(state.publications[1]).toMatchObject({ revision: 2, description: null, standard_description: standard });
  await expect(availabilityReason).toHaveValue("Keep this unsaved capacity decision.");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
});

test("publication conflicts retain edited copy and reason until explicit catalogue reload", async ({ page, context }) => {
  await fixtures(context, "conflict"); await page.goto("/admin/services");
  const editor = await draft(page); await editor.getByRole("button", { name: "Publish reviewed description", exact: true }).click();
  await expect(editor.getByRole("alert")).toContainText("This description changed");
  await editor.getByRole("button", { name: "Back to editing", exact: true }).click();
  await expect(editor.getByRole("textbox", { name: "Public description", exact: true })).toHaveValue(published);
  await expect(editor.getByRole("textbox", { name: "Private publication reason", exact: true })).toHaveValue(privateReason);
  await page.getByRole("button", { name: "Reload catalogue (replaces draft)", exact: true }).click();
  await expect(editor.getByRole("textbox", { name: "Public description", exact: true })).toHaveValue("Another administrator published this current copy.");
});

test("availability saves keep description drafts and cannot silently advance their publication revision", async ({ page, context }) => {
  const state = await fixtures(context, "other_copy"); await page.goto("/admin/services");
  const editor = await draft(page); await editor.getByRole("button", { name: "Back to editing", exact: true }).click();
  await page.getByRole("textbox", { name: "Private operational reason", exact: true }).fill("Pause after reviewing pilot team capacity.");
  await page.getByRole("checkbox").check(); await page.getByRole("button", { name: "Pause new requests", exact: true }).click();
  await expect(page.getByText("New requests paused", { exact: true })).toBeVisible();
  await expect(editor.getByRole("textbox", { name: "Public description", exact: true })).toHaveValue(published);
  await editor.getByRole("button", { name: "Review description", exact: true }).click();
  await editor.getByRole("button", { name: "Publish reviewed description", exact: true }).click();
  await expect(editor.getByRole("alert")).toContainText("This description changed");
  expect(state.publications[0].revision).toBe(1);
});

test("history retry and pagination keep the description draft", async ({ page, context }) => {
  await fixtures(context, "history_error"); await page.goto("/admin/services");
  const editor = page.getByRole("region", { name: "Service description editor" });
  const input = editor.getByRole("textbox", { name: "Public description", exact: true }); await input.fill(published);
  await editor.locator("summary").click(); await expect(editor.getByRole("alert")).toContainText("Publication history unavailable");
  await editor.getByRole("button", { name: "Retry description history", exact: true }).click();
  await expect(editor.getByText("Published: Synthetic publication 0", { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Next publications", exact: true }).click();
  await expect(editor.getByText("Published: Synthetic publication 20", { exact: true })).toBeVisible();
  await expect(input).toHaveValue(published);
});

test("published copy appears as plain text in the searchable catalogue and paused entries disappear on refresh", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/services");
  const editor = await draft(page); await editor.getByRole("button", { name: "Publish reviewed description", exact: true }).click();
  await expect(editor.getByRole("status").filter({ hasText: "Description published" })).toBeVisible();
  await page.goto("/?service=title-verification#callback");
  await expect(page.locator(".callback-form")).toContainText(published);
  await expect(page.locator(".callback-form img")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.goto("/services"); const catalogue = page.getByRole("region", { name: "Services accepting requests", exact: true });
  await expect(catalogue.getByText(published, { exact: true })).toBeVisible();
  await expect(catalogue.locator("img")).toHaveCount(0); await expect(page.getByText(privateReason, { exact: true })).toHaveCount(0);
  await catalogue.getByRole("combobox", { name: "Service category", exact: true }).selectOption("Documents");
  await expect(catalogue.getByRole("article")).toHaveCount(1);
  await catalogue.getByRole("combobox", { name: "Service category", exact: true }).selectOption("all");
  await catalogue.getByRole("searchbox", { name: "Search services", exact: true }).fill("literal");
  await expect(catalogue.getByRole("article")).toHaveCount(1);
  await expect(catalogue.getByRole("link", { name: "Start request for Title Verification ↗", exact: true })).toHaveAttribute("href", "/request?service=title-verification");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("live-service-catalogue.png"), fullPage: true });
  state.pause(); await catalogue.getByRole("button", { name: "Refresh catalogue", exact: true }).click();
  await expect(catalogue.getByText("No services match these filters. Try another category or search.", { exact: true })).toBeVisible();
  await expect(catalogue.getByText(published, { exact: true })).toHaveCount(0);
});

test("public catalogue offers retry and an honest empty state; agents cannot edit descriptions", async ({ page, context }) => {
  const state = await fixtures(context, "public_error"); await page.goto("/services");
  const catalogue = page.getByRole("region", { name: "Services accepting requests", exact: true });
  await expect(catalogue.getByRole("alert")).toBeVisible();
  await catalogue.getByRole("button", { name: "Refresh catalogue", exact: true }).click(); await expect(catalogue.getByRole("article")).toHaveCount(2);
  state.empty(); await catalogue.getByRole("button", { name: "Refresh catalogue", exact: true }).click();
  await expect(catalogue.getByText("No services are accepting new requests right now. Please check again later.", { exact: true })).toBeVisible();
  expect(state.publications).toHaveLength(0);
});

test("agent access never opens the editor", async ({ page, context }) => {
  const state = await fixtures(context, "agent"); await page.goto("/admin/services");
  await expect(page.getByRole("heading", { name: "Administrator access required", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Service description editor" })).toHaveCount(0); expect(state.publications).toHaveLength(0);
});
