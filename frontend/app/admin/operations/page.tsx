"use client";
import MainContent from "../../ui/MainContent";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, type OperationsHealth } from "../api";

const labels = { notifications: "Notifications, case & support deadlines", blog_scan: "Case research scheduler" };
const states = { healthy: "Recent check succeeded", failed: "Last check failed", stale: "No recent completion", starting: "Check in progress", not_observed: "Not yet observed", disabled: "Not enabled" };
const channels = { email: "Email", sms: "SMS", whatsapp: "WhatsApp" };
function when(value: string | null) { return value ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not yet recorded"; }
function workerHint(worker: OperationsHealth["workers"][number]) {
  if (worker.state === "disabled") return "Enable the scheduler when case research is needed.";
  if (worker.error_code === "worker_not_configured") return "Configure the research provider before enabling this scheduler.";
  if (worker.error_code === "database_error") return "Check database connectivity and worker logs.";
  if (worker.state === "failed") return "Inspect worker logs before the next run.";
  if (worker.state === "not_observed" || worker.state === "stale") return "Check that an API or external worker is running. Long-running checks can also become stale.";
  if (worker.state === "starting") return "Waiting for this check to complete.";
  return "At least one worker in this group completed a recent check.";
}

export default function SystemHealth() {
  const { user, onError } = useStaff();
  const [data, setData] = useState<OperationsHealth | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const load = useCallback(async () => {
    if (user.role !== "admin" || inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try { setData(await adminFetch<OperationsHealth>("/admin/operations", { cache: "no-store" })); setError(""); }
    catch (e) { setError(onError(e)); }
    finally { inFlight.current = false; setBusy(false); }
  }, [user.role, onError]);
  useEffect(() => {
    if (user.role !== "admin") return;
    load();
    const refresh = () => { if (!document.hidden) load(); };
    const timer = window.setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", refresh);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, [load, user.role]);

  if (user.role !== "admin") return <MainContent className="operations-page"><h1>System health</h1><p>Administrator access is required to view operational checks.</p></MainContent>;
  const delayed = data?.channels.reduce((total, channel) => total + channel.delayed, 0) ?? 0;
  const failed = data?.channels.reduce((total, channel) => total + channel.failed_24h, 0) ?? 0;
  return <MainContent className="operations-page">
    <header className="operations-head"><div><div className="eyebrow">Administrator workspace</div><h1>System health</h1><p>Spot stalled work and delivery problems before they reach customers.</p></div><button className="btn small light" onClick={load} disabled={busy}>{busy ? "Checking…" : "Refresh checks"}</button></header>
    {error && <div className="admin-error" role="alert"><b>Could not refresh checks.</b><p>{error}</p>{data && <p>Showing the last successful snapshot below. Its checks may be out of date.</p>}</div>}
    {!data ? <p role="status">{error ? "Use Refresh checks to try again." : "Loading system checks…"}</p> : <>
      <section className={`operations-summary admin-card ${error || data.status === "attention" ? "attention" : "healthy"}`} aria-label="Overall health">
        <div><span className={`operations-state ${error || data.status === "attention" ? "warn" : "good"}`}>{error ? "Refresh needed" : data.status === "healthy" ? "Checks look healthy" : "Attention needed"}</span><h2>{error ? "The latest check is unavailable" : data.status === "healthy" ? "No issues in the observed checks" : "Review the checks below"}</h2><p>Last successful snapshot: <time dateTime={data.checked_at}>{when(data.checked_at)}</time></p></div>
        <div className="operations-database"><span className="operations-state good">Database ready</span><small>Schema matched the application at this check.</small></div>
      </section>
      <div className="operations-stats">
        {[ ["Delayed deliveries", delayed], ["Failed deliveries · 24h", failed], ["Files awaiting a scan", data.documents.pending], ["Deadline alerts", data.deadlines.unacknowledged] ].map(([label, value]) => <div className="admin-card" key={label}><span>{label}</span><b>{value}</b></div>)}
      </div>
      <section className="admin-card"><div className="operations-section-head"><div><h2>Background checks</h2><p>Shared observations from API and external workers.</p></div></div>
        <div className="operations-workers">{data.workers.map(worker => <article key={worker.name} className="operations-worker"><div className="operations-row"><h3>{labels[worker.name]}</h3><span className={`operations-state ${worker.state === "healthy" ? "good" : worker.state === "disabled" ? "neutral" : "warn"}`}>{states[worker.state]}</span></div><p>{workerHint(worker)}</p>
          <dl><div><dt>Last success</dt><dd>{when(worker.last_success_at)}</dd></div><div><dt>Last check</dt><dd>{when(worker.finished_at)}</dd></div><div><dt>Last duration</dt><dd>{worker.duration_ms === null ? "–" : `${(worker.duration_ms / 1000).toFixed(1)}s`}</dd></div></dl>
          <small>{worker.enabled_in_api ? "In-process checks enabled" : "In-process checks disabled; external checks can still report"} · Stale after {Math.ceil(worker.stale_after_seconds / 60)} min{worker.consecutive_failures > 0 ? ` · ${worker.consecutive_failures} consecutive failed checks` : ""}</small>
        </article>)}</div>
      </section>
      <section className="admin-card"><h2>Message delivery</h2><p>Delayed means due for more than {data.queue_warn_minutes} minutes. Future reminders are listed separately.</p>
        <div className="operations-channels">{data.channels.map(channel => <article key={channel.name} className="operations-channel"><div className="operations-row"><h3>{channels[channel.name]}</h3><span className={`operations-state ${channel.configured ? "good" : "neutral"}`}>{channel.configured ? "Configured" : "Setup required"}</span></div>
          <dl><div><dt>Due now</dt><dd>{channel.due}</dd></div><div><dt>Delayed</dt><dd>{channel.delayed}</dd></div><div><dt>Scheduled</dt><dd>{channel.scheduled}</dd></div><div><dt>Failed · 24h</dt><dd>{channel.failed_24h}</dd></div></dl>
          {channel.oldest_due_at && <small>Oldest due: {when(channel.oldest_due_at)}</small>}
          {!channel.configured && channel.due > 0 && <p className="operations-warning">Queued messages cannot send until this channel is configured.</p>}
        </article>)}</div><p className="operations-footnote">Configuration checks do not contact providers or prove delivery. Inspect delivery history before retrying failed messages; some outcomes need manual review.</p>
      </section>
      <div className="operations-bottom"><section className="admin-card"><h2>Document scanning</h2><p>{data.documents.delayed} pending longer than {data.queue_warn_minutes} min · {data.documents.failed} failed scans · {data.documents.infected} threats detected.</p><p>Quarantined files remain blocked from download and verification.</p><Link className="text-link" href="/admin?view=queue">Open case queue →</Link></section>
        <section className="admin-card"><h2>Work needing review</h2><p>{data.deadlines.unacknowledged} deadline alerts · {data.deadlines.escalated} escalated.</p><p>{data.research.failed_24h} failed case-research scans in the last 24 hours.</p>{data.support && <p>{data.support.overdue_requests} overdue support responses · {data.support.unacknowledged} support alerts need acknowledgement · {data.support.escalated} escalated.</p>}<div className="operations-links"><Link className="text-link" href="/admin/alerts">Deadline alerts →</Link><Link className="text-link" href="/admin/support/alerts">Support alerts →</Link><Link className="text-link" href="/admin/blog/cases">Case research →</Link></div></section></div>
      <p className="operations-footnote">Refreshes every 30 seconds while this page is visible. These application checks do not test external provider availability or backup recoverability; keep off-host backup monitoring and recovery drills running.</p>
    </>}
  </MainContent>;
}
