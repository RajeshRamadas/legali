import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const first = "826fb188-309e-4c19-94a4-e67d559219ce", second = "926fb188-309e-4c19-94a4-e67d559219ce";
const profile = { name: "Synthetic Customer", phone: "+919999900001", contact: "+919999900001", email: null };
const reason = "PRIVATE synthetic intake publication review.";
type Question = { id: string; prompt: string; help: string; kind: string; required: boolean; max_length: number; options: string[] };
const original: Question[] = [
  { id: first, prompt: "When is your planned transaction?", help: "Approximate timing is enough.", kind: "select", required: true, max_length: 200, options: ["This month", "Later"] },
  { id: second, prompt: "Anything else about service timing?", help: "Do not include private document contents. "+"Reference".repeat(25), kind: "textarea", required: false, max_length: 1000, options: [] },
];

async function fixtures(context: BrowserContext, mode: "normal" | "empty" | "conflict" | "history_error" | "optional" | "answer_conflict" | "agent" = "normal") {
  await context.addInitScript(profile => {
    sessionStorage.setItem("homexo.staff.token", "intake-editor-fixture-only");
    localStorage.setItem("homexo.customer.session", JSON.stringify({ token: "intake-customer-fixture-only", profile }));
  }, profile);
  let current = { slug: "title-verification", name: "Title Verification", active: true, revision: mode === "empty" ? 1 : 2, questions: mode === "empty" ? [] as Question[] : structuredClone(original) };
  if (mode === "optional") current.questions[0].required = false;
  if (mode === "answer_conflict") current.questions[0] = { ...current.questions[0], kind: "text", options: [] };
  let historyReads = 0, revision = 1, savedForm: typeof current | null = null, submitted = false;
  const answers: Record<string, string> = { service_slug: "title-verification" };
  const history: { id: string; actor: string; at: string; revision: number; reason: string; questions: Question[]; previous_questions: Question[] }[] = [];
  const state = { publications: [] as { revision: number; confirmed: boolean; questions: Question[]; reason: string }[], answers: [] as { key: string; value: string }[], submissions: [] as { notice_version: string; consent: boolean }[], historyReads: () => historyReads,
    republish: () => { current = { ...current, revision: current.revision+1, questions: current.questions.map(row => ({ ...row, prompt: "Changed question for new drafts", options: row.options.map(value => "Changed "+value) })) }; } };
  const draft = () => {
    if (!savedForm) savedForm = structuredClone(current);
    const questions = [{ key: "service_slug", prompt: "Selected service", kind: "select", required: true, help: "", options: [{ value: "title-verification", label: "Title Verification" }] }, ...savedForm.questions.map(row => ({
      key: "extra_"+row.id.replaceAll("-", ""), prompt: row.prompt, kind: row.kind, required: row.required, help: row.help, min_length: row.required ? 1 : 0, max_length: row.max_length, options: row.options.map((label, index) => ({ value: String(index+1), label })),
    }))];
    return { id: "draft-fixture", status: submitted ? "submitted" : "draft", revision, service_available: true, service_form_revision: savedForm.revision, answers,
      questions, next_question: questions.find(row => !(row.key in answers))?.key ?? null, completed: Object.keys(answers).length, total: questions.length,
      updated_at: "2026-11-11T10:00:00Z", expires_at: "2026-12-11T10:00:00Z", ticket: submitted ? { ticket_number: "HX-INTAKE-FIXTURE", status: "submitted", message: "Synthetic request received." } : null,
      notice: { version: "guided-request-v2", retention_days: 30, saving: "Save these synthetic answers privately.", submission: "I reviewed this synthetic service request.", details: [] } };
  };
  await context.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,PATCH,POST,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path.endsWith("/auth/me")) return reply({ id: "intake-editor", name: "Fixture Administrator", role: mode === "agent" ? "agent" : "admin", mfa_enabled: true, available_for_calls: false });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path === "/api/v1/admin/intake-forms") return reply({ items: [current] });
    if (path.endsWith("/title-verification/history")) {
      historyReads++;
      if (mode === "history_error" && historyReads === 1) return reply({ detail: "Form history unavailable" }, 503);
      const rows = mode === "history_error" ? Array.from({ length: 21 }, (_, index) => ({ id: `event-${index}`, actor: "Fixture Administrator", at: "2026-11-11T10:00:00Z", revision: index+2, reason, questions: original, previous_questions: [] })) : history;
      const page = Number(url.searchParams.get("page") || 1); return reply({ items: rows.slice((page-1)*20, page*20), total: rows.length, page, page_size: 20 });
    }
    if (path === "/api/v1/admin/intake-forms/title-verification" && request.method() === "PATCH") {
      const body = request.postDataJSON(); state.publications.push(body);
      if (mode === "conflict" && state.publications.length === 1) state.republish();
      if (body.revision !== current.revision) return reply({ detail: "This form changed. Reload the published form." }, 409);
      history.unshift({ id: `published-${history.length}`, actor: "Fixture Administrator", at: "2026-11-11T10:00:00Z", revision: current.revision+1, reason: body.reason, questions: body.questions, previous_questions: current.questions });
      current = { ...current, questions: body.questions, revision: current.revision+1 }; return reply(current);
    }
    if (path === "/api/v1/account") return reply({ profile, requests: [], bookings: [], payments: [], payments_mode: "off" });
    if (path.endsWith("/support-requests/unread")) return reply({ requests: 0, unread_replies: 0 });
    if (path === "/api/v1/intake/drafts") { const value = draft(); return reply({ items: [value], notice: value.notice }); }
    if (path.endsWith("/draft-fixture/submit")) { state.submissions.push(request.postDataJSON()); submitted = true; return reply(draft().ticket); }
    if (path.endsWith("/draft-fixture")) {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON(); state.answers.push(body);
        if (mode === "answer_conflict" && state.answers.length === 1) { revision++; return reply({ detail: "This draft changed on another tab. Reload the saved answers." }, 409); }
        answers[body.key] = body.value; revision++;
      }
      return reply(draft());
    }
    return reply({ detail: "No intake form browser fixture" }, 503);
  });
  return state;
}

test("administrator builds, reorders, reviews and publishes service questions with private history", async ({ page, context }) => {
  const state = await fixtures(context, "empty"); await page.goto("/admin/intake-forms");
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  await editor.getByRole("button", { name: "Add question", exact: true }).click();
  const first = editor.getByRole("group", { name: "Question 1", exact: true });
  await first.getByRole("textbox", { name: "Question text", exact: true }).fill("When is your planned transaction?");
  await first.getByRole("combobox", { name: "Answer type", exact: true }).selectOption("select");
  await first.getByRole("textbox", { name: "Choice 1", exact: true }).fill("This month");
  await first.getByRole("textbox", { name: "Choice 2", exact: true }).fill("Later"); await first.getByRole("checkbox").check();
  await editor.getByRole("button", { name: "Add question", exact: true }).click();
  const second = editor.getByRole("group", { name: "Question 2", exact: true });
  await second.getByRole("textbox", { name: "Question text", exact: true }).fill("Anything else about service timing?");
  await second.getByRole("combobox", { name: "Answer type", exact: true }).selectOption("textarea");
  await second.getByRole("textbox", { name: "Help text (optional)", exact: true }).fill("Please share scope only. "+"Reference".repeat(25));
  await editor.getByRole("button", { name: "Move question 2 up", exact: true }).click();
  await expect(first.getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Anything else about service timing?");
  await editor.getByRole("textbox", { name: "Private publication reason", exact: true }).fill(reason);
  await editor.getByRole("button", { name: "Review intake form", exact: true }).click(); expect(state.publications).toHaveLength(0);
  await expect(editor.getByRole("region", { name: "Question preview" })).toBeFocused();
  await editor.getByRole("button", { name: "Publish reviewed form", exact: true }).click();
  await expect(editor.getByRole("status").filter({ hasText: "Intake form published" })).toBeFocused();
  expect(state.publications[0]).toMatchObject({ revision: 1, confirmed: true, reason }); expect(state.publications[0].questions).toHaveLength(2);
  expect(state.historyReads()).toBe(0);
  await editor.locator("summary").filter({ hasText: "Private form publication history" }).click(); await expect(editor.getByText(`Private reason: ${reason}`, { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("service-intake-editor.png"), fullPage: true });
});

test("publication conflict preserves question edits and private reason until explicit reload", async ({ page, context }) => {
  const state = await fixtures(context, "conflict"); await page.goto("/admin/intake-forms");
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  await editor.getByRole("group", { name: "Question 1", exact: true }).getByRole("textbox", { name: "Question text", exact: true }).fill("Keep this unsaved service question?");
  await editor.getByRole("textbox", { name: "Private publication reason", exact: true }).fill(reason);
  await editor.getByRole("button", { name: "Review intake form", exact: true }).click(); await editor.getByRole("button", { name: "Publish reviewed form", exact: true }).click();
  await expect(editor.getByRole("alert")).toContainText("This form changed");
  await editor.getByRole("button", { name: "Back to editing", exact: true }).click();
  await expect(editor.getByRole("group", { name: "Question 1", exact: true }).getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Keep this unsaved service question?");
  await expect(editor.getByRole("textbox", { name: "Private publication reason", exact: true })).toHaveValue(reason);
  await page.getByRole("button", { name: "Reload published form (replaces draft)", exact: true }).click();
  await expect(editor.getByRole("group", { name: "Question 1", exact: true }).getByRole("textbox", { name: "Question text", exact: true })).toHaveValue("Changed question for new drafts");
  expect(state.publications).toHaveLength(1);
});

test("history errors and paging preserve unpublished question text", async ({ page, context }) => {
  await fixtures(context, "history_error"); await page.goto("/admin/intake-forms");
  const editor = page.getByRole("region", { name: "Service intake form editor" });
  const input = editor.getByRole("group", { name: "Question 1", exact: true }).getByRole("textbox", { name: "Question text", exact: true });
  await input.fill("Keep this form draft while reviewing history?");
  await editor.locator("summary").filter({ hasText: "Private form publication history" }).click();
  await expect(editor.getByRole("alert")).toContainText("Form history unavailable");
  await editor.getByRole("button", { name: "Retry form history", exact: true }).click();
  await expect(editor.getByRole("heading", { name: "Version 2", exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Next publications", exact: true }).click();
  await expect(editor.getByRole("heading", { name: "Version 22", exact: true })).toBeVisible(); await expect(input).toHaveValue("Keep this form draft while reviewing history?");
});

test("customer answers pinned choices and paragraphs, reviews original labels and submits with current consent", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto("/request?draft=draft-fixture");
  await expect(page.getByText(/Service questions version 2 is saved/)).toBeVisible();
  await page.getByRole("combobox", { name: "When is your planned transaction?", exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Continue", exact: true }).click(); state.republish();
  await expect(page.getByRole("textbox", { name: "Anything else about service timing?", exact: true })).toHaveAttribute("maxlength", "1000");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.getByRole("textbox", { name: "Anything else about service timing?", exact: true }).fill("A synthetic timing note. "+"Reference".repeat(25));
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Does everything look right?", exact: true })).toBeVisible();
  await expect(page.locator(".intake-review")).toContainText("Later"); await expect(page.getByText("Changed Later", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create my request", exact: true })).toBeDisabled();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("service-intake-customer.png"), fullPage: true });
  await page.getByRole("checkbox").check(); await page.getByRole("button", { name: "Create my request", exact: true }).click();
  await expect(page.getByRole("heading", { name: "HX-INTAKE-FIXTURE", exact: true })).toBeVisible();
  expect(state.submissions[0]).toMatchObject({ notice_version: "guided-request-v2", consent: true });
  expect(state.answers[0]).toMatchObject({ key: "extra_"+first.replaceAll("-", ""), value: "2" });
});

test("optional choice can be skipped and save-and-exit keeps the paragraph for resume", async ({ page, context }) => {
  const state = await fixtures(context, "optional"); await page.goto("/request?draft=draft-fixture");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("textbox", { name: "Anything else about service timing?", exact: true }).fill("Resume this saved timing detail.");
  await page.getByRole("button", { name: "Save and exit", exact: true }).click(); await expect(page).toHaveURL(/\/request$/);
  await page.getByRole("link", { name: "Resume", exact: true }).click();
  await expect(page.locator(".intake-review")).toContainText("Resume this saved timing detail.");
  expect(state.answers[0].value).toBe(""); expect(state.submissions).toHaveLength(0);
});

test("customer revision conflict keeps typed answer until saved answers are explicitly reloaded", async ({ page, context }) => {
  await fixtures(context, "answer_conflict"); await page.goto("/request?draft=draft-fixture");
  const input = page.getByRole("textbox", { name: "When is your planned transaction?", exact: true }); await input.fill("Keep my unsaved timing detail.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "This draft changed" })).toContainText("This draft changed"); await expect(input).toHaveValue("Keep my unsaved timing detail.");
  await expect(input).toBeDisabled(); await page.getByRole("button", { name: "Reload saved answers", exact: true }).click();
  await expect(input).toBeEnabled(); await expect(input).toHaveValue("");
});

test("agents cannot publish forms or see the administration link", async ({ page, context }) => {
  const state = await fixtures(context, "agent"); await page.goto("/admin/intake-forms");
  await expect(page.getByRole("heading", { name: "Administrator access required", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Intake forms", exact: true })).toHaveCount(0);
  expect(state.publications).toHaveLength(0); expect(state.historyReads()).toBe(0);
});
