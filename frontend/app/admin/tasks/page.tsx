"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import "../services/services.css";
import "./tasks.css";

type Filters = { assignee: string; status: string; due: string; priority: string; q: string };
type Queue = { items: { id: string; title: string; status: "open" | "done" | "cancelled"; source: string; due_at: string | null; overdue: boolean;
  assignee: { id: string; name: string } | null; case: { ticket_number: string; status: string; status_label: string; priority: string; service_name: string; customer_name: string } }[];
  total: number; page: number; page_size: number; checked_at: string; summary: { open: number; overdue: number; due_today: number; unscheduled: number } };
const blank: Filters = { assignee: "me", status: "open", due: "all", priority: "all", q: "" };
const dueLabels: Record<string, string> = { all: "Any due date", overdue: "Overdue", today: "Due today", week: "Next 7 days", unscheduled: "No due date" };
const when = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
function endpoint(filters: Filters, page = 1) {
  return `/admin/task-queue?${new URLSearchParams({ ...filters, q: filters.q.trim(), page: String(page), page_size: "25" })}`;
}

export default function StaffTaskQueue() {
  const { user, onError } = useStaff();
  const [draft, setDraft] = useState<Filters>(blank), [applied, setApplied] = useState<Filters>(blank);
  const [data, setData] = useState<Queue | null>(null), [busy, setBusy] = useState(true), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const guard = useRef(false), feedback = useRef<HTMLParagraphElement>(null), failure = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true; guard.current = true; setBusy(true);
    adminFetch<Queue>(endpoint(blank), { cache: "no-store" })
      .then(result => { if (active) { setData(result); setApplied(blank); setError(""); } })
      .catch(error => { if (active) setError(onError(error)); })
      .finally(() => { if (active) { guard.current = false; setBusy(false); } });
    return () => { active = false; };
  }, [user.role, onError]);
  useEffect(() => { if (error) failure.current?.focus(); }, [error]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  const changed = JSON.stringify({ ...draft, q: draft.q.trim() }) !== JSON.stringify(applied);
  async function load(filters: Filters, page = 1) {
    if (guard.current) return;
    guard.current = true; setBusy(true); setError(""); setNotice("");
    const normalized = { ...filters, q: filters.q.trim() };
    try {
      const result = await adminFetch<Queue>(endpoint(normalized, page), { cache: "no-store" });
      setData(result); setApplied(normalized); setNotice(`Task queue loaded. Page ${result.page}; ${result.total} matching ${result.total === 1 ? "task" : "tasks"}.`);
    } catch (error) { setError(onError(error)); }
    finally { guard.current = false; setBusy(false); }
  }
  const scope = applied.assignee === "me" ? "Assigned to me" : applied.assignee === "all" ? "Everyone" : "Unassigned";
  const summary = [scope, applied.status === "all" ? "All task statuses" : `Status: ${applied.status}`, dueLabels[applied.due],
    applied.priority === "all" ? "Any case priority" : `Case priority: ${applied.priority}`, applied.q ? `Search: “${applied.q}”` : ""].filter(Boolean).join(" · ");
  return <MainContent className="service-availability task-queue-page">
    <header><div className="eyebrow">Staff workspace</div><h1>Task queue</h1><p>Find the next task across cases you can currently open. Open a case to review its checklist and update a task.</p></header>
    <section className="service-availability-card"><h2>Find case tasks</h2>
      <form aria-label="Task queue filters" onSubmit={event => { event.preventDefault(); load(draft); }}><fieldset disabled={busy}>
        <label>Search tasks<input maxLength={100} placeholder="Task title or case number" value={draft.q} onChange={event => setDraft({ ...draft, q: event.target.value })} /></label>
        <div className="task-queue-filters"><label>Task ownership<select value={draft.assignee} onChange={event => setDraft({ ...draft, assignee: event.target.value })}><option value="me">Assigned to me</option>{user.role === "admin" && <><option value="all">Everyone</option><option value="unassigned">Unassigned</option></>}</select></label>
          <label>Task status<select value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value })}><option value="open">Open</option><option value="done">Done</option><option value="cancelled">Cancelled</option><option value="all">All task statuses</option></select></label>
          <label>Task due date<select value={draft.due} onChange={event => setDraft({ ...draft, due: event.target.value })}>{Object.entries(dueLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label>Case priority<select value={draft.priority} onChange={event => setDraft({ ...draft, priority: event.target.value })}><option value="all">Any case priority</option>{["urgent", "high", "normal", "low"].map(value => <option key={value} value={value}>{value[0].toUpperCase()+value.slice(1)}</option>)}</select></label>
        </div><p>Dates use India Standard Time. Next 7 days starts now. Closed cases are excluded; case holds do not change task due dates.</p>
        <div className="task-queue-actions"><button className="btn">Apply task filters</button><button type="button" className="btn light" onClick={() => { setDraft(blank); load(blank); }}>Clear task filters</button><button type="button" className="btn light" onClick={() => load(applied, data?.page ?? 1)}>Refresh tasks</button></div>
      </fieldset></form>{changed && <p>Filter edits have not been applied. Refresh and paging keep your edits.</p>}
    </section>
    {busy && <p role="status">Loading tasks…</p>}
    {error && <div role="alert" tabIndex={-1} ref={failure}><p>Could not load tasks. {error}</p><p>{data ? "The last successful page is still shown and may be out of date. Your filter edits are kept." : "Use Refresh tasks to try again. Your filter edits are kept."}</p></div>}
    {notice && <p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {data && <>
      <section className="task-queue-counts" aria-label="Matching task counts">{[["Open tasks", data.summary.open], ["Overdue tasks", data.summary.overdue], ["Due today", data.summary.due_today], ["No due date", data.summary.unscheduled]].map(([label, value]) => <div className="service-availability-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}</section>
      <section className="service-availability-card" aria-label="Matching tasks"><h2>Matching tasks ({data.total})</h2><p className="task-queue-applied">Showing: {summary}</p><p>Checked <time dateTime={data.checked_at}>{when(data.checked_at)}</time> IST. Counts cover all matching tasks, across pages.</p>
        {!data.items.length ? <p>{data.total ? "No tasks on this page. Choose Previous tasks or refresh." : "No tasks match these filters in cases you can currently open."}</p> : <ol className="task-queue-list">{data.items.map(task => <li key={task.id}><article aria-label={task.title}>
          <div className="task-queue-entry-head"><h3>{task.title}</h3><span className={task.overdue ? "task-queue-overdue" : ""}>{task.overdue ? "Overdue" : task.status[0].toUpperCase()+task.status.slice(1)}</span></div>
          <p>{task.case.customer_name} · {task.case.service_name}</p><dl><div><dt>Assigned to</dt><dd>{task.assignee?.name ?? "Unassigned"}</dd></div><div><dt>Task due date</dt><dd>{task.due_at ? <time dateTime={task.due_at}>{when(task.due_at)} IST</time> : "No due date"}</dd></div><div><dt>Case priority</dt><dd>{task.case.priority}</dd></div><div><dt>Task source</dt><dd>{task.source === "playbook" ? "Routine checklist" : "Manual task"}</dd></div></dl>
          {task.case.status === "on_hold" && <p>Case on hold · task due date stays as recorded.</p>}
          <Link className="btn light" href={`/admin/tickets/${encodeURIComponent(task.case.ticket_number)}`}>Open case {task.case.ticket_number}</Link><p className="task-queue-case-status">Case status: {task.case.status_label}</p>
        </article></li>)}</ol>}
        <nav aria-label="Task queue pages"><button className="btn light" disabled={busy || data.page <= 1} onClick={() => load(applied, data.page-1)}>Previous tasks</button><span>Page {data.page}</span><button className="btn light" disabled={busy || data.page*data.page_size >= data.total} onClick={() => load(applied, data.page+1)}>Next tasks</button></nav>
      </section>
    </>}
    <p>Task assignment alone does not grant case access. A case owner or administrator can add staff to the case team when needed.</p>
  </MainContent>;
}
