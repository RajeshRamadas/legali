"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch, type StaffUser } from "../api";
import "./time-off.css";

type Period = { id: string; starts_at: string; ends_at: string; reason: string; cancelled_at: string | null };
type Periods = { items: Period[]; name: string; timezone: string; total: number; page_size: number };

export default function TimeOffPage() {
  const { user, onError } = useStaff();
  const [staff, setStaff] = useState<StaffUser[]>([]), [target, setTarget] = useState("");
  const [rosterError, setRosterError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (user.role !== "admin") return;
    adminFetch<{ items: StaffUser[] }>("/admin/staff").then(result => { setStaff(result.items); setRosterError(""); }).catch(error => setRosterError(onError(error)));
  }, [user.role, onError]);
  return <MainContent className="time-off-page"><header><div className="eyebrow">Consultation availability</div><h1>Time off</h1><p>Block holidays, leave or other unavailable periods. Weekly consultation hours stay unchanged.</p></header>
    {user.role === "admin" && <section className="time-off-card"><label>Staff member<select disabled={busy} value={target} onChange={event => setTarget(event.target.value)}><option value="">My time off</option>{staff.filter(person => person.id !== user.id).map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>{rosterError && <p role="alert">Staff list could not load. {rosterError}</p>}</section>}
    <Editor key={target || user.id} target={target} onBusy={setBusy} />
  </MainContent>;
}

function Editor({ target, onBusy }: { target: string; onBusy: (value: boolean) => void }) {
  const { onError } = useStaff();
  const [data, setData] = useState<Periods | null>(null), [page, setPage] = useState(1), [version, setVersion] = useState(0);
  const [start, setStart] = useState(""), [end, setEnd] = useState(""), [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [cancel, setCancel] = useState("");
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [deviceZone, setDeviceZone] = useState("");
  const guard = useRef(false), pending = useRef<{ body: string; key: string } | null>(null);
  const feedback = useRef<HTMLParagraphElement>(null);
  const query = target ? `?user_id=${encodeURIComponent(target)}` : "";
  const load = useCallback(async () => {
    try { setData(await adminFetch<Periods>(`/admin/time-off${query}${query ? "&" : "?"}page=${page}`)); setError(""); }
    catch (error) { setError(onError(error)); }
  }, [query, page, onError]);
  useEffect(() => { load(); }, [load, version]);
  useEffect(() => { setDeviceZone(Intl.DateTimeFormat().resolvedOptions().timeZone); }, []);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (guard.current) return;
    guard.current = true; setBusy(true); onBusy(true); setError(""); setNotice("");
    try {
      const starts = new Date(start), ends = new Date(end);
      if (!Number.isFinite(starts.getTime()) || !Number.isFinite(ends.getTime()) || ends <= starts) throw new Error("Choose an end after the start.");
      const body = { starts_at: starts.toISOString(), ends_at: ends.toISOString(), reason: reason.trim(), confirmed };
      const serialized = JSON.stringify(body);
      if (pending.current?.body !== serialized) pending.current = { body: serialized, key: crypto.randomUUID() };
      const result = await adminFetch<Period>(`/admin/time-off${query}`, { method: "POST", body: JSON.stringify({ ...body, submission_key: pending.current.key }) });
      setStart(""); setEnd(""); setReason(""); setConfirmed(false); pending.current = null;
      setNotice(result.cancelled_at ? "This period was already cancelled. It has not been recreated." : "Time off saved. These times are no longer offered for booking."); setPage(1); setVersion(value => value + 1);
    } catch (error) { setError(`${onError(error)} Your entered details are kept.`); }
    finally { guard.current = false; setBusy(false); onBusy(false); }
  }
  async function cancelPeriod(id: string) {
    if (guard.current) return; guard.current = true; setBusy(true); onBusy(true); setError(""); setNotice("");
    try {
      await adminFetch(`/admin/time-off/${id}/cancel${query}`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
      setCancel(""); setNotice("Time off cancelled. Otherwise available times can be booked again."); setVersion(value => value + 1);
    } catch (error) { setError(onError(error)); }
    finally { guard.current = false; setBusy(false); onBusy(false); }
  }
  const date = (value: string) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: data?.timezone }).format(new Date(value));
  return <>
    <section className="time-off-card"><h2>{data ? `Add time off for ${data.name}` : "Add time off"}</h2>
      <p>Move or cancel overlapping scheduled meetings first. This does not cancel meetings, change payments or send messages.</p>
      <p className="time-off-muted">Enter dates and times in your device timezone{deviceZone ? ` (${deviceZone})` : ""}. Saved periods display in {data?.timezone || "the consultation timezone"}. Use a private operational reason; do not include medical details.</p>
      <form onSubmit={save}><fieldset disabled={busy || !data}><div className="time-off-fields">
        <label>Unavailable from<input type="datetime-local" required value={start} onChange={event => setStart(event.target.value)} /></label>
        <label>Available again<input type="datetime-local" required value={end} onChange={event => setEnd(event.target.value)} /></label>
      </div><label>Private reason<textarea required minLength={10} maxLength={500} rows={3} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label className="time-off-confirm"><input type="checkbox" required checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>I checked existing meetings. New bookings and scheduling changes must respect this period.</span></label>
      <button className="btn" disabled={!confirmed || reason.trim().length < 10}>{busy ? "Saving…" : "Save time off"}</button></fieldset></form>
      {error && <p role="alert">{error}</p>}{notice && <p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    </section>
    <section className="time-off-card"><h2>Private time-off history</h2><button className="btn light" disabled={busy} onClick={load}>Refresh time off</button>
      {!data ? <p role="status">Loading time off…</p> : !data.items.length ? <p>No time off recorded.</p> : <ul className="time-off-list">{data.items.map(period => <li key={period.id}>
        <h3>{date(period.starts_at)} – {date(period.ends_at)}</h3><p className="time-off-muted">{period.cancelled_at ? "Cancelled" : new Date(period.ends_at).getTime() <= Date.now() ? "Ended" : "Unavailable"}</p><p className="time-off-reason">{period.reason}</p>
        {!period.cancelled_at && new Date(period.ends_at).getTime() > Date.now() && (cancel === period.id ? <div className="time-off-cancel"><p>Cancel this period and allow otherwise available slots to be booked?</p><button className="btn" disabled={busy} onClick={() => cancelPeriod(period.id)}>Confirm cancellation</button><button className="btn light" disabled={busy} onClick={() => setCancel("")}>Keep time off</button></div> : <button className="btn light" disabled={busy} onClick={() => setCancel(period.id)}>Cancel time off</button>)}
      </li>)}</ul>}
      {data && (data.total > data.page_size || page > 1) && <nav aria-label="Time-off history pages"><button className="btn light" disabled={busy || page === 1} onClick={() => setPage(value => value-1)}>Previous periods</button><span>Page {page}</span><button className="btn light" disabled={busy || page*data.page_size >= data.total} onClick={() => setPage(value => value+1)}>Next periods</button></nav>}
    </section>
  </>;
}
