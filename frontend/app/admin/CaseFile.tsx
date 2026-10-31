"use client";

import { useEffect, useRef, useState } from "react";
import { formatBytes, normalizeTag, type GovSource } from "@homexo/shared";
import { adminFetch, adminUpload, fileHref, formatDate, type ReportTemplate, type StaffReport, type StaffUser, type TicketDetail } from "./api";

type EditItem = { id?: string; tag: string; label: string; guidance: string; fetch_by: "customer" | "homexo"; source: string | null };
type Run = (action: () => Promise<TicketDetail>, done: string) => Promise<boolean>;

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx";

// The ticket's document repository and legal report: preliminary report with its tagged checklist, document review,
// government fetches, then the final report PDF to print, sign and upload back.
export default function CaseFile({ ticket, staff, onTicket, onError }: {
  ticket: TicketDetail;
  staff: StaffUser[];
  onTicket: (t: TicketDetail) => void;
  onError: (e: unknown) => string;
}) {
  const [template, setTemplate] = useState<ReportTemplate | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const base = `/admin/tickets/${encodeURIComponent(ticket.ticket_number)}`;
  const report = ticket.report;

  useEffect(() => {
    adminFetch<ReportTemplate>(`/admin/report-template?ticket=${encodeURIComponent(ticket.ticket_number)}`).then(setTemplate).catch(onError);
  }, [ticket.ticket_number, onError]);

  const run: Run = async (action, done) => {
    setError("");
    setNotice("");
    try {
      onTicket(await action());
      setNotice(done);
      return true;
    } catch (e) {
      setError(onError(e));
      return false;
    }
  };
  const call = (key: string, path: string, method: string, body: object | undefined, done: string) => {
    setBusy(key);
    return run(() => adminFetch<TicketDetail>(`${base}${path}`, { method, body: body ? JSON.stringify(body) : undefined }), done).finally(() => setBusy(""));
  };
  const upload = (key: string, path: string, file: File, fields: Record<string, string>, done: string) => {
    const form = new FormData();
    Object.entries(fields).forEach(([k, v]) => form.append(k, v));
    form.append("file", file);
    setBusy(key);
    return run(() => adminUpload<TicketDetail>(`${base}${path}`, form), done).finally(() => setBusy(""));
  };

  const tags = report?.items.map((i) => i.tag) ?? [];
  const docs = new Map(ticket.documents.map((d) => [d.id, d]));
  const editable = !!report && report.status !== "signed";

  return (
    <section className="admin-card casefile">
      <div className="casefile-head">
        <div>
          <h2>Documents and legal report</h2>
          <small>{report ? `${report.status_label} · ${report.progress.done} of ${report.progress.total} checklist items done` : `${ticket.documents.length} document${ticket.documents.length === 1 ? "" : "s"} shared · no report yet`}</small>
        </div>
        {report && <a className="btn small light" href={fileHref(report.preliminary_pdf_url)} target="_blank" rel="noreferrer">Preliminary PDF</a>}
      </div>
      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}
      {!report && ticket.document_request?.items.length ? <div className="casefile-empty"><h3>Automatic document request</h3><p>{ticket.document_request.prompt}</p><small>Intake: {ticket.document_request.intake.state} · {ticket.document_request.intake.transaction} · {ticket.document_request.intake.seller_capacity.replaceAll("_", " ")}</small><ul>{ticket.document_request.items.map(item => <li key={item.id}>{item.label} · {item.status_label} · {item.fetch_by === "homexo" ? "official-record task" : "customer upload"}</li>)}</ul></div> : null}

      {!report && !editing && (
        <div className="casefile-empty">
          <p>Write the preliminary report: what you understand so far and the documents you need. Each document gets a tag the customer files uploads under. Public records (EC, khata, RTC, tax receipts) are marked for Homexo to fetch from the government portals.</p>
          <button className="btn small" disabled={!template} onClick={() => setEditing(true)}>Start preliminary report</button>
        </div>
      )}

      {editing && template && (
        <ReportEditor ticket={ticket} template={template} staff={staff} busy={busy === "save"}
          onCancel={() => setEditing(false)}
          onSave={async (body) => { if (await call("save", "/report", "PUT", body, "Report saved.")) setEditing(false); }} />
      )}

      {report && !editing && (
        <>
          <div className="casefile-actions">
            {editable && <button className="btn small light" onClick={() => setEditing(true)}>Edit report and checklist</button>}
            {report.status === "draft" && (
              <button className="btn small" disabled={busy === "issue"} onClick={() => call("issue", "/report/issue", "POST", undefined, "Preliminary report sent. The customer sees the checklist when they open their documents.")}>Issue to customer</button>
            )}
            {report.status === "issued" && (
              <button className="btn small light" disabled={busy === "issue"} onClick={() => call("issue", "/report/issue", "POST", undefined, "The customer has been told about the updated checklist.")}>Notify customer of changes</button>
            )}
          </div>

          <ol className="casefile-items">
            {report.items.map((item) => (
              <li key={item.id} className={`casefile-item ${item.status}`}>
                <div className="casefile-item-top">
                  <b>{item.label}</b>
                  <span className="dc-tag">#{item.tag}</span>
                  <span className={`casefile-pill ${item.fetch_by === "homexo" && item.status === "pending" ? "fetching" : item.status}`}>{item.status_label}</span>
                  <span className="casefile-who">{item.fetch_by === "homexo" ? "Homexo fetches" : "Customer uploads"}</span>
                </div>
                {item.guidance && <small>{item.guidance}</small>}
                {item.note && <small className="casefile-note">Note: {item.note}</small>}
                {item.documents.length > 0 && (
                  <ul className="casefile-linked">
                    {item.documents.map((id) => docs.get(id)).filter(Boolean).map((d) => (
                      <li key={d!.id}><a href={fileHref(d!.download_url)} target="_blank" rel="noreferrer">{d!.filename}</a><small> · {d!.uploaded_by} · {formatDate(d!.at)}</small></li>
                    ))}
                  </ul>
                )}
                {item.fetch_by === "homexo" && item.source && !["verified", "waived"].includes(item.status) && (
                  <FetchHint source={item.source} property={ticket.property} />
                )}
                {editable && report.status !== "draft" && (
                  <ItemActions item={item} busy={busy === item.id}
                    onReview={(status, note) => call(item.id, `/report/items/${item.id}`, "PATCH", { status, note }, `#${item.tag}: ${status}.`)}
                    onUpload={(file) => upload(item.id, "/documents", file, { tag: item.tag, note: "" }, `${file.name} filed under #${item.tag}.`)} />
                )}
              </li>
            ))}
          </ol>

          {report.status !== "draft" && (
            <FinalReport report={report} staff={staff} busy={busy}
              onSave={(body) => call("final-save", "/report", "PUT", body, "Final report text saved.")}
              onGenerate={() => call("generate", "/report/final", "POST", undefined, "Final report generated. Print it, sign it and upload the signed scan.")}
              onSigned={(file) => upload("signed", "/report/signed", file, {}, "Signed report uploaded. The customer can download it now.")} />
          )}
        </>
      )}

      <DocumentList ticket={ticket} tags={tags} busy={busy}
        onTag={(id, tag) => call(id, `/documents/${id}`, "PATCH", { tag }, tag ? `Filed under #${tag}.` : "Tag removed.")}
        onDelete={(id) => call(id, `/documents/${id}`, "DELETE", undefined, "Document removed.")}
        onUpload={(file, tag, note) => upload("upload", "/documents", file, { tag, note }, `${file.name} uploaded.`)}
        onProperty={(body) => call("property", "/property", "PATCH", body, "Property details saved.")} />
    </section>
  );
}

function FetchHint({ source, property }: { source: GovSource; property: TicketDetail["property"] }) {
  const known = property ? [
    property.survey_number && `Survey no. ${property.survey_number}${property.subdivision_or_surnoc ? `/${property.subdivision_or_surnoc}` : ""}`,
    property.property_id_or_pid && `PID ${property.property_id_or_pid}`,
    property.village && `Village ${property.village}`, property.hobli && `Hobli ${property.hobli}`, property.taluk && `Taluk ${property.taluk}`, property.district && `District ${property.district}`,
  ].filter(Boolean).join(" · ") : "";
  return (
    <div className="casefile-fetch">
      <div>
        <b>Get it from {source.name}</b>
        <small>Search by: {source.search_by}.</small>
        <small>{known ? `On file: ${known}` : "Add the survey number / PID under Property identifiers below first."}</small>
      </div>
      <a className="btn small light" href={source.url} target="_blank" rel="noreferrer">Open portal ↗</a>
    </div>
  );
}

function ItemActions({ item, busy, onReview, onUpload }: {
  item: StaffReport["items"][number];
  busy: boolean;
  onReview: (status: string, note: string | null) => Promise<boolean>;
  onUpload: (file: File) => Promise<boolean>;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const done = item.status === "verified" || item.status === "waived";

  if (rejecting) {
    return (
      <form className="casefile-inline" onSubmit={async (e) => { e.preventDefault(); if (await onReview("rejected", note.trim())) { setRejecting(false); setNote(""); } }}>
        <input autoFocus required maxLength={1000} placeholder="What's wrong? The customer sees this." value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn small" disabled={busy || !note.trim()}>Ask again</button>
        <button type="button" className="admin-link" onClick={() => setRejecting(false)}>Cancel</button>
      </form>
    );
  }
  return (
    <div className="casefile-item-actions">
      {!done && <button className="btn small" disabled={busy || item.documents.length === 0} title={item.documents.length ? undefined : "No file under this tag yet"} onClick={() => onReview("verified", null)}>Verify</button>}
      {!done && item.documents.length > 0 && <button className="admin-link" disabled={busy} onClick={() => setRejecting(true)}>Reject</button>}
      {!done && <button className="admin-link" disabled={busy} onClick={() => { const why = window.prompt("Why isn't this needed? (optional, printed on the final report)"); if (why !== null) onReview("waived", why.trim() || null); }}>Waive</button>}
      {done && <button className="admin-link" disabled={busy} onClick={() => onReview("pending", null)}>Reopen</button>}
      {!done && (
        <>
          <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
          <button className="admin-link" disabled={busy} onClick={() => input.current?.click()}>{item.fetch_by === "homexo" ? "Upload fetched copy" : "Upload on their behalf"}</button>
        </>
      )}
    </div>
  );
}

function ReportEditor({ ticket, template, staff, busy, onSave, onCancel }: {
  ticket: TicketDetail;
  template: ReportTemplate;
  staff: StaffUser[];
  busy: boolean;
  onSave: (body: object) => void;
  onCancel: () => void;
}) {
  const report = ticket.report;
  const [sections, setSections] = useState<Record<string, string>>(() =>
    Object.fromEntries((report?.sections ?? template.preliminary).map((s) => [s.key, s.text])));
  const [items, setItems] = useState<EditItem[]>(() =>
    report ? report.items.map((i) => ({ id: i.id, tag: i.tag, label: i.label, guidance: i.guidance, fetch_by: i.fetch_by, source: i.source?.key ?? null })) : template.items.map((i) => ({ ...i })));
  const [lawyer, setLawyer] = useState(report?.lawyer?.id ?? "");
  const hints = Object.fromEntries(template.preliminary.map((s) => [s.key, s.hint]));
  const missing = template.items.filter((t) => !items.some((i) => i.tag === t.tag));
  const locked = (item: EditItem) => !!report?.items.find((i) => i.id === item.id && i.status === "verified");

  const update = (index: number, patch: Partial<EditItem>) => setItems(items.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  const move = (index: number, by: number) => {
    const next = [...items];
    const [item] = next.splice(index, 1);
    next.splice(Math.max(0, Math.min(next.length, index + by)), 0, item);
    setItems(next);
  };

  return (
    <form className="casefile-editor" onSubmit={(e) => {
      e.preventDefault();
      onSave({
        preliminary: sections,
        items: items.map(({ id, tag, label, guidance, fetch_by, source }) => ({ id, tag: id ? undefined : tag, label, guidance, fetch_by, source })),
        ...(lawyer ? { lawyer_id: lawyer } : {}),
      });
    }}>
      {(report?.sections ?? template.preliminary).map((s) => (
        <label key={s.key}>{s.heading}
          <textarea rows={s.key === "observations" ? 4 : 3} maxLength={8000} placeholder={hints[s.key]} value={sections[s.key] ?? ""} onChange={(e) => setSections({ ...sections, [s.key]: e.target.value })} />
        </label>
      ))}
      {staff.length > 1 && (
        <label>Advocate signing the report
          <select value={lawyer} onChange={(e) => setLawyer(e.target.value)}>
            {!report && <option value="">Me</option>}
            {staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
      )}

      <div className="casefile-editor-head"><b>Documents required</b><small>The tag is what the customer files uploads under. It can't change once the item is saved.</small></div>
      <ol className="casefile-edit-items">
        {items.map((item, index) => (
          <li key={item.id ?? `new-${index}`}>
            <div className="casefile-edit-row">
              <input aria-label="Document" required maxLength={160} placeholder="Document, e.g. Gift deed from father" value={item.label} onChange={(e) => update(index, { label: e.target.value })} />
              {item.id ? <span className="dc-tag">#{item.tag}</span> : (
                <input aria-label="Tag" className="casefile-tag-input" placeholder={normalizeTag(item.label).slice(0, 32) || "tag"} value={item.tag} onChange={(e) => update(index, { tag: normalizeTag(e.target.value) })} />
              )}
            </div>
            <div className="casefile-edit-row">
              <input aria-label="What to send" maxLength={500} placeholder="What exactly to send" value={item.guidance} onChange={(e) => update(index, { guidance: e.target.value })} />
              <select aria-label="Who provides it" value={item.fetch_by} onChange={(e) => update(index, { fetch_by: e.target.value as EditItem["fetch_by"] })}>
                <option value="customer">Customer uploads</option>
                <option value="homexo">Homexo fetches</option>
              </select>
              <select aria-label="Government portal" value={item.source ?? ""} onChange={(e) => update(index, { source: e.target.value || null })}>
                <option value="">No portal</option>
                {template.sources.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
              </select>
              <span className="casefile-move">
                <button type="button" aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
                <button type="button" aria-label="Move down" disabled={index === items.length - 1} onClick={() => move(index, 1)}>↓</button>
                <button type="button" aria-label="Remove" disabled={locked(item)} title={locked(item) ? "Verified items can't be removed" : undefined} onClick={() => setItems(items.filter((_, i) => i !== index))}>✕</button>
              </span>
            </div>
          </li>
        ))}
      </ol>
      <div className="casefile-actions">
        <button type="button" className="admin-link" onClick={() => setItems([...items, { tag: "", label: "", guidance: "", fetch_by: "customer", source: null }])}>+ Add a document</button>
        {missing.length > 0 && (
          <select aria-label="Add from the standard checklist" value="" onChange={(e) => { const t = missing.find((m) => m.tag === e.target.value); if (t) setItems([...items, { ...t }]); }}>
            <option value="">+ Add from the standard checklist…</option>
            {missing.map((m) => <option key={m.tag} value={m.tag}>{m.label}</option>)}
          </select>
        )}
      </div>
      <div className="casefile-actions">
        <button className="btn small" disabled={busy || items.length === 0}>{busy ? "Saving…" : report ? "Save report" : "Save draft"}</button>
        <button type="button" className="admin-link" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function FinalReport({ report, staff, busy, onSave, onGenerate, onSigned }: {
  report: StaffReport;
  staff: StaffUser[];
  busy: string;
  onSave: (body: object) => Promise<boolean>;
  onGenerate: () => void;
  onSigned: (file: File) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(report.final_sections.map((s) => [s.key, s.text])));
  const [reviewer, setReviewer] = useState(report.reviewer?.id ?? "");
  const input = useRef<HTMLInputElement>(null);
  const signed = report.status === "signed";
  const dirty = report.final_sections.some((s) => (values[s.key] ?? "") !== s.text) || reviewer !== (report.reviewer?.id ?? "");
  const left = report.items.filter((i) => i.status !== "verified" && i.status !== "waived").length;

  return (
    <div className="casefile-final">
      <div className="casefile-editor-head">
        <b>Final report</b>
        <small>{signed ? `Signed copy uploaded ${report.signed_at ? formatDate(report.signed_at) : ""}.` : left ? `${left} checklist item${left === 1 ? "" : "s"} still to verify or waive before the PDF can be made.` : "Checklist complete. Write the findings, generate the PDF, print it and sign it."}</small>
      </div>
      {!signed && (
        <form className="casefile-editor" onSubmit={async (e) => { e.preventDefault(); await onSave({ final: values, reviewer_id: reviewer || null }); }}>
          {report.final_sections.map((s) => (
            <label key={s.key}>{s.heading}{s.key === "opinion" ? " (required)" : ""}
              <textarea rows={s.key === "title_flow" ? 4 : 3} maxLength={8000} placeholder={s.hint} value={values[s.key] ?? ""} onChange={(e) => setValues({ ...values, [s.key]: e.target.value })} />
            </label>
          ))}
          <label>Second signature (reviewing advocate)
            <select value={reviewer} onChange={(e) => setReviewer(e.target.value)}>
              <option value="">Leave blank to fill in by hand</option>
              {staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <div className="casefile-actions">
            <button className="btn small light" disabled={!dirty || busy === "final-save"}>{busy === "final-save" ? "Saving…" : "Save text"}</button>
            <button type="button" className="btn small" disabled={dirty || !report.checklist_complete || busy === "generate"} title={dirty ? "Save the text first" : undefined} onClick={onGenerate}>
              {busy === "generate" ? "Generating…" : report.final_pdf_url ? "Generate again" : "Generate final report PDF"}
            </button>
          </div>
        </form>
      )}
      <div className="casefile-actions">
        {report.final_pdf_url && <a className="btn small light" href={fileHref(report.final_pdf_url)} target="_blank" rel="noreferrer">Open final PDF to print</a>}
        {report.status === "final_generated" && (
          <>
            <input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onSigned(f); e.target.value = ""; }} />
            <button className="btn small gold" disabled={busy === "signed"} onClick={() => input.current?.click()}>{busy === "signed" ? "Uploading…" : "Upload signed scan"}</button>
          </>
        )}
        {report.signed_report_url && <a className="btn small gold" href={fileHref(report.signed_report_url)} target="_blank" rel="noreferrer">Signed report</a>}
      </div>
    </div>
  );
}

const PROPERTY_FIELDS: [keyof NonNullable<TicketDetail["property"]>, string][] = [
  ["survey_number", "Survey no."], ["subdivision_or_surnoc", "Hissa / surnoc"], ["property_id_or_pid", "PID / e-Khata no."],
  ["village", "Village"], ["hobli", "Hobli"], ["taluk", "Taluk"], ["district", "District"], ["address_line", "Address"],
];

function DocumentList({ ticket, tags, busy, onTag, onDelete, onUpload, onProperty }: {
  ticket: TicketDetail;
  tags: string[];
  busy: string;
  onTag: (id: string, tag: string) => void;
  onDelete: (id: string) => void;
  onUpload: (file: File, tag: string, note: string) => Promise<boolean>;
  onProperty: (body: object) => Promise<boolean>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [tag, setTag] = useState("");
  const [note, setNote] = useState("");
  const [prop, setProp] = useState<Record<string, string>>(() => Object.fromEntries(PROPERTY_FIELDS.map(([k]) => [k, (ticket.property?.[k] as string) ?? ""])));
  const input = useRef<HTMLInputElement>(null);
  const final = ticket.report && ["final_generated", "signed"].includes(ticket.report.status);

  return (
    <>
      <details className="casefile-section">
        <summary>All documents ({ticket.documents.length})</summary>
        <form className="casefile-inline" onSubmit={async (e) => {
          e.preventDefault();
          if (file && await onUpload(file, tag, note.trim())) { setFile(null); setNote(""); if (input.current) input.current.value = ""; }
        }}>
          <input ref={input} type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Tag">
            <option value="">No tag</option>
            {tags.map((t) => <option key={t} value={t}>#{t}</option>)}
          </select>
          <input placeholder="Note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn small" disabled={!file || busy === "upload"}>{busy === "upload" ? "Uploading…" : "Upload"}</button>
        </form>
        {ticket.documents.length === 0 ? <p className="muted">The customer hasn't shared anything yet.</p> : (
          <ul className="casefile-docs">
            {ticket.documents.map((d) => (
              <li key={d.id}>
                <div>
                  <a href={fileHref(d.download_url)} target="_blank" rel="noreferrer"><b>{d.filename}</b></a>
                  <small>{formatBytes(d.size)} · {d.uploaded_by} · {formatDate(d.at)}{d.note ? ` · ${d.note}` : ""}</small>
                </div>
                <select value={d.tag ?? ""} disabled={busy === d.id} aria-label="Tag" onChange={(e) => onTag(d.id, e.target.value)}>
                  <option value="">Untagged</option>
                  {tags.map((t) => <option key={t} value={t}>#{t}</option>)}
                  {d.tag && !tags.includes(d.tag) && <option value={d.tag}>#{d.tag}</option>}
                </select>
                {!final && <button className="admin-link" disabled={busy === d.id} onClick={() => window.confirm(`Remove ${d.filename}?`) && onDelete(d.id)}>Remove</button>}
              </li>
            ))}
          </ul>
        )}
      </details>
      <details className="casefile-section">
        <summary>Property identifiers for government portals</summary>
        <form className="casefile-prop" onSubmit={(e) => { e.preventDefault(); onProperty(prop); }}>
          {PROPERTY_FIELDS.map(([key, label]) => (
            <label key={key}>{label}<input maxLength={key === "address_line" ? 300 : 100} value={prop[key]} onChange={(e) => setProp({ ...prop, [key]: e.target.value })} /></label>
          ))}
          <button className="btn small light" disabled={busy === "property"}>Save</button>
        </form>
      </details>
    </>
  );
}
