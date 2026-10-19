"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { formatBytes, normalizeTag, type CustomerDocument, type ReportItem, type TicketStatus } from "@homexo/shared";
import { api } from "../api";
import "./documents.css";
import { openDocuments, readRef, type Ref } from "./ref";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx";
const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function DocumentsPage() {
  const [ref, setRef] = useState<Ref | null>(null);
  const [ticket, setTicket] = useState<TicketStatus | null>(null);
  const [form, setForm] = useState<Ref>({ ticket_number: "", contact: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
      <header className="header">
        <div className="wrap navrow">
          <Link className="brand" href="/" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></Link>
          <nav className="dc-nav" aria-label="Customer">
            <Link href="/#track">Track a request</Link>
            <Link href="/documents" className="active">My documents</Link>
          </nav>
        </div>
      </header>
      <main>
        <section className="dc-band">
          <div className="wrap">
            <div className="eyebrow">Document repository</div>
            <h1>Your case documents</h1>
            <p>Share documents with your lawyer and tag each one. When the preliminary report arrives, it lists what is needed with a tag for each; file your uploads under those tags. Public records like the EC, khata and RTC we get from the government portals for you.</p>
          </div>
        </section>
        <div className="wrap dc-body">
          {!ticket || !ref ? (
            <form className="dc-card dc-signin" onSubmit={(e) => { e.preventDefault(); open({ ticket_number: form.ticket_number.trim(), contact: form.contact.trim() }); }}>
              <h2>Open your request</h2>
              <label>Ticket number<input required placeholder="HX-261018-ABC123" value={form.ticket_number} onChange={(e) => setForm({ ...form, ticket_number: e.target.value })} /></label>
              <label>Phone or email<input required placeholder="Used when you raised it" value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} /></label>
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="btn" disabled={loading}>{loading ? "Opening…" : "Open documents"}</button>
            </form>
          ) : (
            <Repository ticket={ticket} reference={ref} onChange={setTicket} />
          )}
        </div>
      </main>
      <footer className="footer">
        <div className="wrap" style={{ fontSize: 11, color: "#a4bcb2", lineHeight: 1.7 }}>
          Files are kept in Homexo's private cloud storage and seen only by your case team. Download links expire after a few minutes.
        </div>
      </footer>
    </>
  );
}

function Repository({ ticket, reference, onChange }: { ticket: TicketStatus; reference: Ref; onChange: (t: TicketStatus) => void }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const report = ticket.report;
  const docs = new Map(ticket.documents.map((d) => [d.id, d]));
  const reportTags = report?.items.map((i) => i.tag) ?? [];

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
              <h2>Preliminary report</h2>
              <p className="dc-muted">Your lawyer will send a preliminary report listing the documents needed, each with a tag. Until then you can upload what you have and tag it; you can link it to the report's tags later.</p>
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
