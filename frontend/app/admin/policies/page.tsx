"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import MainContent from "../../ui/MainContent";
import Dialog from "../../ui/Dialog";
import PolicyBody from "../../policies/PolicyBody";
import { POLICY_LABELS, policyDate, type PolicyContent, type PolicyHead, type PolicyHistory, type PolicyKind } from "../../policies/types";
import "../../policies/policies.css";

const blank = (kind: PolicyKind): PolicyContent => ({ title: POLICY_LABELS[kind], summary: "", body: "", organization: "", contact_email: "", contact_phone: "", postal_address: "", grievance_officer: "" });

export default function PoliciesAdmin() {
  const { user, onError } = useStaff();
  const [heads, setHeads] = useState<PolicyHead[] | null>(null), [kind, setKind] = useState<PolicyKind>("privacy");
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [reset, setReset] = useState(0);
  const [copy, setCopy] = useState<PolicyContent | null>(null);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    if (user.role !== "admin") return;
    const current = ++sequence.current;
    try {
      const result = await adminFetch<{ items: PolicyHead[] }>("/admin/site-policies", { cache: "no-store" });
      if (current === sequence.current) { setHeads(result.items); setError(""); setCopy(null); setReset(value => value + 1); }
    } catch (error) { if (current === sequence.current) setError(onError(error)); }
  }, [user.role, onError]);
  useEffect(() => { load(); return () => { sequence.current += 1; }; }, [load]);
  const head = heads?.find(item => item.kind === kind);
  function saved(item: PolicyHead, text: string) {
    setHeads(current => current?.map(value => value.kind === item.kind ? item : value) ?? [item]);
    setCopy(null); setNotice(`${POLICY_LABELS[item.kind]}: ${text}`);
  }
  if (user.role !== "admin") return <MainContent className="policy-admin"><h1>Public policies</h1><p>Administrator access is required.</p></MainContent>;
  return <MainContent className="policy-admin"><header><div className="eyebrow">Administrator workspace</div><h1>Public policies</h1><p>Prepare privacy, terms and grievance/contact information. Only explicitly published versions appear on the website.</p><p>Use reviewed policy wording and real accountable contact details. This editor does not supply legal advice or invent an organization&apos;s policies.</p></header>
    {error && <p className="policy-form-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!heads ? <><p role="status">Loading policies…</p><button className="btn light" onClick={load}>Try loading again</button></> : <div className="policy-admin-grid"><aside><ul className="policy-admin-list">{heads.map(item => <li key={item.kind}><button aria-pressed={item.kind === kind} onClick={() => { setKind(item.kind); setCopy(null); setNotice(""); }}><strong>{POLICY_LABELS[item.kind]}</strong><small>{item.published ? `Published · v${item.published.number}` : "Unpublished"}{item.draft ? " · Draft saved" : ""}</small></button></li>)}</ul><p><Link className="btn light" href="/policies">View policy centre</Link></p></aside>
      {head && <div><Editor key={`${kind}:${head.revision}:${reset}`} head={head} initial={copy} onSaved={saved} onError={onError} onReload={load} />
        <History key={`${kind}:${head.revision}`} kind={kind} onError={onError} onCopy={value => { setCopy(value); setReset(value => value + 1); setNotice("An earlier version was copied into the editor. Save it as a new draft before publication."); }} /></div>}
    </div>}
  </MainContent>;
}

function Editor({ head, initial, onSaved, onError, onReload }: { head: PolicyHead; initial: PolicyContent | null; onSaved: (head: PolicyHead, notice: string) => void; onError: (error: unknown) => string; onReload: () => void }) {
  const original = head.draft || head.published?.content || blank(head.kind);
  const [value, setValue] = useState<PolicyContent>(initial || original), [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [preview, setPreview] = useState(false);
  const [withdraw, setWithdraw] = useState(false), [reason, setReason] = useState(""), [confirmed, setConfirmed] = useState(false);
  const dirty = JSON.stringify(value) !== JSON.stringify(head.draft);
  const submitGuard = useRef(false);
  function edit(key: keyof PolicyContent, text: string) { setValue(current => ({ ...current, [key]: text })); setReviewed(false); }
  async function command(action: "draft" | "publish" | "withdraw") {
    if (submitGuard.current) return;
    submitGuard.current = true; setBusy(true); setError("");
    try {
      const payload = action === "draft" ? { revision: head.revision, content: value } : action === "publish" ? { revision: head.revision, reviewed } : { revision: head.revision, reviewed: confirmed, reason };
      const result = await adminFetch<PolicyHead>(`/admin/site-policies/${head.kind}/${action}`, { method: action === "draft" ? "PUT" : "POST", body: JSON.stringify(payload) });
      setWithdraw(false); onSaved(result, action === "draft" ? "draft saved privately." : action === "publish" ? `version ${result.published?.number} published.` : "policy and public history withdrawn.");
    } catch (error) { setError(onError(error)); }
    finally { submitGuard.current = false; setBusy(false); }
  }
  return <section className="policy-card"><h2>{POLICY_LABELS[head.kind]}</h2><p>{head.published ? <>Current public version: {head.published.number} · <Link className="text-link" href={`/policies/${head.kind}`}>Read public page</Link></> : "Nothing is currently published."}</p>
    {head.withdraw_reason && <p>Last withdrawal reason (team only): {head.withdraw_reason}</p>}
    <form className="policy-form" onSubmit={event => { event.preventDefault(); command("draft"); }}><fieldset disabled={busy}>
      <label>Policy title<input required maxLength={160} value={value.title} onChange={event => edit("title", event.target.value)} /></label>
      <label>Summary<textarea rows={3} maxLength={600} value={value.summary} onChange={event => edit("summary", event.target.value)} /></label>
      <label>Organization name<input maxLength={160} value={value.organization} onChange={event => edit("organization", event.target.value)} /></label>
      <label>Public contact email<input maxLength={254} value={value.contact_email} onChange={event => edit("contact_email", event.target.value)} autoComplete="off" /></label>
      <label>Public phone (optional)<input maxLength={30} value={value.contact_phone} onChange={event => edit("contact_phone", event.target.value)} /></label>
      <label>Postal address{head.kind !== "grievance" && " (optional)"}<textarea rows={3} maxLength={1000} value={value.postal_address} onChange={event => edit("postal_address", event.target.value)} /></label>
      <label>Accountable grievance contact{head.kind !== "grievance" && " (optional)"}<input maxLength={160} value={value.grievance_officer} onChange={event => edit("grievance_officer", event.target.value)} /></label>
      <label>Policy text (Markdown)<textarea rows={15} maxLength={20000} value={value.body} onChange={event => edit("body", event.target.value)} /></label>
      <button className="btn" type="submit">{busy ? "Saving…" : "Save private draft"}</button>
    </fieldset></form>
    <div className="policy-actions"><button className="btn light" aria-expanded={preview} onClick={() => setPreview(current => !current)}>Preview text and contact details</button></div>
    {preview && <section className="policy-card" aria-label="Draft preview"><h2>{value.title || "Untitled draft"}</h2><p>{value.summary}</p><PolicyBody content={value} /></section>}
    <div className="policy-form"><p>{dirty ? "Save the current text as a private draft before publishing." : "Publication uses the saved draft."} Published snapshots cannot be edited; later changes create a new version.</p>
      <label className="policy-check"><input type="checkbox" checked={reviewed} disabled={busy || dirty || !head.draft} onChange={event => setReviewed(event.target.checked)} />I confirm this saved version, organization details and contacts are reviewed and approved for public publication.</label>
      <div className="policy-actions"><button className="btn" disabled={busy || dirty || !head.draft || !reviewed} onClick={() => command("publish")}>Publish reviewed version</button>{head.published && <button className="btn light" disabled={busy} onClick={() => setWithdraw(true)}>Withdraw public policy</button>}</div>
    </div>
    {error && <div className="policy-form-error" role="alert"><p>{error} Your editor text is kept here.</p><button className="btn light" onClick={onReload} disabled={busy}>Reload latest (replaces editor text)</button></div>}
    <Dialog open={withdraw} onClose={() => { if (!busy) setWithdraw(false); }} label="Withdraw public policy" className="policy-withdraw-dialog"><h2>Withdraw public policy?</h2><p>The current policy and its public version history will become unavailable. Snapshots remain in the administrator history. Previously read or downloaded copies cannot be recalled.</p>
      <form className="policy-form" onSubmit={event => { event.preventDefault(); command("withdraw"); }}><label>Withdrawal reason (team only)<textarea required minLength={10} maxLength={1000} rows={3} value={reason} disabled={busy} onChange={event => setReason(event.target.value)} /></label>
        <label className="policy-check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />I confirm removal of this policy and its public history.</label>
        {error && <p role="alert" className="policy-form-error">{error}</p>}
        <div className="policy-actions"><button type="submit" className="btn" disabled={busy || !confirmed}>Confirm withdrawal</button><button type="button" className="btn light" disabled={busy} onClick={() => setWithdraw(false)}>Keep published</button></div>
      </form></Dialog>
  </section>;
}

function History({ kind, onCopy, onError }: { kind: PolicyKind; onCopy: (content: PolicyContent) => void; onError: (error: unknown) => string }) {
  const [page, setPage] = useState(1), [data, setData] = useState<PolicyHistory | null>(null), [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    adminFetch<PolicyHistory>(`/admin/site-policies/${kind}/versions?page=${page}`, { cache: "no-store" }).then(value => { if (active) { setData(value); setError(""); } }).catch(error => { if (active) setError(onError(error)); });
    return () => { active = false; };
  }, [kind, page, onError, refresh]);
  return <section className="policy-card policy-history"><h2>Published version history</h2>{error && <div role="alert"><p>{error}</p><button className="btn light" onClick={() => setRefresh(value => value + 1)}>Try history again</button></div>}{!data ? !error && <p role="status">Loading history…</p> : !data.items.length ? <p>No versions have been published.</p> : data.items.map(item => <details key={item.number}><summary>Version {item.number} · {item.is_public ? "Public" : "Withdrawn"} · {policyDate(item.published_at)}</summary><h3>{item.content.title}</h3><p>{item.content.summary}</p><PolicyBody content={item.content} /><button className="btn light" onClick={() => onCopy(item.content)}>Use version {item.number} in editor</button></details>)}
    {data && data.total > data.page_size && <div className="policy-actions"><button className="btn light" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous versions</button><span>Page {page}</span><button className="btn light" disabled={page * data.page_size >= data.total} onClick={() => setPage(value => value + 1)}>Next versions</button></div>}
  </section>;
}
