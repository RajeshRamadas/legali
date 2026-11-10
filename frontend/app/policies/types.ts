export const POLICY_LABELS = { privacy: "Privacy notice", terms: "Terms of service", grievance: "Contact & grievance" };
export type PolicyKind = keyof typeof POLICY_LABELS;
export type PolicyContent = { title: string; summary: string; body: string; organization: string; contact_email: string; contact_phone: string; postal_address: string; grievance_officer: string };
export type PolicySnapshot = { kind: PolicyKind; number: number; published_at: string; content: PolicyContent };
export type PolicyHead = { kind: PolicyKind; revision: number; version_counter: number; draft: PolicyContent | null; published: PolicySnapshot | null; withdraw_reason: string | null };
export type PolicyIndex = { items: { kind: PolicyKind; label: string; available: boolean; policy: PolicySnapshot | null }[] };
export type PolicyHistory = { items: (PolicySnapshot & { is_public: boolean })[]; total: number; page: number; page_size: number };
export const policyDate = (date: string) => new Date(date).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
