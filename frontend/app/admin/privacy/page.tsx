"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { PRIVACY_KIND_LABELS, PRIVACY_STATUS_LABELS, PRIVACY_RESOLUTION_LABELS, PRIVACY_REASON_LABELS, type PrivacyResolution, type PrivacyReason } from "@homexo/shared";
import { useStaff } from "../AdminShell";
import { adminFetch, type AdminPrivacyQueue, type AdminPrivacyRequest, type PrivacyRetention } from "../api";
import "../../ui/privacy.css";

const date = (value: string) => new Date(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function PrivacyDesk() {
  const { user, onError } = useStaff();
  const [data, setData] = useState<AdminPrivacyQueue | null>(null), [retention, setRetention] = useState<PrivacyRetention | null>(null);
  const [filter, setFilter] = useState("open"), [page, setPage] = useState(1), [error, setError] = useState("");
  const [selected, setSelected] = useState<AdminPrivacyRequest | null>(null), [busy, setBusy] = useState(false);
  const sequence = useRef(0), selection = useRef(0);
  const load = useCallback(async () => {
    if (user.role !== "admin") return;
    const request = ++sequence.current;
    try {
      const [queue, policy] = await Promise.all([adminFetch<AdminPrivacyQueue>(`/admin/privacy-requests?status=${filter}&page=${page}`, { cache: "no-store" }), adminFetch<PrivacyRetention>("/admin/privacy-retention", { cache: "no-store" })]);
      if (request === sequence.current) { setData(queue); setRetention(policy); setError(""); }
    } catch (e) { if (request === sequence.current) setError(onError(e)); }
  }, [user.role, onError, filter, page]);
  useEffect(() => { load(); }, [load]);
  async function show(id: string) {
    const request = ++selection.current;
    setBusy(true); setError("");
    try { const item = await adminFetch<AdminPrivacyRequest>(`/admin/privacy-requests/${id}`, { cache: "no-store" }); if (request === selection.current) setSelected(item); }
    catch (e) { if (request === selection.current) setError(onError(e)); }
    finally { if (request === selection.current) setBusy(false); }
  }
  function changeFilter(value: string) { ++selection.current; setBusy(false); setSelected(null); setFilter(value); setPage(1); }
  if (user.role !== "admin") return <main className="privacy-admin"><h1>Privacy requests</h1><p>Administrator access is required to review privacy requests.</p></main>;
  return <main className="privacy-admin"><header className="privacy-heading"><div><div className="eyebrow">Administrator workspace</div><h1>Privacy requests</h1><p>Review scope, retention obligations and the response shared with the customer.</p></div><button className="btn small light" onClick={load}>Refresh queue</button></header>
    {error && <div className="privacy-error" role="alert">Could not refresh the privacy desk. {error}{data && <p>The last loaded queue is shown below.</p>}</div>}
    {retention && <section className="privacy-card"><div className="privacy-heading"><h2>Anonymous chat retention</h2><span className="privacy-badge">{retention.cleanup_enabled ? "Cleanup enabled" : "Cleanup not enabled"}</span></div><p>Preview: {retention.eligible_anonymous_chats} anonymous chats eligible after {retention.retention_days} inactive days. {retention.held_conversations} conversations are on hold.</p><p className="privacy-muted">Case-linked, consented and held conversations are preserved. Cleanup is a separate operator task governed by the reviewed retention policy.</p></section>}
    <div className="privacy-heading"><label>Queue status <select className="privacy-filter" value={filter} onChange={e => changeFilter(e.target.value)}>{[ ["open", "Open requests"], ["submitted", "Submitted"], ["in_review", "Under review"], ["closed", "Closed"], ["withdrawn", "Withdrawn"], ["all", "All requests"] ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><span className="privacy-badge warn">{data?.overdue ?? "–"} overdue open requests</span></div>
    <div className="privacy-admin-grid"><section className="privacy-queue" aria-label="Privacy request queue">
      {!data ? <p role="status">Loading privacy requests…</p> : !data.items.length ? <section className="privacy-card"><h2>No requests in this view</h2><p>Change the filter to see other requests.</p></section> : data.items.map(item => <article className="privacy-card" key={item.id}><div className="privacy-heading"><h3>{PRIVACY_KIND_LABELS[item.kind]}</h3><span className={`privacy-badge ${item.overdue ? "warn" : ""}`}>{PRIVACY_STATUS_LABELS[item.status]}</span></div><p>{item.customer.name || "Verified customer"} · Phone ending {item.customer.phone_last4}</p><p className="privacy-reference">{item.reference}</p><p className="privacy-muted">Sent {date(item.created_at)} · Review target {date(item.due_at)}{item.overdue ? " · Overdue" : ""}</p><button className="btn small light" disabled={busy} onClick={() => show(item.id)}>{item.status === "submitted" || item.status === "in_review" ? "Review request" : "View decision"}</button></article>)}
      {data && (data.total > data.page_size || page > 1) && <div className="privacy-pager"><button className="btn small light" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button><span>Page {page} · {data.total} requests</span><button className="btn small light" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Next</button></div>}
    </section><section className="privacy-review" aria-label="Selected privacy request">{selected ? <ReviewPanel key={`${selected.id}:${selected.revision}`} item={selected} onError={onError} onReload={() => show(selected.id)} onSaved={item => { setSelected(item); load(); }} /> : <div className="privacy-card"><h2>Choose a request</h2><p>Open a request to review its details and record a decision.</p></div>}</section></div>
  </main>;
}

function ReviewPanel({ item, onError, onReload, onSaved }: { item: AdminPrivacyRequest; onError: (e: unknown) => string; onReload: () => void; onSaved: (item: AdminPrivacyRequest) => void }) {
  const [response, setResponse] = useState(item.customer_response || ""), [note, setNote] = useState(item.internal_note || "");
  const [outcome, setOutcome] = useState<PrivacyResolution | "">(""), [reason, setReason] = useState<PrivacyReason | "">("");
  const [error, setError] = useState(""), [saving, setSaving] = useState(false);
  const terminal = item.status === "closed" || item.status === "withdrawn";
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    try { onSaved(await adminFetch<AdminPrivacyRequest>(`/admin/privacy-requests/${item.id}`, { method: "PATCH", body: JSON.stringify({ revision: item.revision, status: outcome ? "closed" : "in_review", customer_response: response.trim(), internal_note: note.trim(), resolution: outcome || null, retention_reason: outcome && outcome !== "fulfilled" ? reason || null : null }) })); }
    catch (e) { setError(onError(e)); }
    finally { setSaving(false); }
  }
  return <article className="privacy-card"><div className="privacy-heading"><h2>Request details</h2><span className="privacy-badge">{PRIVACY_STATUS_LABELS[item.status]}</span></div><p className="privacy-reference">{item.reference}</p><p>{PRIVACY_KIND_LABELS[item.kind]}{item.ticket_number ? ` · ${item.ticket_number}` : " · Account and requests"}</p><p className="privacy-text">{item.details}</p><p className="privacy-muted">Review target {date(item.due_at)} · Notice {item.notice_version}</p>
    {terminal ? <><h3>Customer response</h3><p className="privacy-text">{item.customer_response || "No response was recorded before withdrawal."}</p>{item.resolution && <p>{PRIVACY_RESOLUTION_LABELS[item.resolution]}{item.retention_reason ? ` · ${PRIVACY_REASON_LABELS[item.retention_reason]}` : ""}</p>}<h3>Internal review note</h3><p className="privacy-text">{item.internal_note || "No internal note."}</p></> : <form className="privacy-form" onSubmit={save}><fieldset disabled={saving}>
      <label htmlFor="privacy-customer-response">Response shown to customer<textarea id="privacy-customer-response" rows={5} maxLength={2000} minLength={outcome ? 20 : undefined} required={!!outcome} value={response} onChange={e => setResponse(e.target.value)} /></label>
      <label htmlFor="privacy-internal-note">Internal review note (administrators only)<textarea id="privacy-internal-note" rows={3} maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
      {item.status === "in_review" && <><label htmlFor="privacy-outcome">Decision<select id="privacy-outcome" value={outcome} onChange={e => { setOutcome(e.target.value as PrivacyResolution | ""); setReason(""); }}><option value="">Continue review</option>{Object.entries(PRIVACY_RESOLUTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {outcome && outcome !== "fulfilled" && <label htmlFor="privacy-reason">Decision reason<select id="privacy-reason" required value={reason} onChange={e => setReason(e.target.value as PrivacyReason)}><option value="">Choose a reason</option>{Object.entries(PRIVACY_REASON_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
        <p className="privacy-muted">Complete the approved privacy or case action before recording it as fulfilled. Explain any information retained and the reason to the customer.</p></>}
      <button className="btn" disabled={saving}>{saving ? "Saving…" : item.status === "submitted" ? "Start review" : outcome ? "Record decision and close" : "Save review update"}</button></fieldset>
      {error && <div className="privacy-error" role="alert"><p>{error}</p><p>Your draft is kept here. Reloading replaces it with the latest saved version.</p><button className="btn small light" type="button" onClick={onReload}>Reload latest request</button></div>}
    </form>}
  </article>;
}
