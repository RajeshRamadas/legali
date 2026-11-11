"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import DescriptionEditor from "./DescriptionEditor";
import type { ManagedService as Service } from "./types";
import "./services.css";

type History = { items: { id: string; paused: boolean; revision: number; reason: string; actor: string; at: string }[]; total: number; page: number; page_size: number };
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

export default function ServiceAvailabilityPage() {
  const { user, onError } = useStaff();
  const [services, setServices] = useState<Service[]>([]), [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const feedback = useRef<HTMLParagraphElement>(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await adminFetch<{ items: Service[] }>("/admin/services"); setServices(data.items); setSelected(current => current || data.items.find(item => item.active)?.slug || ""); setVersion(value => value + 1); }
    catch (error) { setError(onError(error)); }
    finally { setLoading(false); }
  }, [onError]);
  useEffect(() => { if (user.role === "admin") load(); }, [load, user.role]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  if (user.role !== "admin") return <MainContent><h1>Administrator access required</h1><p>Only administrators can control service availability.</p></MainContent>;
  const service = services.find(item => item.slug === selected);
  return <MainContent className="service-availability"><header><div className="eyebrow">Pilot & capacity</div><h1>Service availability</h1><p>Control which services accept new requests. Pausing preserves existing cases, saved drafts and bookings.</p></header>
    <section className="service-availability-card"><h2>Choose a service</h2><p>{services.filter(item => item.active && !item.paused).length} accepting · {services.filter(item => item.active && item.paused).length} paused · {services.filter(item => !item.active).length} retired</p>
      <label>Service<select disabled={busy || loading} value={selected} onChange={event => { setSelected(event.target.value); setNotice(""); }}>{services.map(item => <option key={item.id} value={item.slug}>{item.name} · {!item.active ? "Retired" : item.paused ? "Paused" : "Accepting requests"}</option>)}</select></label>
      <button className="btn light" disabled={busy || loading} onClick={() => { setNotice(""); load(); }}>Reload catalogue (replaces draft)</button>
      {loading && <p role="status">Loading service availability…</p>}{error && <p role="alert">{error}</p>}{notice && <p ref={feedback} tabIndex={-1} role="status">{notice}</p>}
    </section>
    {service && !loading && <><AvailabilityEditor key={`${service.id}:${version}`} service={service} disabled={busy} onBusy={setBusy} onError={onError} onSaved={async result => { setServices(items => items.map(item => item.id === result.id ? { ...item, paused: result.paused, revision: result.revision, active: result.active } : item)); setNotice("Service availability saved. New requests now follow this setting."); }} />
      <DescriptionEditor key={`description:${service.id}:${version}`} service={service} disabled={busy} onBusy={setBusy} onError={onError} onSaved={result => setServices(items => items.map(item => item.id === result.id ? { ...item, description: result.description, description_revision: result.description_revision, description_customized: result.description_customized, default_description: result.default_description } : item))} /></>}
  </MainContent>;
}

function AvailabilityEditor({ service, disabled, onBusy, onError, onSaved }: { service: Service; disabled: boolean; onBusy: (value: boolean) => void; onError: (error: unknown) => string; onSaved: (service: Service) => Promise<void> }) {
  const [reason, setReason] = useState(""), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [history, setHistory] = useState<History | null>(null), [page, setPage] = useState(1), [historyError, setHistoryError] = useState("");
  const guard = useRef(false);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const loadHistory = useCallback(async () => { try { setHistory(await adminFetch<History>(`/admin/services/${encodeURIComponent(service.slug)}/history?page=${page}`)); setHistoryError(""); } catch (error) { setHistoryError(onError(error)); } }, [service.slug, page, onError]);
  useEffect(() => { loadHistory(); }, [loadHistory, historyRefresh]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (guard.current || disabled) return; guard.current = true; setBusy(true); onBusy(true); setError("");
    try { const result = await adminFetch<Service>(`/admin/services/${encodeURIComponent(service.slug)}`, { method: "PATCH", body: JSON.stringify({ revision: service.revision, paused: !service.paused, confirmed, reason: reason.trim() }) }); await onSaved(result); setReason(""); setConfirmed(false); setPage(1); setHistoryRefresh(value => value+1); }
    catch (error) { setError(`${onError(error)} Your draft is kept. Reload the catalogue to review the current state before trying again.`); }
    finally { guard.current = false; setBusy(false); onBusy(false); }
  }
  return <><section className="service-availability-card"><span className="service-availability-state">{!service.active ? "Retired" : service.paused ? "New requests paused" : "Accepting new requests"}</span><h2>{service.name}</h2><p>{service.description}</p>
    {!service.active ? <p>This service is retired. These controls cannot reactivate retired services.</p> : <form onSubmit={submit}><p>{service.paused ? "Resuming makes this service available for new requests again." : "Pausing removes this service from new-request choices and blocks new cases, including online consultations when that service is paused."} Existing work continues. This does not cancel a case, refund a payment or send a notification.</p>
      <fieldset disabled={busy || disabled}><label>Private operational reason<textarea required minLength={10} maxLength={1000} rows={3} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label className="service-availability-confirm"><input type="checkbox" required checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>I reviewed the effect on new requests. Existing cases and bookings will continue.</span></label>
      <button className="btn" disabled={!confirmed || reason.trim().length < 10}>{busy ? "Saving…" : service.paused ? "Resume new requests" : "Pause new requests"}</button></fieldset>
    </form>}{error && <p role="alert">{error}</p>}</section>
    <section className="service-availability-card"><h2>Private availability history</h2><p>Operational reasons are visible only to administrators.</p>{historyError && <p role="alert">{historyError} <button className="text-link" onClick={loadHistory}>Retry history</button></p>}
      {history ? !history.items.length ? <p>No availability changes recorded.</p> : <ol className="service-availability-history">{history.items.map(item => <li key={item.id}><strong>{item.paused ? "Paused" : "Resumed"} · revision {item.revision}</strong><p>{item.actor} · {date(item.at)}</p><p>{item.reason}</p></li>)}</ol> : <p role="status">Loading history…</p>}
      {history && (history.total > history.page_size || page > 1) && <nav aria-label="Availability history pages"><button className="btn light" disabled={page === 1 || busy} onClick={() => setPage(value => value-1)}>Previous changes</button><span>Page {page}</span><button className="btn light" disabled={page*history.page_size >= history.total || busy} onClick={() => setPage(value => value+1)}>Next changes</button></nav>}
    </section></>;
}
