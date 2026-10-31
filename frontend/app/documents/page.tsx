"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, describeUploadCheck, formatBytes, normalizeTag, type AccountRequest, type CustomerDocument, type ReportItem, type TicketStatus } from "@homexo/shared";
import PropertyIntakeFields, { EMPTY_INTAKE } from "../PropertyIntakeFields";
import { api } from "../api";
import "./documents.css";
import CustomerNav from "../account/CustomerNav";
import { signOut, useSession, type Session } from "../account/session";
import { openDocuments, readRef, type Ref } from "./ref";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx";
const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function DocumentsPage() {
  const [ref, setRef] = useState<Ref | null>(null);
  const [ticket, setTicket] = useState<TicketStatus | null>(null);
  const [form, setForm] = useState<Ref>({ ticket_number: "", contact: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const session = useSession();

  async function open(next: Ref) {
    setError("");
    setLoading(true);
    try {
      setTicket(await api.lookupTicket(next.ticket_number, next.contact));
      setRef(next);
      openDocuments(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't open that request.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const saved = readRef();
    if (saved) open(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <CustomerNav />
      <main>
        <section className="dc-band">
          <div className="wrap">
            <div className="eyebrow">Document repository</div>
            <h1>Your case documents</h1>
            <p>Your property details create a document checklist automatically. Upload each document under its requested tag. Your case team obtains official records and the advocate confirms what applies to your case.</p>
          </div>
        </section>
        <div className="wrap dc-body">
          {!ticket || !ref ? (
            session ? <AccountRequests session={session} loading={loading} error={error} onOpen={open} /> :
            <form className="dc-card dc-signin" onSubmit={(e) => { e.preventDefault(); open({ ticket_number: form.ticket_number.trim(), contact: form.contact.trim() }); }}>
              <h2>Open your request</h2>
              <label>Ticket number<input required placeholder="HX-261018-ABC123" value={form.ticket_number} onChange={(e) => setForm({ ...form, ticket_number: e.target.value })} /></label>
              <label>Phone or email<input required placeholder="Used when you raised it" value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} /></label>
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="btn" disabled={loading}>{loading ? "Opening…" : "Open documents"}</button>
              <p className="dc-muted" style={{ margin: 0 }}>Or <Link href="/account" style={{ color: "var(--forest2)", fontWeight: 800 }}>sign in with your phone</Link> to see all your requests.</p>
            </form>
          ) : (
            <Repository ticket={ticket} reference={ref} onChange={setTicket} />
          )}
        </div>
      </main>
      <footer className="footer">
        <div className="wrap" style={{ fontSize: 11, color: "#a4bcb2", lineHeight: 1.7 }}>
          Files are kept in Homexo's private cloud storage and seen only by your case team. Download links expire after a few minutes. When you upload, the first pages are checked automatically by an AI service for document type, readability and dates, so we can tell you quickly if something needs fixing. An advocate still reviews every document.
        </div>
      </footer>
    </>
  );
}

// Signed in: pick one of the account's requests instead of typing the ticket number.
function AccountRequests({ session, loading, error, onOpen }: { session: Session; loading: boolean; error: string; onOpen: (ref: Ref) => void }) {
  const [requests, setRequests] = useState<AccountRequest[] | null>(null);
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    api.getAccount(session.token)
      .then((account) => setRequests(account.requests.filter((r) => r.kind === "request")))
      .catch((e) => (e instanceof ApiError && e.status === 401 ? signOut() : setLoadError(e instanceof Error ? e.message : "We couldn't load your requests.")));
  }, [session.token]);
  return (
    <section className="dc-card" style={{ maxWidth: 640 }}>
      <h2>Choose a request</h2>
      <p className="dc-muted">Requests raised with {session.profile.phone}.</p>
      {(error || loadError) && <p className="dc-error" role="alert">{error || loadError}</p>}
      {requests === null && !loadError && <p className="dc-muted">Loading…</p>}
      {requests?.length === 0 && <p className="dc-muted">No property requests on this number yet. <Link href="/#callback" style={{ color: "var(--forest2)", fontWeight: 800 }}>Request a callback</Link> to start one.</p>}
      <ul className="dc-files">
        {requests?.map((r) => (
          <li key={r.ticket_number}>
            <div className="dc-file-main"><b>{r.service_name}</b><small>{r.ticket_number} · {r.status_label}{r.needs_you ? ` · ${r.needs_you}` : ""}</small></div>
            <button className="btn small light" disabled={loading} onClick={() => onOpen({ ticket_number: r.ticket_number, contact: session.profile.contact })}>Open</button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Repository({ ticket, reference, onChange }: { ticket: TicketStatus; reference: Ref; onChange: (t: TicketStatus) => void }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const report = ticket.report;
  const request = ticket.document_request;
  const [intake, setIntake] = useState(request?.intake ?? EMPTY_INTAKE);
  const docs = new Map(ticket.documents.map((d) => [d.id, d]));
  const reportTags = (report?.items ?? request?.items ?? []).map((i) => i.tag);
  const checking = ticket.documents.some((d) => d.check?.status === "pending");
  const polls = useRef(0);

  // Upload checks finish a few seconds after the upload; refresh until they do (bounded, so a stuck check stops polling).
  useEffect(() => {
    if (!checking) { polls.current = 0; return; }
    if (polls.current >= 15) return;
    const timer = setTimeout(async () => {
      polls.current += 1;
      try { onChange(await api.lookupTicket(reference.ticket_number, reference.contact)); } catch { /* keep the current view */ }
    }, 4000);
    return () => clearTimeout(timer);
  }, [checking, ticket, reference, onChange]);

  async function run(key: string, action: () => Promise<TicketStatus>, done: string) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      onChange(await action());
      setNotice(done);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy("");
    }
  }

  const upload = (file: File, tag: string, note = "") =>
    run(`upload-${tag}`, () => api.uploadDocument(reference, file, { tag, note }), `Uploaded ${file.name}${tag ? ` under #${tag}` : ""}.`);

  return (
    <>
      <div className="dc-ticket">
        <div><span className="tiny-label">Ticket</span><b>{ticket.ticket_number}</b><small>{ticket.service_name}{ticket.package ? ` · ${ticket.package}` : ""}</small></div>
        <span className={`status-pill status-${ticket.status}`}>{ticket.status_label}</span>
      </div>
      {(error || notice) && <p className={error ? "dc-error" : "dc-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}
      {request && request.origin !== "not_applicable" && <section className="dc-card" style={{ marginBottom: 20 }}>
        <h2>{request.missing_count ? "Documents we need from you" : "Your document request"}</h2>
        <p role="status">{request.prompt}</p>
        {request.questions.length > 0 && <p className="dc-muted">Complete the property details below so we can tailor the request. Unknown answers remain questions for the advocate.</p>}
        {ticket.can_upload && !report && <details open={request.questions.length > 0}><summary>Property details and automatic checklist</summary>
          <form onSubmit={e => { e.preventDefault(); run("intake", () => api.updatePropertyIntake(reference, intake), "Property details saved. Your document checklist has been updated."); }}>
            <PropertyIntakeFields value={intake} onChange={setIntake} identifiers />
            <button className="btn small" style={{ marginTop: 12 }} disabled={busy === "intake"}>{busy === "intake" ? "Updating…" : "Update required documents"}</button>
          </form>
        </details>}
        <small className="dc-muted">{request.note}</small>
      </section>}

      <div className="dc-layout">
        <section className="dc-card">
          {report ? (
            <>
              <div className="dc-card-head">
                <div>
                  <h2>Preliminary report</h2>
                  <small>{report.lawyer_name ? `From ${report.lawyer_name}` : "From your case team"}{report.issued_at ? ` · ${dateFormat.format(new Date(report.issued_at))}` : ""}</small>
                </div>
                <a className="btn small light" href={api.fileUrl(report.preliminary_pdf_url)} target="_blank" rel="noreferrer">Print / PDF</a>
              </div>
              {report.signed_report_url && (
                <div className="dc-signed">
                  <div><b>Your signed legal report is ready</b><small>Signed by the advocates{report.signed_at ? ` on ${dateFormat.format(new Date(report.signed_at))}` : ""}.</small></div>
                  <a className="btn small gold" href={api.fileUrl(report.signed_report_url)} target="_blank" rel="noreferrer">Download</a>
                </div>
              )}
              {report.status === "final_generated" && <p className="dc-banner">Every document is checked. Your final report is with the advocates for signature.</p>}
              <div className="dc-progress" aria-label={`${report.progress.done} of ${report.progress.total} documents accepted`}>
                <div style={{ width: `${report.progress.total ? (report.progress.done / report.progress.total) * 100 : 0}%` }} />
              </div>
              <small className="dc-muted">{report.progress.done} of {report.progress.total} checklist items done</small>
              <ol className="dc-checklist">
                {report.items.map((item) => (
                  <ChecklistItem key={item.id} item={item} docs={item.documents.map((id) => docs.get(id)).filter(Boolean) as CustomerDocument[]}
                    canUpload={ticket.can_upload && report.status === "issued"} busy={busy === `upload-${item.tag}`} onUpload={(f) => upload(f, item.tag)} />
                ))}
              </ol>
              <details className="dc-sections">
                <summary>Read the full preliminary report</summary>
                {report.sections.filter((s) => s.text.trim()).map((s) => (
                  <div key={s.key}><h3>{s.heading}</h3><p>{s.text}</p></div>
                ))}
              </details>
            </>
          ) : (
            <>
              <h2>Automatically requested documents</h2>
              <p className="dc-muted">Upload the documents below to start verification. Received means uploaded, not legally verified. The advocate may add or waive requirements after reviewing your case.</p>
              <ol className="dc-checklist">{request?.items.map(item => <ChecklistItem key={item.id} item={item} docs={item.documents.map(id => docs.get(id)).filter(Boolean) as CustomerDocument[]} canUpload={ticket.can_upload} busy={busy === `upload-${item.tag}`} onUpload={file => upload(file, item.tag)} />)}</ol>
              {!request?.items.length && <p>The case team will confirm the documents needed for this service.</p>}
            </>
          )}
        </section>

        <section className="dc-card">
          <h2>All documents</h2>
          {ticket.can_upload && <UploadForm tags={reportTags} busy={busy.startsWith("upload")} onUpload={upload} />}
          {ticket.documents.length === 0 ? <p className="dc-muted">No documents yet.</p> : (
            <ul className="dc-files">
              {ticket.documents.map((d) => (
                <li key={d.id}>
                  <div className="dc-file-main">
                    <a href={api.fileUrl(d.download_url)} target="_blank" rel="noreferrer"><b>{d.filename}</b></a>
                    <small>{formatBytes(d.size)} · {dateFormat.format(new Date(d.at))} · {d.uploaded_by === "you" ? "You" : "Homexo"}{d.note ? ` · ${d.note}` : ""}</small>
                    {(() => { const c = describeUploadCheck(d.check); return c && <small className={c.warn ? "dc-check warn" : "dc-check"} role={c.warn ? "status" : undefined}>{c.text}</small>; })()}
                  </div>
                  {d.uploaded_by === "you" && d.can_delete && ticket.can_upload ? (
                    <TagPicker value={d.tag ?? ""} tags={reportTags} disabled={busy === d.id}
                      onChange={(tag) => run(d.id, () => api.tagDocument(reference, d.id, tag), tag ? `Filed under #${tag}.` : "Tag removed.")} />
                  ) : <span className="dc-tag">{d.tag ? `#${d.tag}` : "untagged"}</span>}
                  {d.can_delete && ticket.can_upload && (
                    <button className="dc-link" disabled={busy === d.id} onClick={() => run(d.id, () => api.deleteDocument(reference, d.id), `Removed ${d.filename}.`)}>Remove</button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function ChecklistItem({ item, docs, canUpload, busy, onUpload }: { item: ReportItem; docs: CustomerDocument[]; canUpload: boolean; busy: boolean; onUpload: (f: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const done = item.status === "verified" || item.status === "waived";
  const homexo = item.fetch_by === "homexo";
  return (
    <li className={`dc-item ${item.status}${done ? " done" : ""}`}>
      <span className="dc-box" aria-hidden>{done ? "✓" : ""}</span>
      <div className="dc-item-body">
        <div className="dc-item-top">
          <b>{item.label}</b>
          <span className="dc-tag">#{item.tag}</span>
          <span className={`dc-pill ${homexo && item.status === "pending" ? "fetching" : item.status}`}>{item.status_label}</span>
        </div>
        {item.guidance && <small>{item.guidance}</small>}
        {homexo && item.source && item.status === "pending" && <small className="dc-source">We get this from {item.source.name}, so you needn't upload it. If you already have a copy, you can add it.</small>}
        {item.status === "rejected" && item.note && <p className="dc-reject">{item.note}</p>}
        {docs.length > 0 && (
          <ul className="dc-linked">
            {docs.map((d) => <li key={d.id}><a href={api.fileUrl(d.download_url)} target="_blank" rel="noreferrer">{d.filename}</a></li>)}
          </ul>
        )}
      </div>
      {canUpload && !done && (
        <>
          <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
          <button className={`btn small${homexo ? " light" : ""}`} disabled={busy} onClick={() => input.current?.click()}>{busy ? "Uploading…" : docs.length ? "Add file" : "Upload"}</button>
        </>
      )}
    </li>
  );
}

function TagPicker({ value, tags, disabled, onChange }: { value: string; tags: string[]; disabled?: boolean; onChange: (tag: string) => void }) {
  const known = value === "" || tags.includes(value);
  return (
    <select className="dc-select" value={known ? value : `custom:${value}`} disabled={disabled} aria-label="Tag"
      onChange={(e) => {
        const next = e.target.value;
        if (next === "__other") {
          const typed = normalizeTag(window.prompt("Tag for this document, e.g. gift-deed") ?? "");
          if (typed) onChange(typed);
        } else if (!next.startsWith("custom:")) onChange(next);
      }}>
      <option value="">Untagged</option>
      {tags.map((t) => <option key={t} value={t}>#{t}</option>)}
      {!known && <option value={`custom:${value}`}>#{value}</option>}
      <option value="__other">Other tag…</option>
    </select>
  );
}

function UploadForm({ tags, busy, onUpload }: { tags: string[]; busy: boolean; onUpload: (f: File, tag: string, note: string) => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [tag, setTag] = useState("");
  const [custom, setCustom] = useState("");
  const [note, setNote] = useState("");
  const input = useRef<HTMLInputElement>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    await onUpload(file, tag === "__other" ? normalizeTag(custom) : tag, note.trim());
    setFile(null);
    setNote("");
    setCustom("");
    if (input.current) input.current.value = "";
  }

  return (
    <form className="dc-upload" onSubmit={submit}>
      <label className="dc-drop">
        <input ref={input} type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <span>{file ? `${file.name} · ${formatBytes(file.size)}` : "Choose a file: PDF, photo or Word, up to 25 MB"}</span>
      </label>
      <div className="dc-upload-row">
        <select className="dc-select" value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Tag">
          <option value="">No tag yet</option>
          {tags.map((t) => <option key={t} value={t}>#{t}</option>)}
          <option value="__other">Other tag…</option>
        </select>
        {tag === "__other" && <input className="dc-input" placeholder="e.g. gift-deed" value={custom} onChange={(e) => setCustom(e.target.value)} aria-label="Your tag" />}
        <input className="dc-input" placeholder="Note (optional)" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" />
        <button className="btn small" disabled={!file || busy}>{busy ? "Uploading…" : "Upload"}</button>
      </div>
    </form>
  );
}
