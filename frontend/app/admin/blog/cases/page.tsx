"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { BlogAgentStatus, CaseLead, CaseLeadStatus } from "@homexo/shared";
import { useStaff } from "../../AdminShell";
import { adminFetch, timeAgo } from "../../api";
import "../blog-agent.css";

const FILTERS: { value: CaseLeadStatus | ""; label: string }[] = [
  { value: "new", label: "New" },
  { value: "", label: "All" },
  { value: "drafted", label: "Drafted" },
  { value: "failed", label: "Failed" },
  { value: "dismissed", label: "Dismissed" },
];

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const STATUS_LABEL: Record<CaseLeadStatus, string> = { new: "New", drafting: "Writing draft…", drafted: "Drafted", dismissed: "Dismissed", failed: "Draft failed" };

export default function CaseFinderPage() {
  const { user, onError } = useStaff();
  const [status, setStatus] = useState<BlogAgentStatus | null>(null);
  const [leads, setLeads] = useState<CaseLead[] | null>(null);
  const [filter, setFilter] = useState<CaseLeadStatus | "">("new");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        adminFetch<BlogAgentStatus>("/admin/blog-agent"),
        adminFetch<{ items: CaseLead[] }>(`/admin/blog-agent/leads${filter ? `?status=${filter}` : ""}`),
      ]);
      setStatus(s);
      setLeads(l.items);
    } catch (e) {
      setError(onError(e));
    }
  }, [filter, onError]);

  useEffect(() => {
    if (user.role === "admin") load();
  }, [user.role, load]);

  // While a scan or a draft is running, refresh every few seconds.
  const working = status?.running || leads?.some((l) => l.status === "drafting");
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [working, load]);

  if (user.role !== "admin") return <p className="admin-empty">Only admins can manage the blog.</p>;

  async function act(key: string, path: string, body: object | undefined, done: string) {
    setError("");
    setNotice("");
    setBusy(key);
    try {
      await adminFetch(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
      setNotice(done);
      await load();
    } catch (e) {
      setError(onError(e));
    } finally {
      setBusy("");
    }
  }

  function dismiss(lead: CaseLead) {
    const reason = window.prompt("Why dismiss this case? (optional)", "") ?? null;
    if (reason === null) return;
    act(lead.id, `/admin/blog-agent/leads/${lead.id}/dismiss`, { reason }, "Dismissed.");
  }

  const last = status?.runs[0];

  return (
    <>
      <Link className="admin-back" href="/admin/blog">← All posts</Link>
      <header className="admin-head">
        <div><div className="eyebrow">Blog</div><h1>Case finder</h1></div>
        <div className="blog-new">
          <button className="btn small" disabled={!status?.available || status.running || busy === "scan"}
            onClick={() => act("scan", "/admin/blog-agent/scan", undefined, "Searching for new cases. This takes a minute or two.")}>
            {status?.running ? "Searching…" : "Find new cases"}
          </button>
        </div>
      </header>
      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}

      {status && !status.available && (
        <p className="admin-error">The case finder is off: the server has no ANTHROPIC_API_KEY. See docs/blog-agent/implementation.md.</p>
      )}
      {status && (
        <section className="admin-card agent-summary">
          <p>
            Claude searches {status.domains.length} legal news and court sites for property rulings from the last {status.lookback_days} days,
            and writes drafts from the judgment. Every fact is checked against the source in code. <b>Nothing is published until you review it.</b>
          </p>
          <small className="admin-footnote">
            {status.scheduled ? `Runs every ${status.interval_hours} hours and drafts the best ${status.auto_drafts}.` : "Scheduled runs are off; use the button."}
            {last && <> Last search {timeAgo(last.started_at)}: {last.status === "failed" ? <span className="needs-reply">failed ({last.error})</span> : last.status === "running" ? "running" : `${last.added} new of ${last.found} found`}.</>}
          </small>
        </section>
      )}

      <div className="admin-toggle agent-filters">
        {FILTERS.map((f) => (
          <button key={f.label} type="button" className={filter === f.value ? "on" : undefined} onClick={() => setFilter(f.value)}>{f.label}</button>
        ))}
      </div>

      <div className="agent-leads">
        {leads?.map((lead) => (
          <article key={lead.id} className="admin-card agent-lead">
            <div className="agent-lead-head">
              <span className={`agent-score score-${lead.relevance}`} title="Relevance to home buyers, 1 to 5">{lead.relevance}</span>
              <div>
                <h2><a href={lead.url} target="_blank" rel="noreferrer">{lead.title} ↗</a></h2>
                <small className="muted">
                  {[lead.court, lead.case_number, lead.decision_date && `decided ${day(lead.decision_date)}`, lead.source_name].filter(Boolean).join(" · ")}
                </small>
              </div>
              <span className={`admin-pill lead-${lead.status}`}>{STATUS_LABEL[lead.status]}</span>
            </div>
            {lead.summary && <p>{lead.summary}</p>}
            {lead.why_it_matters && <p className="agent-why"><b>For buyers:</b> {lead.why_it_matters}</p>}
            {lead.note && <p className={lead.status === "failed" ? "admin-error" : "muted"}>{lead.note}</p>}
            <div className="agent-lead-actions">
              {lead.topics.map((t) => <span key={t} className="agent-topic">{t}</span>)}
              <span className="agent-spacer" />
              {lead.post_id && <Link className="btn small" href={`/admin/blog/${lead.post_id}`}>Review draft</Link>}
              {(lead.status === "new" || lead.status === "failed" || lead.status === "dismissed") && (
                <button className="btn small" disabled={!status?.available || busy === lead.id}
                  onClick={() => act(lead.id, `/admin/blog-agent/leads/${lead.id}/draft`, undefined, "Writing the draft. It appears here and in the blog list in a minute or two.")}>
                  {lead.status === "failed" ? "Try again" : "Write draft"}
                </button>
              )}
              {(lead.status === "new" || lead.status === "failed") && <button className="admin-link" disabled={busy === lead.id} onClick={() => dismiss(lead)}>Dismiss</button>}
            </div>
          </article>
        ))}
        {leads && !leads.length && <p className="admin-empty">{filter === "new" ? "No new cases. Use “Find new cases” to search." : "Nothing here."}</p>}
        {!leads && !error && <p className="admin-empty">Loading…</p>}
      </div>
    </>
  );
}
