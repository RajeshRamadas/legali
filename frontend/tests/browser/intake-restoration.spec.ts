import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext, type Page } from "@playwright/test";

const oldQuestions = [{ id: "b26fb188-309e-4c19-94a4-e67d559219ce", prompt: "Original timing question?", help: "Approximate timing is enough.", kind: "text", required: false, max_length: 200, options: [] as string[] }];
const currentQuestions = [{ ...oldQuestions[0], prompt: "Current timing question?" }];
const reason = "Restore the original form after operational review.";

async function fixtures(context: BrowserContext, mode: "normal" | "conflict" | "source_changed" | "agent" | "retired" = "normal") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "form-restore-browser-fixture-only"));
  let current = { slug: "title-verification", name: "Title Verification", active: mode !== "retired", revision: 3, questions: structuredClone(currentQuestions) };
  const event = (revision: number, questions: typeof oldQuestions, previous_questions: typeof oldQuestions, restored_from_revision: number | null = null) => ({ id: `history-${revision}`, actor: "Fixture Administrator", at: "2026-11-11T13:00:00Z", revision, questions, previous_questions, reason: "Synthetic original publication review.", restored_from_revision });
  const history = [event(3, currentQuestions, oldQuestions), event(2, oldQuestions, [])];
  const state = { restores: [] as { revision: number; source_revision: number; preview_questions: typeof oldQuestions; confirmed: boolean; reason: string }[], publications: [] as { revision: number; questions: typeof oldQuestions }[] };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,PATCH,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path.endsWith("/auth/me")) return reply({ id: "restore-staff", name: "Fixture Administrator", role: mode === "agent" ? "agent" : "admin", mfa_enabled: true, available_for_calls: false });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path === "/api/v1/admin/intake-forms") return reply({ items: [current] });
    if (path.endsWith("/title-verification/history")) return reply({ items: history, total: history.length, page: 1, page_size: 20 });
    if (path.endsWith("/title-verification/restore") && request.method() === "POST") {
      const body = request.postDataJSON(); state.restores.push(body);
      if (mode === "conflict" && state.restores.length === 1) current = { ...current, revision: 4, questions: [{ ...currentQuestions[0], prompt: "Concurrent administrator question?" }] };
      if (body.revision !== current.revision) return reply({ detail: "This form changed. Reload the published form before saving again." }, 409);
      if (mode === "source_changed") return reply({ detail: "The retained questions differ from your preview. Reload history and review again." }, 409);
      const questions = body.source_revision === 1 ? [] : oldQuestions;
      if (JSON.stringify(body.preview_questions) !== JSON.stringify(questions)) return reply({ detail: "Preview mismatch in fixture" }, 409);
      const previous = current.questions; current = { ...current, revision: current.revision+1, questions: structuredClone(questions) };
      history.unshift({ ...event(current.revision, questions, previous, body.source_revision), reason: body.reason });
      return reply(current);
    }
    if (path.endsWith("/title-verification") && request.method() === "PATCH") {
      const body = request.postDataJSON(); state.publications.push(body);
      if (body.revision !== current.revision) return reply({ detail: "Stale editor revision" }, 409);
      const previous = current.questions; current = { ...current, revision: current.revision+1, questions: body.questions };
      history.unshift(event(current.revision, current.questions, previous)); return reply(current);
    }
    return reply({ detail: "No form restoration browser fixture" }, 503);
  });
  return state;
}

async function source(page: Page, revision = 2) {
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  await editor.locator("summary").filter({ hasText: "Private form publication history" }).click();
  return editor.locator(".intake-form-publication").filter({ has: page.getByRole("heading", { name: `Version ${revision}`, exact: true }) });
}

test("restore preview and cancellation preserve editor changes without publishing", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/intake-forms");
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  const question = editor.getByRole("textbox", { name: "Question text", exact: true }); await question.fill("Keep this unpublished question draft?");
  const draftReason = editor.getByRole("textbox", { name: "Private publication reason", exact: true }); await draftReason.fill("Keep this private draft publication reason.");
  const original = await source(page); const trigger = original.getByRole("button", { name: "Review restoration of version 2", exact: true }); await trigger.click();
  const preview = editor.getByRole("region", { name: "Restoration question preview" }); await expect(preview).toBeFocused();
  await expect(preview).toContainText("Original timing question?"); await expect(question).toBeDisabled(); expect(state.restores).toHaveLength(0);
  await editor.getByRole("button", { name: "Cancel restoration", exact: true }).click();
  await expect(trigger).toBeFocused(); await expect(question).toBeEnabled(); await expect(question).toHaveValue("Keep this unpublished question draft?");
  await expect(draftReason).toHaveValue("Keep this private draft publication reason."); expect(state.publications).toHaveLength(0);
});

test("reviewed restoration creates a new published version and shows its history source", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/intake-forms");
  const original = await source(page); await original.getByRole("button", { name: "Review restoration of version 2", exact: true }).click();
  const form = page.getByRole("form", { name: "Restore published form" });
  await expect(form.getByRole("button", { name: "Publish restored version", exact: true })).toBeDisabled(); expect(state.restores).toHaveLength(0);
  await form.getByRole("textbox", { name: "Private restoration reason", exact: true }).fill(reason);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("intake-form-restoration.png"), fullPage: true });
  await form.getByRole("button", { name: "Publish restored version", exact: true }).click();
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  await expect(editor.getByRole("status").filter({ hasText: "Version 2 restored as version 4" })).toBeFocused();
  await expect(editor.getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Original timing question?");
  await expect(editor.getByText("Restored from version 2", { exact: true })).toBeVisible();
  expect(state.restores[0]).toMatchObject({ revision: 3, source_revision: 2, confirmed: true, preview_questions: oldQuestions, reason });
  expect(state.restores).toHaveLength(1); expect(state.publications).toHaveLength(0);
});

test("successful restoration keeps an unpublished draft and publishes it only after a fresh review", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/intake-forms");
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  await editor.getByRole("textbox", { name: "Question text", exact: true }).fill("Retain my different unpublished question?");
  await editor.getByRole("textbox", { name: "Private publication reason", exact: true }).fill("Retain this private publication draft reason.");
  const original = await source(page); await original.getByRole("button", { name: "Review restoration of version 2", exact: true }).click();
  await editor.getByRole("textbox", { name: "Private restoration reason", exact: true }).fill(reason);
  await editor.getByRole("button", { name: "Publish restored version", exact: true }).click();
  await expect(editor.getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Retain my different unpublished question?");
  await expect(editor.getByRole("textbox", { name: "Private publication reason", exact: true })).toHaveValue("Retain this private publication draft reason.");
  await expect(editor.getByText(/Your unpublished question draft and reason are kept below/)).toBeVisible(); expect(state.publications).toHaveLength(0);
  await editor.getByRole("button", { name: "Review intake form", exact: true }).click();
  await editor.getByRole("button", { name: "Publish reviewed form", exact: true }).click();
  await expect.poll(() => state.publications.length).toBe(1); expect(state.publications[0].revision).toBe(4);
});

test("restoration conflict keeps both drafts until explicit reload", async ({ page, context }) => {
  await fixtures(context, "conflict"); await page.goto("/admin/intake-forms");
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  await editor.getByRole("textbox", { name: "Question text", exact: true }).fill("Preserve this local question on conflict?");
  const original = await source(page); await original.getByRole("button", { name: "Review restoration of version 2", exact: true }).click();
  const form = page.getByRole("form", { name: "Restore published form" }); await form.getByRole("textbox", { name: "Private restoration reason", exact: true }).fill(reason);
  await form.getByRole("button", { name: "Publish restored version", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("This form changed"); await expect(form.getByRole("alert")).toBeFocused();
  await expect(form.getByRole("textbox", { name: "Private restoration reason", exact: true })).toHaveValue(reason);
  await expect(editor.getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Preserve this local question on conflict?");
  await form.getByRole("button", { name: "Cancel restoration", exact: true }).click();
  await page.getByRole("button", { name: "Reload published form (replaces draft)", exact: true }).click();
  await expect(editor.getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Concurrent administrator question?");
});

test("the original empty version can be restored through its retained preceding snapshot", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/admin/intake-forms");
  const original = await source(page); await original.locator("summary").filter({ hasText: "Previous questions" }).click();
  await original.getByRole("button", { name: "Review restoration of version 1", exact: true }).click();
  const form = page.getByRole("form", { name: "Restore published form" });
  await expect(form).toContainText("No additional questions. Standard guided questions still apply.");
  await form.getByRole("textbox", { name: "Private restoration reason", exact: true }).fill(reason);
  await form.getByRole("button", { name: "Publish restored version", exact: true }).click();
  await expect(page.getByText(/Published version 4 · 0 additional questions/)).toBeVisible(); expect(state.restores[0].preview_questions).toEqual([]);
});

test("changed retained source is shown as an error without replacing editor state", async ({ page, context }) => {
  const state = await fixtures(context, "source_changed"); await page.goto("/admin/intake-forms");
  const original = await source(page); await original.getByRole("button", { name: "Review restoration of version 2", exact: true }).click();
  const form = page.getByRole("form", { name: "Restore published form" }); await form.getByRole("textbox", { name: "Private restoration reason", exact: true }).fill(reason);
  await form.getByRole("button", { name: "Publish restored version", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("differ from your preview"); await expect(form.getByRole("textbox", { name: "Private restoration reason", exact: true })).toHaveValue(reason);
  await expect(page.getByText(/Published version 3 · 1 additional questions/)).toBeVisible(); expect(state.publications).toHaveLength(0);
});

for (const mode of ["agent", "retired"] as const) test(`${mode} cannot restore a form`, async ({ page, context }) => {
  const state = await fixtures(context, mode); await page.goto("/admin/intake-forms");
  if (mode === "agent") await expect(page.getByRole("heading", { name: "Administrator access required", exact: true })).toBeVisible();
  else { const original = await source(page); await expect(original.getByRole("button", { name: "Review restoration of version 2", exact: true })).toBeDisabled(); }
  await expect(page.getByRole("form", { name: "Restore published form" })).toHaveCount(0); expect(state.restores).toHaveLength(0);
});
