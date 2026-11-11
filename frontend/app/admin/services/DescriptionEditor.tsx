"use client";
import { useEffect, useRef, useState } from "react";
import { adminFetch } from "../api";
import type { ManagedService } from "./types";

type History = { items: { id: string; at: string; actor: string; previous_description: string; description: string; uses_standard: boolean; revision: number; reason: string }[]; total: number; page: number; page_size: number };
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

export default function DescriptionEditor({ service, disabled, onBusy, onSaved, onError }: {
  service: ManagedService; disabled: boolean; onBusy: (busy: boolean) => void;
  onSaved: (service: ManagedService) => void; onError: (error: unknown) => string;
}) {
  const [draft, setDraft] = useState(service.description), [standard, setStandard] = useState(false), [reason, setReason] = useState("");
  const [reviewing, setReviewing] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [open, setOpen] = useState(false), [history, setHistory] = useState<History | null>(null), [page, setPage] = useState(1), [refresh, setRefresh] = useState(0), [historyError, setHistoryError] = useState("");
  const feedback = useRef<HTMLParagraphElement>(null), preview = useRef<HTMLDivElement>(null), guard = useRef(false), errorHandler = useRef(onError);
  useEffect(() => { errorHandler.current = onError; }, [onError]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  useEffect(() => { if (reviewing) preview.current?.focus(); }, [reviewing]);
  useEffect(() => {
    if (!open) return;
    let active = true; setHistory(null); setHistoryError("");
    adminFetch<History>(`/admin/services/${encodeURIComponent(service.slug)}/description/history?page=${page}`)
      .then(result => { if (active) setHistory(result); }).catch(error => { if (active) setHistoryError(errorHandler.current(error)); });
    return () => { active = false; };
  }, [open, service.slug, page, refresh]);
  const changed = standard ? service.description_customized : draft.trim() !== service.description;
  async function publish(event: React.FormEvent) {
    event.preventDefault(); if (guard.current || disabled || !changed) return;
    if (!reviewing) { setReviewing(true); setError(""); setNotice(""); return; }
    guard.current = true; setBusy(true); onBusy(true); setError(""); setNotice("");
    try {
      const result = await adminFetch<ManagedService>(`/admin/services/${encodeURIComponent(service.slug)}/description`, {
        method: "PATCH", body: JSON.stringify({ revision: service.description_revision, description: standard ? null : draft.trim(), standard_description: standard ? service.default_description : null, reason: reason.trim(), confirmed: true }),
      });
      onSaved(result); setDraft(result.description); setStandard(false); setReason(""); setReviewing(false); setPage(1); setRefresh(value => value+1);
      setNotice("Description published. New catalogue loads use this copy. Service availability is unchanged.");
    } catch (error) { setError(`${onError(error)} Your description draft and private reason are kept.`); }
    finally { guard.current = false; setBusy(false); onBusy(false); }
  }
  return <section className="service-availability-card" aria-label="Service description editor">
    <h2>Public service description</h2><p>Publish plain text for the live services catalogue and callback selection. Names, service scope, intake questions and availability use their existing settings.</p>
    <p>Current copy: {service.description_customized ? "Administrator published" : "Standard catalogue"} · description revision {service.description_revision ?? 1}</p>
    {!service.active ? <p>Retired service descriptions cannot be published.</p> : <form onSubmit={publish}>
      <fieldset disabled={busy || disabled}>
        {!reviewing ? <>
          <label>Public description<textarea required minLength={10} maxLength={800} rows={5} value={draft} onChange={event => { setDraft(event.target.value); setStandard(false); setNotice(""); }} /></label>
          <button type="button" className="btn light" disabled={!service.description_customized} onClick={() => { setDraft(service.default_description); setStandard(true); setNotice(""); }}>Use standard description</button>
          <p>This prepares a draft. Review and publish it to change the public catalogue.</p>
          <label>Private publication reason<textarea required minLength={10} maxLength={1000} rows={3} value={reason} onChange={event => setReason(event.target.value)} /></label>
          <button className="btn" disabled={!changed || draft.trim().length < 10 || reason.trim().length < 10}>Review description</button>
        </> : <>
          <div ref={preview} tabIndex={-1} className="service-description-preview" aria-label="Public description preview"><h3>{service.name}</h3><p>{draft.trim()}</p></div>
          <p>Publishing replaces the public description immediately. The private reason stays in administrator history.</p>
          <button type="button" className="btn light" onClick={() => setReviewing(false)}>Back to editing</button>{" "}
          <button className="btn">{busy ? "Publishing…" : "Publish reviewed description"}</button>
        </>}
      </fieldset>
    </form>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status" ref={feedback} tabIndex={-1}>{notice}</p>}
    <details onToggle={event => setOpen(event.currentTarget.open)} className="service-description-history"><summary>Private description history</summary>
      {historyError ? <p role="alert">{historyError} <button type="button" className="text-link" onClick={() => setRefresh(value => value+1)}>Retry description history</button></p> : !history ? <p role="status">Loading description history…</p> : <>
        {!history.items.length ? <p>No description publications recorded.</p> : <ol className="service-availability-history">{history.items.map(item => <li key={item.id}><strong>Revision {item.revision} · {item.uses_standard ? "Standard description restored" : "Custom description published"}</strong><p>{item.actor} · {date(item.at)}</p><p>Previous: {item.previous_description}</p><p>Published: {item.description}</p><p>Private reason: {item.reason}</p></li>)}</ol>}
        {(history.total > history.page_size || page > 1) && <nav aria-label="Description history pages"><button type="button" className="btn light" disabled={page <= 1} onClick={() => setPage(value => value-1)}>Previous publications</button><span>Page {page}</span><button type="button" className="btn light" disabled={page*history.page_size >= history.total} onClick={() => setPage(value => value+1)}>Next publications</button></nav>}
      </>}
    </details>
  </section>;
}
