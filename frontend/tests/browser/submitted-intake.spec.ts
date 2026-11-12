import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const number = "HX-SUBMITTED-FIXTURE";
const person = { id: "review-staff", name: "Fixture Administrator", role: "admin", mfa_enabled: true, available_for_calls: false };
const goal = "Please review literal <img src=x onerror=alert(1)> text. "+"Reference".repeat(40);

async function fixtures(context: BrowserContext, mode: "normal" | "legacy" | "plain" | "agent" | "denied" | "partial" = "normal") {
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "submitted-intake-ui-fixture-only"));
  const state = { ticketReads: 0, writes: 0 };
  const review = {
    format: mode === "legacy" || mode === "partial" ? "legacy" : "snapshot", incomplete: mode === "partial", service_form_revision: 2,
    submitted_at: mode === "partial" ? null : "2026-11-11T10:00:00Z", saving_consented_at: "2026-11-11T09:30:00Z", submission_notice: "guided-request-v2", saving_notice: "guided-request-v2",
    answers: mode === "partial" ? [] : [
      { key: "goal", question: mode === "legacy" ? "Customer goal" : "Tell us what you want to achieve.", answer: goal, skipped: false, section: "general" },
      { key: "property_type", question: "Property type", answer: mode === "legacy" ? "apartment" : "Apartment", skipped: false, section: "general" },
      { key: "extra_timing", question: "When is your planned transaction?", answer: "After signing", skipped: false, section: "service" },
      { key: "extra_notes", question: "Other timing details?", answer: "", skipped: true, section: "service" },
    ],
  };
  const ticket = {
    ticket_number: number, title: "Synthetic guided request", service_slug: "title-verification", service_name: "Title Verification", customer_name: "Synthetic Customer",
    phone: "+919999900001", package: null, location: "Synthetic Bengaluru", status: "submitted", status_label: "Received", priority: "normal", source: "chat", needs_reply: false,
    created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z", assignee: mode === "agent" ? person : null,
    description: "Synthetic case summary for submitted intake review.", customer: { id: "customer-fixture", name: "Synthetic Customer", phone: "+919999900001", email: null },
    property: { type: "apartment", location: "Synthetic Bengaluru" }, documents: [], report: null, messages: [], meetings: [], notifications: [], events: [], verification_workflow: null,
    guided_request: mode === "plain" ? null : review,
    chat_transcript: mode === "partial" ? [] : [{ from: "assistant", message: "Original submitted question", at: "2026-11-11T10:00:00Z" }, { from: "customer", message: "Original submitted answer", at: "2026-11-11T10:00:01Z" }],
    case: { milestones: [{ key: "received", label: "Received", done: true, current: true }], current_milestone: "received", owner: null, team: [], tasks: [], open_tasks: 0, overdue_tasks: 0,
      fee: { status: "none", status_label: "Not quoted", quote: null, paid: null, paid_at: null, reference: null, note: null }, closure: null, closed: null, allowed_statuses: ["in_progress"], outcomes: [],
      deadlines: { due_at: null, first_response_due_at: null, first_response_at: null, overdue: false, first_response_missed: false, paused: false, paused_at: null } },
  };
  await context.route("**/api/v1/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ headers, json, status });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (request.method() !== "GET") { state.writes++; return reply({ detail: "Unexpected browser fixture write" }, 400); }
    if (path.endsWith("/auth/me")) return reply({ ...person, role: mode === "agent" || mode === "denied" ? "agent" : "admin" });
    if (path.endsWith("/admin/urgent") || path.endsWith("/admin/case-alerts") || path.endsWith("/support-requests/deadline-alerts")) return reply({ items: [], unacknowledged: 0 });
    if (path.endsWith("/admin/staff")) return reply({ items: [person] });
    if (path.endsWith("/admin/meta")) return reply({ statuses: [{ value: "submitted", label: "Received" }, { value: "in_progress", label: "In progress" }], priorities: ["normal", "urgent"], notifications: {}, meetings: { google_calendar: false, whatsapp: false, timezone: "Asia/Kolkata", reminder_minutes: [] } });
    if (path.endsWith(`/admin/tickets/${number}`)) { state.ticketReads++; return mode === "denied" ? reply({ detail: "Ticket not found" }, 404) : reply(ticket); }
    if (path.endsWith("/document-hold")) return reply({held:false,revision:0,can_manage:false,changed_at:null});
    if (path.endsWith("/ai-processing")) return reply({allowed:false,status:"not_allowed"});
    if (path.endsWith("/admin/verification/config")) return reply({ configured: false, provider: "off", model: "", states: [], max_documents: 10, max_pages_per_document: 15 });
    if (path.endsWith("/verification")) return reply({ items: [] });
    if (path.endsWith("/admin/report-template")) return reply({ items: [], sources: [], disclaimer: "Synthetic fixture report template" });
    return reply({ detail: "No submitted intake browser fixture" }, 503);
  });
  return state;
}

test("staff searches original answers and recorded notices without fetching again or losing reply drafts", async ({ page, context }) => {
  const state = await fixtures(context); await page.goto(`/admin/tickets/${number}`);
  const panel = page.getByRole("region", { name: "Submitted request review" });
  await expect(panel.getByText("After signing", { exact: true })).toBeVisible(); await expect(panel.getByText("Skipped by customer", { exact: true })).toBeVisible();
  await expect(panel.getByText(goal, { exact: true })).toBeVisible(); await expect(panel.locator("img")).toHaveCount(0);
  const message = page.getByRole("textbox", { name: "Message to the customer", exact: true }); await message.fill("Keep this unsent reply while reviewing intake.");
  await panel.getByRole("combobox", { name: "Answer group", exact: true }).selectOption("service");
  await expect(panel.getByRole("status")).toHaveText("2 of 4 answers shown."); await expect(message).toHaveValue("Keep this unsent reply while reviewing intake.");
  await panel.getByRole("searchbox", { name: "Find in submitted answers", exact: true }).fill("signing");
  await expect(panel.getByRole("status")).toHaveText("1 of 4 answers shown.");
  await panel.getByRole("searchbox", { name: "Find in submitted answers", exact: true }).fill("no matching answer");
  await expect(panel.getByText("No recorded answers match these filters.", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Internal note", exact: true }).click();
  const note = page.getByRole("textbox", { name: "Internal note", exact: true }); await note.fill("Keep this private case note as well.");
  await panel.getByRole("searchbox", { name: "Find in submitted answers", exact: true }).fill("");
  await panel.getByRole("combobox", { name: "Answer group", exact: true }).selectOption("all");
  await expect(note).toHaveValue("Keep this private case note as well.");
  await panel.locator("summary").filter({ hasText: "Recorded notices" }).click();
  await expect(panel.getByText("guided-request-v2", { exact: true })).toHaveCount(2);
  await expect(page.locator(".chat-transcript summary")).toContainText("Submitted question history");
  const scan = await new AxeBuilder({ page }).include(".submitted-intake").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(scan.violations.map(row => ({ id: row.id, nodes: row.nodes.map(node => node.target) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  expect(state.ticketReads).toBe(1); expect(state.writes).toBe(0);
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: test.info().outputPath("submitted-request-review.png"), fullPage: true });
});

test("older records identify saved general values while retaining original service labels", async ({ page, context }) => {
  const state = await fixtures(context, "legacy"); await page.goto(`/admin/tickets/${number}`);
  const panel = page.getByRole("region", { name: "Submitted request review" });
  await expect(panel.getByText(/This older request shows general fields as saved values/)).toBeVisible();
  await expect(panel.getByText("apartment", { exact: true })).toBeVisible(); await expect(panel.getByText("After signing", { exact: true })).toBeVisible();
  await page.locator(".chat-transcript summary").click(); await expect(page.getByText("Original submitted answer", { exact: true })).toBeVisible();
  expect(state.writes).toBe(0);
});

test("ordinary callbacks keep their conversation view without a guided review", async ({ page, context }) => {
  await fixtures(context, "plain"); await page.goto(`/admin/tickets/${number}`);
  await expect(page.getByRole("heading", { name: "Conversation", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Submitted request review" })).toHaveCount(0);
  await expect(page.locator(".chat-transcript summary")).toContainText("Chat with the assistant");
});

test("authorized agents can review intake and denied cases show no saved answers", async ({ page, context }) => {
  await fixtures(context, "agent"); await page.goto(`/admin/tickets/${number}`);
  const panel = page.getByRole("region", { name: "Submitted request review" }); await expect(panel.getByText("After signing", { exact: true })).toBeVisible();
});

test("case access errors do not render intake data", async ({ page, context }) => {
  await fixtures(context, "denied"); await page.goto(`/admin/tickets/${number}`);
  await expect(page.getByRole("alert").filter({ hasText: "Ticket not found" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Submitted request review" })).toHaveCount(0); await expect(page.getByText(goal, { exact: true })).toHaveCount(0);
});

test("incomplete older records show missing-data guidance and safe notice fallbacks", async ({ page, context }) => {
  await fixtures(context, "partial"); await page.goto(`/admin/tickets/${number}`);
  const panel = page.getByRole("region", { name: "Submitted request review" });
  await expect(panel.getByText(/Some recorded answers could not be displayed/)).toBeVisible();
  await expect(panel.getByText(/Original general-question wording was not retained/)).toBeVisible();
  await expect(panel.getByText("No readable answer snapshot was retained. Review the retained case records.", { exact: true })).toBeVisible();
  await panel.locator("summary").click(); await expect(panel.getByText("Not retained", { exact: true })).toBeVisible();
});
