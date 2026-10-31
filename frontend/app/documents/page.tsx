"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, describeUploadCheck, formatBytes, normalizeTag, type AccountRequest, type CustomerDocument, type DocumentJourney, type ReportItem, type TicketStatus } from "@homexo/shared";
import PropertyIntakeFields, { EMPTY_INTAKE } from "../PropertyIntakeFields";
import { api } from "../api";
import "./documents.css";
import CustomerNav from "../account/CustomerNav";
import { signOut, useSession, type Session } from "../account/session";
import { openDocuments, readRef, type Ref } from "./ref";
import { CheckList, DocumentMap, MapLegend, Stepper, revealCheck } from "./Journey";

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
            <div className="eyebrow">Your documents</div>
            <h1>Send your documents, see every check</h1>
            <p>We ask for one document at a time and tell you why we need it. Government records we fetch ourselves. As your advocate checks each one, you can see what is verified, what is being checked and what still needs you.</p>
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
  const [skipped, setSkipped] = useState<string[]>([]);
  const report = ticket.report;
  const request = ticket.document_request;
  const journey = request?.journey;
  const [intake, setIntake] = useState(request?.intake ?? EMPTY_INTAKE);
  const docs = new Map(ticket.documents.map((d) => [d.id, d]));
  const items = request?.items ?? report?.items ?? [];
  const labels = new Map(items.map((i) => [i.tag, i.label]));
  const checking = ticket.documents.some((d) => d.check?.status === "pending");
  const polls = useRef(0);
  const uploadsOpen = ticket.can_upload && (!report || report.status === "issued");

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

  // Several files at once (e.g. one photo per page) go up one after another under the same document.
  const upload = (files: File[], tag: string, note = "") =>
    run(`upload-${tag}`, async () => {
      let latest = ticket;
      for (const file of files) latest = await api.uploadDocument(reference, file, { tag, note });
      return latest;
    }, `Thank you. ${files.length === 1 ? files[0].name : `${files.length} files`} added${tag && labels.get(tag) ? ` to ${labels.get(tag)}` : ""}. We'll check ${files.length === 1 ? "it" : "them"} now.`);

  // Ask for one document at a time: a rejected upload first, then the next one still needed, skipping any the customer put off.
  const yours = items.filter((i) => i.fetch_by === "customer");
  const needed = yours.filter((i) => i.status === "pending" || i.status === "rejected");
  const next = uploadsOpen ? (needed.find((i) => i.id === journey?.next_upload && !skipped.includes(i.id)) ?? needed.find((i) => !skipped.includes(i.id))) : undefined;
  const yoursDone = yours.length - needed.length;

  const renderItem = (item: ReportItem) => (
    <ItemRow item={item} docs={item.documents.map((id) => docs.get(id)).filter(Boolean) as CustomerDocument[]}
      canUpload={uploadsOpen && item.status !== "verified" && item.status !== "waived"} busy={busy === `upload-${item.tag}`} onUpload={(f) => upload(f, item.tag)} />
  );

  return (
    <>
      <div className="dc-ticket">
        <div><span className="tiny-label">Ticket</span><b>{ticket.ticket_number}</b><small>{ticket.service_name}{ticket.package ? ` · ${ticket.package}` : ""}</small></div>
        <span className={`status-pill status-${ticket.status}`}>{ticket.status_label}</span>
      </div>
      {(error || notice) && <p className={error ? "dc-error" : "dc-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}
      {journey && <Stepper journey={journey} />}

      {report?.signed_report_url && (
        <div className="dc-signed">
          <div><b>Your signed legal report is ready</b><small>Signed by the advocates{report.signed_at ? ` on ${dateFormat.format(new Date(report.signed_at))}` : ""}.</small></div>
          <a className="btn small gold" href={api.fileUrl(report.signed_report_url)} target="_blank" rel="noreferrer">Download</a>
        </div>
      )}

      {request && ticket.can_upload && !report && request.questions.length > 0 && (
        <section className="dc-card dc-questions">
          <h2>First, a few questions about the property</h2>
          <p className="dc-muted">Your answers decide which documents we ask for, so you don&apos;t send anything you don&apos;t need. Choose &ldquo;Not sure&rdquo; if you don&apos;t know; your advocate will find out.</p>
          <form onSubmit={(e) => { e.preventDefault(); run("intake", () => api.updatePropertyIntake(reference, intake), "Thanks. Your document list is updated."); }}>
            <PropertyIntakeFields value={intake} onChange={setIntake} identifiers />
            <button className="btn small" style={{ marginTop: 12 }} disabled={busy === "intake"}>{busy === "intake" ? "Saving…" : "Save and update my list"}</button>
          </form>
        </section>
      )}

      {next && (
        <section className="jn-next" aria-label="Next document to upload">
          <div>
            <div className="eyebrow">Next document · {yoursDone + 1} of {yours.length}</div>
            <h2>{next.status === "rejected" ? `Please upload your ${next.label.toLowerCase()} again` : next.label}</h2>
            {next.status === "rejected" && next.note && <p className="jn-reject">Your advocate says: {next.note}</p>}
            {next.guidance && <p>{next.guidance}</p>}
            <p className="jn-why">{whyText(next, journey)}</p>
            <div className="jn-count" aria-hidden><div style={{ width: `${yours.length ? (yoursDone / yours.length) * 100 : 0}%` }} /></div>
            <div className="jn-next-meta">
              <span>{yoursDone} of {yours.length} of your documents in</span>
              {needed.length > 1 && <button type="button" onClick={() => setSkipped([...skipped, next.id])}>I don&apos;t have it now, show the next one</button>}
              {skipped.length > 0 && <button type="button" onClick={() => setSkipped([])}>Show skipped ones again</button>}
            </div>
          </div>
          <DropZone busy={busy === `upload-${next.tag}`} onFiles={(files) => upload(files, next.tag)} label={`Drop your ${next.label.toLowerCase()} here`} />
        </section>
      )}
      {uploadsOpen && !next && yours.length > 0 && needed.length === 0 && (
        <p className="dc-notice" role="status">You&apos;ve sent everything we need for now. We&apos;ll message you if the advocate needs anything else.</p>
      )}

      <div className="dc-layout">
        <section className="dc-card">
          <div className="dc-card-head">
            <div>
              <h2>What we&apos;re checking</h2>
              <small>Each question is answered by the documents under it. Tap one to see or add its documents.</small>
            </div>
            {report && <a className="btn small light" href={api.fileUrl(report.preliminary_pdf_url)} target="_blank" rel="noreferrer">Report PDF</a>}
          </div>
          {journey ? <CheckList journey={journey} items={items} renderItem={renderItem}
            open={journey.checks.filter((c) => c.status === "problem" || c.flags.length || (next && c.tags.includes(next.tag))).map((c) => c.key)} /> : (
            <ol className="jn-items">{items.map((i) => <li key={i.id}>{renderItem(i)}</li>)}</ol>
          )}
          {!items.length && <p>The case team will confirm the documents needed for this service.</p>}
          {request?.note && <p className="dc-muted" style={{ marginTop: 12 }}>{request.note}</p>}
          {report && report.sections.some((s) => s.text.trim()) && (
            <details className="dc-sections">
              <summary>Read your advocate&apos;s preliminary report{report.lawyer_name ? ` from ${report.lawyer_name}` : ""}</summary>
              {report.sections.filter((s) => s.text.trim()).map((s) => (
                <div key={s.key}><h3>{s.heading}</h3><p>{s.text}</p></div>
              ))}
            </details>
          )}
        </section>

        <div className="dc-side">
          {journey && journey.groups.length > 0 && (
            <section className="dc-card">
              <h2>How your documents fit together</h2>
              <p className="dc-muted">We first confirm who is selling and how they came to own the property. Then we check it is free of loans, matches government records, is approved and has no court cases. The advocate weighs it all in the final opinion.</p>
              <DocumentMap journey={journey} onPick={revealCheck} />
              <MapLegend />
            </section>
          )}

          <section className="dc-card">
            <h2>All your files</h2>
            {ticket.can_upload && <OtherUpload items={items} busy={busy.startsWith("upload")} onUpload={upload} />}
            {ticket.documents.length === 0 ? <p className="dc-muted">No files yet.</p> : (
              <ul className="dc-files">
                {ticket.documents.map((d) => (
                  <li key={d.id}>
                    <div className="dc-file-main">
                      <a href={api.fileUrl(d.download_url)} target="_blank" rel="noreferrer"><b>{d.filename}</b></a>
                      <small>{formatBytes(d.size)} · {dateFormat.format(new Date(d.at))} · {d.uploaded_by === "you" ? "You" : "Homexo"}{d.note ? ` · ${d.note}` : ""}</small>
                      <CheckLine doc={d} />
                    </div>
                    {d.uploaded_by === "you" && d.can_delete && ticket.can_upload ? (
                      <TagPicker value={d.tag ?? ""} items={items} disabled={busy === d.id}
                        onChange={(tag) => run(d.id, () => api.tagDocument(reference, d.id, tag), tag ? `Moved to ${labels.get(tag) ?? tag}.` : "Marked as not sure.")} />
                    ) : <span className="dc-kind">{d.tag ? labels.get(d.tag) ?? d.tag.replaceAll("-", " ") : "Not sorted yet"}</span>}
                    {d.can_delete && ticket.can_upload && (
                      <button className="dc-link" disabled={busy === d.id} onClick={() => run(d.id, () => api.deleteDocument(reference, d.id), `Removed ${d.filename}.`)}>Remove</button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function whyText(item: ReportItem, journey?: DocumentJourney) {
  const check = journey?.checks.find((c) => c.tags.includes(item.tag));
  return check ? `Why we need it: it helps answer “${check.question}”` : "";
}

function CheckLine({ doc }: { doc: CustomerDocument }) {
  const c = describeUploadCheck(doc.check);
  return c ? <small className={c.warn ? "dc-check warn" : "dc-check"} role={c.warn ? "status" : undefined}>{c.text}</small> : null;
}

const STATUS_ICON: Record<string, string> = { verified: "✓", waived: "✓", received: "…", rejected: "!", pending: "" };

function ItemRow({ item, docs, canUpload, busy, onUpload }: { item: ReportItem; docs: CustomerDocument[]; canUpload: boolean; busy: boolean; onUpload: (f: File[]) => void }) {
  const homexo = item.fetch_by === "homexo";
  return (
    <div className={`jn-item ${item.status}`}>
      <span className="jn-item-status" aria-hidden>{STATUS_ICON[item.status]}</span>
      <div className="jn-item-top">
        <b>{item.label}</b>
        <span className={`dc-pill ${homexo && item.status === "pending" ? "fetching" : item.status}`}>{item.status_label}</span>
      </div>
      <div className="jn-item-body">
        {item.guidance && <small>{item.guidance}</small>}
        {homexo && item.source && item.status === "pending" && <small className="dc-source">We get this from {item.source.name}, so you don&apos;t need to upload it. If you already have a copy, you can add it.</small>}
        {item.status === "rejected" && item.note && <p className="dc-reject">Your advocate says: {item.note}</p>}
        {docs.length > 0 && (
          <ul className="jn-files">
            {docs.map((d) => <li key={d.id}><a href={api.fileUrl(d.download_url)} target="_blank" rel="noreferrer">{d.filename}</a><CheckLine doc={d} /></li>)}
          </ul>
        )}
        {canUpload && homexo && item.status === "pending" && !docs.length ? (
          <DropZone compact quiet busy={busy} onFiles={onUpload} label="Already have a copy? You can add it." />
        ) : canUpload && (
          <DropZone compact busy={busy} onFiles={onUpload}
            label={item.status === "rejected" ? "Upload a better copy" : docs.length ? "Add more pages" : homexo ? "Have a copy? Add it" : "Upload"} />
        )}
      </div>
    </div>
  );
}

// Drag and drop, choose files, or (on phones) take a photo. Several files are fine, e.g. one photo per page.
function DropZone({ label, busy, onFiles, compact, quiet }: { label: string; busy: boolean; onFiles: (files: File[]) => void; compact?: boolean; quiet?: boolean }) {
  const [over, setOver] = useState(false);
  const files = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const take = (list: FileList | null) => { const picked = Array.from(list ?? []); if (picked.length) onFiles(picked); };
  return (
    <div className={`jn-drop${compact ? " compact" : ""}${quiet ? " quiet" : ""}${over ? " over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) take(e.dataTransfer.files); }}>
      <input ref={files} type="file" accept={ACCEPT} multiple hidden onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
      <div>
        <b>{busy ? "Uploading…" : label}</b>
        {!compact && <><br /><small>PDF, photo or Word file, up to 25 MB each. Photos of each page are fine.</small></>}
      </div>
      <div className="jn-drop-actions">
        <button type="button" className={`btn small${compact ? " light" : " gold"}`} disabled={busy} onClick={() => files.current?.click()}>{compact ? "Choose file" : "Choose files"}</button>
        <button type="button" className="btn small light jn-camera" disabled={busy} onClick={() => camera.current?.click()}>Take a photo</button>
      </div>
    </div>
  );
}

// Labels, not tags: the customer picks "Sale deed of the present owner", the server files it under #sale-deed.
function TagPicker({ value, items, disabled, onChange }: { value: string; items: ReportItem[]; disabled?: boolean; onChange: (tag: string) => void }) {
  const known = value === "" || items.some((i) => i.tag === value);
  return (
    <select className="dc-select" value={known ? value : `custom:${value}`} disabled={disabled} aria-label="What is this file?"
      onChange={(e) => {
        const next = e.target.value;
        if (next === "__other") {
          const typed = normalizeTag(window.prompt("What is this document? e.g. Gift deed") ?? "");
          if (typed) onChange(typed);
        } else if (!next.startsWith("custom:")) onChange(next);
      }}>
      <option value="">Not sure</option>
      {items.map((i) => <option key={i.tag} value={i.tag}>{i.label}</option>)}
      {!known && <option value={`custom:${value}`}>{value.replaceAll("-", " ")}</option>}
      <option value="__other">Something else…</option>
    </select>
  );
}

// For files that don't match a requested document, or when the customer isn't sure what a file is.
function OtherUpload({ items, busy, onUpload }: { items: ReportItem[]; busy: boolean; onUpload: (f: File[], tag: string, note: string) => Promise<void> }) {
  const [tag, setTag] = useState("");
  const [note, setNote] = useState("");
  return (
    <div className="dc-upload">
      <p className="dc-muted" style={{ margin: 0 }}>Have another document, or not sure which one a file is? Add it here. The automatic check suggests where it belongs and your case team sorts it.</p>
      <div className="dc-upload-row">
        <select className="dc-select" value={tag} onChange={(e) => setTag(e.target.value)} aria-label="What is this file?">
          <option value="">I&apos;m not sure what it is</option>
          {items.map((i) => <option key={i.tag} value={i.tag}>{i.label}</option>)}
        </select>
        <input className="dc-input" placeholder="Note for the team (optional)" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" />
      </div>
      <DropZone compact busy={busy} label="Drop files here" onFiles={async (files) => { await onUpload(files, tag, note.trim()); setNote(""); }} />
    </div>
  );
}
