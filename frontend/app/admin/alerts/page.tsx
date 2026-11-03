"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, formatDate, type CaseAlerts } from "../api";

export default function DeadlineAlerts() {
  const { onError } = useStaff();
  const [data, setData] = useState<CaseAlerts | null>(null), [include, setInclude] = useState(false), [page, setPage] = useState(1);
  const [error, setError] = useState(""), [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try { setData(await adminFetch<CaseAlerts>(`/admin/case-alerts?include_acknowledged=${include}&page=${page}`)); setError(""); }
    catch (e) { setError(onError(e)); }
  }, [include, page, onError]);
  useEffect(() => { load(); const timer = window.setInterval(load, 30000); return () => clearInterval(timer); }, [load]);
  async function acknowledge(id: string) {
    setBusy(id); setError("");
    try { await adminFetch(`/admin/case-alerts/${id}/acknowledge`, { method: "POST" }); await load(); window.dispatchEvent(new Event("hx-case-alerts")); }
    catch (e) { setError(onError(e)); } finally { setBusy(""); }
  }
  return <main className="deadline-alerts"><header className="admin-head"><div><div className="eyebrow">Keep cases moving</div><h1>Deadline alerts</h1><p>Missed case targets and first responses that need the team&apos;s attention.</p></div><button className="btn small light" onClick={load}>Refresh</button></header>
    {error && <p className="admin-error" role="alert">{error}</p>}
    <div className="deadline-alert-stats"><div className="admin-card"><small>Need acknowledgement</small><b>{data?.unacknowledged ?? "–"}</b></div><div className="admin-card"><small>Escalated</small><b>{data?.escalated ?? "–"}</b></div></div>
    <section className="admin-card"><label className="deadline-alert-toggle"><input type="checkbox" checked={include} onChange={e => { setInclude(e.target.checked); setPage(1); }} />Include acknowledged alerts</label><p>Acknowledging records that someone has seen the issue. The case remains overdue until its target is resolved. Escalation requires a new acknowledgement.</p></section>
    {!data ? <p role="status">Loading deadline alerts…</p> : !data.items.length ? <section className="admin-card"><h2>No {include ? "active" : "unacknowledged"} deadline alerts</h2><p>Held, closed and resolved cases are excluded. Refresh to see the latest alerts.</p></section> : <ul className="deadline-alert-list">{data.items.map(alert => <li key={alert.id} className={`admin-card deadline-alert-row${alert.escalated_at ? " escalated" : ""}`}><div><div className="deadline-alert-labels"><span className={alert.escalated_at ? "flag late" : "flag warn"}>{alert.escalated_at ? "Escalated" : "Overdue"}</span><Link href={`/admin/tickets/${alert.ticket_number}`}>{alert.ticket_number}</Link></div><h2>{alert.label}</h2><p>Target {formatDate(alert.target_at)} · Owner: {alert.owner?.name ?? "Unassigned"}</p>{alert.escalated_at && <p>Escalated {formatDate(alert.escalated_at)}</p>}{alert.acknowledged_at && <p className="deadline-alert-ack">Acknowledged by {alert.acknowledged_by?.name ?? "staff"} · {formatDate(alert.acknowledged_at)}</p>}</div><div className="deadline-alert-actions"><Link className="btn small light" href={`/admin/tickets/${alert.ticket_number}`}>Open case</Link>{!alert.acknowledged_at && <button className="btn small" disabled={!!busy} onClick={() => acknowledge(alert.id)}>{busy === alert.id ? "Saving…" : "Acknowledge"}</button>}</div></li>)}</ul>}
    {data && (data.total > data.page_size || page > 1) && <div className="admin-pager"><button className="btn small light" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button><span>Page {page} · {data.total} alerts</span><button className="btn small light" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Next</button></div>}
  </main>;
}
