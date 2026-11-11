"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { SUPPORT_KIND_LABELS } from "@homexo/shared";
import { useStaff } from "../../AdminShell";
import { adminFetch, type SupportDeadlineAlert, type SupportDeadlineAlerts } from "../../api";
import MainContent from "../../../ui/MainContent";
import "../../../support/support.css";

const when = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });

export default function SupportAlerts() {
  const { user, onError } = useStaff();
  const [data, setData] = useState<SupportDeadlineAlerts | null>(null), [include, setInclude] = useState(false), [page, setPage] = useState(1);
  const [error, setError] = useState(""), [busy, setBusy] = useState(""), [notice, setNotice] = useState("");
  const sequence = useRef(0), feedback = useRef<HTMLParagraphElement>(null);
  const allowed = user.role === "admin";
  const load = useCallback(async () => {
    if (!allowed) return;
    const current = ++sequence.current;
    try {
      const result = await adminFetch<SupportDeadlineAlerts>(`/admin/support-requests/deadline-alerts?include_acknowledged=${include}&page=${page}`);
      if (current === sequence.current) { setData(result); setError(""); }
    } catch (error) { if (current === sequence.current) setError(onError(error)); }
  }, [allowed, include, page, onError]);
  useEffect(() => {
    load();
    const timer = window.setInterval(() => { if (!document.hidden) load(); }, 30000);
    const invalidatePending = () => { sequence.current++; };
    return () => { clearInterval(timer); invalidatePending(); };
  }, [load]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  async function acknowledge(alert: SupportDeadlineAlert) {
    if (busy) return;
    setBusy(alert.id); setError(""); setNotice("");
    try {
      await adminFetch(`/admin/support-requests/deadline-alerts/${alert.id}/acknowledge`, { method: "POST", body: JSON.stringify({ revision: alert.revision }) });
      setNotice("Support alert acknowledged. The response target remains overdue until the team responds.");
      window.dispatchEvent(new Event("hx-support-alerts"));
      await load();
    } catch (error) { setError(onError(error)); }
    finally { setBusy(""); }
  }
  if (!allowed) return <MainContent className="support-page"><h1>Support response alerts</h1><p>Administrator access is required to review support alerts.</p></MainContent>;
  return <MainContent className="support-page">
    <header><div className="eyebrow">Customer care</div><h1>Support response alerts</h1><p>Follow up on missed team-response targets. These are operational targets, not statutory grievance deadlines.</p><Link className="text-link" href="/admin/support">Open support queue →</Link></header>
    <div className="support-card support-row"><div><strong>{data?.unacknowledged ?? "–"}</strong> need acknowledgement · <strong>{data?.escalated ?? "–"}</strong> escalated</div><button className="btn small light" disabled={!!busy} onClick={load}>Refresh alerts</button></div>
    {error && <p className="support-error" role="alert">{error} Use Refresh alerts to load the latest state before retrying.</p>}
    {notice && <p ref={feedback} tabIndex={-1} className="support-card support-alert-feedback" role="status">{notice}</p>}
    <section className="support-card"><label className="support-alert-toggle"><input type="checkbox" checked={include} disabled={!!busy} onChange={event => { setInclude(event.target.checked); setPage(1); setData(null); }} />Include acknowledged alerts</label><p>Acknowledgement records that an administrator has seen this alert. Escalation requires a new acknowledgement. A reply to the customer clears the current response target.</p></section>
    {!data ? <p role="status">{error ? "Use Refresh alerts to try again." : "Loading support alerts…"}</p> : !data.items.length ? <section className="support-card"><h2>No {include ? "active" : "unacknowledged"} support alerts</h2><p>Monitoring records missed targets while its worker is running. The support queue still shows current overdue requests.</p></section> : <ul className="support-alert-list">{data.items.map(alert => <li key={alert.id} className="support-card">
      <div className="support-row"><strong>{alert.escalated_at ? "Escalated response target" : "Response target missed"}</strong><span>{SUPPORT_KIND_LABELS[alert.kind]}</span></div>
      <p className="support-reference">{alert.reference}</p><p>Target {when(alert.target_at)} · Owner: {alert.owner?.name || "Unassigned"}{alert.owner && !alert.owner.active ? " · unavailable" : ""}</p>
      {alert.escalated_at && <p>Escalated {when(alert.escalated_at)}</p>}
      {alert.acknowledged_at && <p>Acknowledged by {alert.acknowledged_by?.name || "Former administrator"} · {when(alert.acknowledged_at)}</p>}
      <div className="support-row"><Link className="btn small light" href={`/admin/support?request=${encodeURIComponent(alert.support_request_id)}`}>Open support request</Link>{!alert.acknowledged_at && <button className="btn small" disabled={!!busy} onClick={() => acknowledge(alert)}>{busy === alert.id ? "Acknowledging…" : "Acknowledge support alert"}</button>}</div>
    </li>)}</ul>}
    {data && (data.total > data.page_size || page > 1) && <div className="support-row"><button className="btn small light" disabled={page <= 1 || !!busy} onClick={() => { setPage(value => value-1); setData(null); }}>Previous alerts</button><span>Page {page} · {data.total} alerts</span><button className="btn small light" disabled={page*data.page_size >= data.total || !!busy} onClick={() => { setPage(value => value+1); setData(null); }}>Next alerts</button></div>}
  </MainContent>;
}
