"use client";
import { useEffect, useRef, useState } from "react";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import "../services/services.css";
import "./activity.css";

type Filters = { category: string; actor: string; from_date: string; to_date: string; record_id: string };
type Activity = { id: string; at: string; actor: string; category: string; activity: string; record_type: string; record_id: string | null };
type History = { items: Activity[]; next_cursor: string | null; checked_at: string; categories: { value: string; label: string }[] };
const blank: Filters = { category: "all", actor: "", from_date: "", to_date: "", record_id: "" };
const when = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
function endpoint(filters: Filters, cursor?: string) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value.trim()) query.set(key, value.trim());
  if (cursor) query.set("cursor", cursor);
  return `/admin/activity?${query}`;
}

export default function ActivityHistory() {
  const { user, onError } = useStaff();
  const [draft, setDraft] = useState<Filters>(blank), [applied, setApplied] = useState<Filters>(blank);
  const [pages, setPages] = useState<History[]>([]), [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(true), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const guard = useRef(false), feedback = useRef<HTMLParagraphElement>(null), failure = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (user.role !== "admin") return;
    let active = true; guard.current = true; setBusy(true);
    adminFetch<History>(endpoint(blank), { cache: "no-store" })
      .then(result => { if (active) { setPages([result]); setIndex(0); setApplied(blank); setError(""); } })
      .catch(error => { if (active) setError(onError(error)); })
      .finally(() => { if (active) { guard.current = false; setBusy(false); } });
    return () => { active = false; };
  }, [user.role, onError]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  useEffect(() => { if (error) failure.current?.focus(); }, [error]);
  if (user.role !== "admin") return <MainContent><h1>Administrator access required</h1><p>Only administrators can review recorded activity.</p></MainContent>;
  const current = pages[index], categories = pages[0]?.categories ?? [];
  const changed = JSON.stringify(draft) !== JSON.stringify(applied);
  const summary = [categories.find(item => item.value === applied.category)?.label ?? "All activity groups",
    applied.actor ? `Staff name contains “${applied.actor}”` : "All recorded actors",
    applied.from_date ? `From ${applied.from_date}` : "", applied.to_date ? `Through ${applied.to_date}` : "",
    applied.record_id ? `Record ${applied.record_id}` : ""].filter(Boolean).join(" · ");
  async function load(filters: Filters, older = false) {
    if (guard.current) return;
    guard.current = true; setBusy(true); setError(""); setNotice("");
    const normalized = Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, value.trim()])) as Filters;
    try {
      const result = await adminFetch<History>(endpoint(normalized, older ? current?.next_cursor ?? undefined : undefined), { cache: "no-store" });
      if (older) { setPages(values => [...values, result]); setIndex(index+1); }
      else { setPages([result]); setIndex(0); setApplied(normalized); }
      setNotice(`${older ? `Page ${index+2} loaded` : "Activity refreshed"}. ${result.items.length} recorded ${result.items.length === 1 ? "entry" : "entries"} shown.`);
    } catch (error) { setError(onError(error)); }
    finally { guard.current = false; setBusy(false); }
  }
  function navigate(next: number) {
    setIndex(next); setError(""); setNotice(`Page ${next+1} loaded. ${pages[next].items.length} recorded entries shown.`);
  }
  return <MainContent className="service-availability activity-page">
    <header><div className="eyebrow">Administrator workspace</div><h1>Activity history</h1><p>Review recorded changes across the platform. Open the relevant workspace for the full decision history and context.</p></header>
    <section className="service-availability-card"><h2>Find recorded activity</h2>
      <form aria-label="Activity filters" onSubmit={event => { event.preventDefault(); load(draft); }}>
        <fieldset disabled={busy}><div className="activity-filters">
          <label>Activity group<select value={draft.category} onChange={event => setDraft({ ...draft, category: event.target.value })}><option value="all">All activity groups</option>{categories.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>Staff name<input maxLength={100} value={draft.actor} onChange={event => setDraft({ ...draft, actor: event.target.value })} placeholder="Contains a staff member’s name" /></label>
          <label>From date<input type="date" value={draft.from_date} onChange={event => setDraft({ ...draft, from_date: event.target.value })} /></label>
          <label>To date<input type="date" min={draft.from_date || undefined} value={draft.to_date} onChange={event => setDraft({ ...draft, to_date: event.target.value })} /></label>
        </div><details><summary>Find a record by reference</summary><label>Record reference<input value={draft.record_id} onChange={event => setDraft({ ...draft, record_id: event.target.value })} maxLength={36} pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" placeholder="Paste a record reference from an entry" /></label></details>
          <p className="activity-hint">Dates use India Standard Time. Staff names are current display names. Unattributed entries can represent customers, automated work or former staff.</p>
          <div className="activity-actions"><button className="btn">Apply activity filters</button><button type="button" className="btn light" onClick={() => { setDraft(blank); load(blank); }}>Clear activity filters</button><button type="button" className="btn light" onClick={() => load(applied)}>Refresh activity</button></div>
        </fieldset>
      </form>{changed && <p>Filter edits have not been applied. Refresh keeps your filter edits.</p>}
    </section>
    {busy && <p role="status">Loading activity…</p>}
    {error && <div role="alert" tabIndex={-1} ref={failure}><p>Could not load activity. {error}</p><p>{current ? "The last successful page is still shown. Its entries may be out of date. Your filter edits are kept." : "Use Refresh activity to try again. Your filter edits are kept."}</p></div>}
    {notice && <p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {current && <section className="service-availability-card" aria-label="Recorded activity">
      <h2>Recorded activity</h2><p className="activity-applied">Showing: {summary}</p><p>Loaded <time dateTime={current.checked_at}>{when(current.checked_at)}</time> IST · Page {index+1}</p>
      {!current.items.length ? <p>No recorded activity matches these filters.</p> : <ol className="activity-entries">{current.items.map(item => <li key={item.id}>
        <article aria-label={item.activity}><div className="activity-entry-head"><h3>{item.activity}</h3><span>{categories.find(category => category.value === item.category)?.label ?? "Other recorded activity"}</span></div>
          <p>{item.actor} · <time dateTime={item.at}>{when(item.at)}</time> IST</p><details><summary>Entry references</summary><dl><div><dt>Entry reference</dt><dd>{item.id}</dd></div><div><dt>Record type</dt><dd>{item.record_type}</dd></div>{item.record_id && <div><dt>Record reference</dt><dd>{item.record_id}</dd></div>}</dl></details>
        </article>
      </li>)}</ol>}
      <nav aria-label="Activity history pages"><button className="btn light" disabled={busy || index === 0} onClick={() => navigate(index-1)}>Newer activity</button><span>Page {index+1}</span><button className="btn light" disabled={busy || (!pages[index+1] && !current.next_cursor)} onClick={() => pages[index+1] ? navigate(index+1) : load(applied, true)}>Older activity</button></nav>
    </section>}
    <p>Only retained audit entries appear here. This is a read-only index; it does not establish that every platform action was recorded. Private reasons, message content and authentication details stay in their existing restricted workflows.</p>
  </MainContent>;
}
