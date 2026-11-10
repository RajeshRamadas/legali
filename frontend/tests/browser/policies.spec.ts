import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { POLICY_LABELS, type PolicyContent, type PolicyHead, type PolicyKind, type PolicySnapshot } from "../../app/policies/types";

const source: PolicyContent = { title: "Synthetic privacy policy", summary: "Illustrative policy information for a browser fixture, not a real legal notice.",
  body: "# Information supplied\n\nThis is a synthetic browser fixture used to verify policy display. It does not describe a real organization's policy.\n\n<script>window.policyInjected=true</script>\n\n![Tracking image](https://external.invalid/tracking.png)",
  organization: "Synthetic Policy Test Firm", contact_email: "privacy@policy-fixture.in", contact_phone: "", postal_address: "Synthetic office address used only by tests", grievance_officer: "Synthetic Contact" };

async function fixtures(context: BrowserContext, published = false, role = "admin") {
  const heads = Object.fromEntries(Object.keys(POLICY_LABELS).map(kind => [kind, { kind, revision: 0, version_counter: 0, draft: null, published: null, withdraw_reason: null }])) as Record<PolicyKind, PolicyHead>;
  const versions: Record<PolicyKind, (PolicySnapshot & { is_public: boolean })[]> = { privacy: [], terms: [], grievance: [] };
  let conflict = false;
  function seed() {
    const item = { kind: "privacy" as const, number: 1, published_at: "2026-11-10T00:00:00Z", content: structuredClone(source), is_public: true };
    heads.privacy = { ...heads.privacy, revision: 2, version_counter: 1, published: item };
    versions.privacy.push(item);
  }
  if (published) seed();
  await context.addInitScript(() => sessionStorage.setItem("homexo.staff.token", "policy-browser-fixture-only"));
  await context.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", ""), method = route.request().method();
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,PUT,OPTIONS" };
    const reply = (json: unknown, status = 200) => route.fulfill({ status, headers, json });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/auth/me") return reply({ id: "fixture-staff", name: "Policy Reviewer", role, mfa_enabled: true, available_for_calls: false });
    if (path === "/admin/urgent") return reply({ items: [] });
    if (path === "/admin/case-alerts") return reply({ items: [], total: 0, unacknowledged: 0, escalated: 0 });
    if (path === "/admin/site-policies") return reply({ items: Object.values(heads) });
    const admin = /^\/admin\/site-policies\/(privacy|terms|grievance)\/(draft|publish|withdraw|versions)$/.exec(path);
    if (admin) {
      const kind = admin[1] as PolicyKind, action = admin[2], head = heads[kind];
      if (action === "versions") return reply({ items: [...versions[kind]].reverse(), total: versions[kind].length, page: 1, page_size: 10 });
      const payload = route.request().postDataJSON();
      if (payload.revision !== head.revision || action === "draft" && conflict) {
        conflict = false; head.revision += 1;
        return reply({ detail: "This policy changed. Reload the latest version before saving or publishing." }, 409);
      }
      if (action === "draft") head.draft = structuredClone(payload.content);
      if (action === "publish") {
        if (!payload.reviewed || !head.draft) return reply({ detail: "Review a saved draft first." }, 422);
        const snapshot = { kind, number: ++head.version_counter, published_at: "2026-11-10T00:00:00Z", content: structuredClone(head.draft), is_public: true };
        head.published = snapshot; head.draft = null; versions[kind].push(snapshot);
      }
      if (action === "withdraw") { head.published = null; head.withdraw_reason = payload.reason; versions[kind].forEach(item => { item.is_public = false; }); }
      head.revision += 1;
      return reply(head);
    }
    if (path === "/policies") return reply({ items: Object.entries(heads).map(([kind,item]) => ({ kind, label: POLICY_LABELS[kind as PolicyKind], available: !!item.published, policy: item.published })) });
    const publicPath = /^\/policies\/(privacy|terms|grievance)(?:\/versions\/(\d+))?$/.exec(path);
    if (publicPath) {
      const kind = publicPath[1] as PolicyKind, head = heads[kind];
      const item = publicPath[2] ? versions[kind].find(item => item.number === Number(publicPath[2]) && item.is_public) : head.published;
      return head.published && item ? reply(item) : reply({ detail: "This policy is not published." }, 404);
    }
    return reply({ detail: "No policy browser fixture for this request." }, 503);
  });
  return { heads, versions, conflictNextSave: () => { conflict = true; } };
}

async function accessible(page: Page) {
  const report = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  await test.info().attach("policy-axe.json", { body: Buffer.from(JSON.stringify(report)), contentType: "application/json" });
  expect(report.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) }))).toEqual([]);
}

test("unpublished policies do not invent contact details or expose drafts", async ({ page, context }) => {
  const state = await fixtures(context);
  state.heads.privacy.draft = { ...source, body: "PRIVATE_DRAFT_SENTINEL" };
  await page.goto("/policies");
  await expect(page.getByRole("link", { name: "View availability" })).toHaveCount(3);
  await expect(page.getByText("PRIVATE_DRAFT_SENTINEL")).toHaveCount(0);
  await accessible(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.locator("footer").getByRole("link", { name: "Privacy notice", exact: true }).click();
  await expect(page.getByRole("heading", { name: "This policy is not published" })).toBeVisible();
  await expect(page.getByText(source.contact_email)).toHaveCount(0);
});

test("published policy text is readable, safely rendered and addressable by version", async ({ page, context }) => {
  await fixtures(context, true);
  await page.goto("/policies/privacy");
  await expect(page.getByRole("heading", { name: source.title, exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: source.contact_email })).toHaveAttribute("href", "mailto:privacy@policy-fixture.in");
  await expect(page.locator(".policy-document img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { policyInjected?: boolean }).policyInjected)).toBeUndefined();
  await page.getByRole("link", { name: "Link to this version" }).click();
  await expect(page).toHaveURL(/version=1/);
  await expect(page.getByRole("link", { name: "Current policy" })).toBeVisible();
  await accessible(page);
});

test("administrator saves a private draft, publishes after review and withdraws all public copies", async ({ page, context }) => {
  const state = await fixtures(context);
  await page.goto("/admin/policies");
  await expect(page.getByRole("heading", { name: "Public policies", exact: true })).toBeVisible();
  await page.getByLabel("Policy title").fill(source.title);
  await page.getByLabel("Summary", { exact: true }).fill(source.summary);
  await page.getByLabel("Organization name").fill(source.organization);
  await page.getByLabel("Public contact email").fill(source.contact_email);
  await page.getByLabel("Policy text (Markdown)").fill(source.body);
  await page.getByRole("button", { name: "Save private draft" }).click();
  await expect(page.locator(".policy-admin > [role=status]")).toContainText("draft saved privately");
  expect(state.heads.privacy.published).toBeNull();
  await expect(page.getByRole("button", { name: "Publish reviewed version" })).toBeDisabled();
  await accessible(page);
  await page.getByLabel(/I confirm this saved version/).check();
  await page.getByRole("button", { name: "Publish reviewed version" }).click();
  await expect(page.locator(".policy-admin > [role=status]")).toContainText("version 1 published");
  await page.goto("/policies/privacy");
  await expect(page.getByRole("heading", { name: source.title, exact: true })).toBeVisible();
  await page.goto("/admin/policies");
  await page.getByRole("button", { name: "Withdraw public policy", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Withdraw public policy", exact: true });
  await dialog.getByLabel("Withdrawal reason (team only)").fill("PRIVATE_WITHDRAWAL_REASON");
  await dialog.getByLabel(/I confirm removal/).check();
  await dialog.getByRole("button", { name: "Confirm withdrawal" }).click();
  await expect(page.locator(".policy-admin > [role=status]")).toContainText("public history withdrawn");
  await page.goto("/policies/privacy?version=1");
  await expect(page.getByRole("heading", { name: "This policy is not published" })).toBeVisible();
  await expect(page.getByText("PRIVATE_WITHDRAWAL_REASON")).toHaveCount(0);
});

test("conflicting saves retain editor text until an explicit reload", async ({ page, context }) => {
  const state = await fixtures(context, true);
  await page.goto("/admin/policies");
  const body = page.getByLabel("Policy text (Markdown)");
  await body.fill("My unsaved review text that must survive a conflict.");
  state.conflictNextSave();
  await page.getByRole("button", { name: "Save private draft" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "This policy changed" })).toBeVisible();
  await expect(body).toHaveValue("My unsaved review text that must survive a conflict.");
  await page.getByRole("button", { name: "Reload latest (replaces editor text)" }).click();
  await expect(body).toHaveValue(source.body);
});
