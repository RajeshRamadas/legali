"use client";

import { useState } from "react";
import { dueIn, formatDate, formatDay, toLocalInput, type StaffUser, type TicketDetail } from "./api";

// Case management on the staff ticket page (backend/app/case_management.py and cases.py).
type Act = (path: string, method: "PATCH" | "POST" | "PUT" | "DELETE", body: object | null, done: string) => Promise<boolean>;

const rupees = (n: number | null) => (n == null ? "–" : `₹${n.toLocaleString("en-IN")}`);

export function CaseOverview({ ticket, act }: { ticket: TicketDetail; act: Act }) {
  const c = ticket.case;
  const closed = !!c.closed;
  const [moving, setMoving] = useState(false);
  const [due, setDue] = useState(c.deadlines.due_at ? toLocalInput(new Date(c.deadlines.due_at)) : "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const d = c.deadlines;

  async function moveDue(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    if (await act("", "PATCH", { due_at: new Date(due).toISOString(), due_reason: reason.trim() }, "Due date moved.")) { setMoving(false); setReason(""); }
    setBusy(false);
  }

  return (
    <section className="admin-card case-overview" aria-label="Case progress">
      <div className="card-head">
        <h2>Case progress</h2>
        <small className="muted">{c.milestones.filter((m) => m.done).length} of {c.milestones.length} milestones</small>
      </div>
      <ol className="case-steps">
        {c.milestones.map((m) => (
          <li key={m.key} className={m.done ? "done" : m.current ? "current" : undefined} aria-current={m.current ? "step" : undefined}>
            <span aria-hidden>{m.done ? "✓" : ""}</span>{m.label}
          </li>
        ))}
      </ol>
      <div className="case-facts">
        <div className={d.overdue ? "late" : undefined}>
          <small>Case due</small>
          <b>{d.due_at ? formatDay(d.due_at) : "–"}</b>
          {d.due_at && !closed && <em>{dueIn(d.due_at)}</em>}
          {!closed && !moving && <button className="admin-link" onClick={() => setMoving(true)}>Move</button>}
        </div>
        <div className={d.first_response_missed ? "late" : undefined}>
          <small>First response</small>
          {d.first_response_at
            ? <><b>{formatDate(d.first_response_at)}</b><em>{d.first_response_missed ? "missed target" : "on time"}</em></>
            : d.first_response_due_at ? <><b>Due {formatDate(d.first_response_due_at)}</b>{!closed && <em>{dueIn(d.first_response_due_at)}</em>}</> : <b>–</b>}
        </div>
        <div className={c.fee.status === "quoted" ? "warn" : undefined}>
          <small>Fee</small>
          <b>{c.fee.status === "none" ? "Not quoted" : c.fee.status === "paid" ? `${rupees(c.fee.paid)} paid` : c.fee.status === "waived" ? "Waived" : `${rupees(c.fee.quote)} due`}</b>
          {c.fee.reference && <em>Ref {c.fee.reference}</em>}
        </div>
        <div className={c.overdue_tasks ? "late" : undefined}>
          <small>Tasks</small>
          <b>{c.open_tasks} open</b>
          {c.overdue_tasks > 0 && <em>{c.overdue_tasks} overdue</em>}
        </div>
      </div>
      {moving && (
        <form className="meeting-inline case-inline" onSubmit={moveDue}>
          <input type="datetime-local" required value={due} onChange={(e) => setDue(e.target.value)} aria-label="New due date" />
          <input required maxLength={300} placeholder="Why is it moving? (team only)" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" />
          <button className="btn small" disabled={busy || !reason.trim()}>Save</button>
          <button type="button" className="admin-link" onClick={() => setMoving(false)}>Back</button>
        </form>
      )}
      {c.closed && (
        <p className="case-closed-note"><b>Closed{c.closed.at ? ` ${formatDate(c.closed.at)}` : ""}: {c.closed.outcome_label ?? "–"}.</b>{c.closed.summary ? ` ${c.closed.summary}` : ""}</p>
      )}
      {c.closure && (c.closure.blockers.length > 0 || c.closure.warnings.length > 0) && (
        <div className="case-closure">
          <small>Before this case can close</small>
          <ul>
            {c.closure.blockers.map((b) => <li key={b} className="blocker">{b}</li>)}
            {c.closure.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}

export function TasksCard({ ticket, staff, act }: { ticket: TicketDetail; staff: StaffUser[]; act: Act }) {
  const c = ticket.case;
  const closed = !!c.closed;
  const [open, setOpen] = useState(false);
  const [showDone, setShowDone] = useState(false);
  const tomorrow = new Date(Date.now() + 86400000);
  tomorrow.setHours(18, 0, 0, 0);
  const [form, setForm] = useState({ title: "", assignee: "", due: toLocalInput(tomorrow), notes: "" });
  const [busy, setBusy] = useState(false);
  // People who can take a task: the owner, the team and (for admins) anyone on staff.
  const people = new Map<string, string>();
  if (c.owner) people.set(c.owner.id, c.owner.name);
  c.team.forEach((m) => people.set(m.user.id, m.user.name));
  staff.forEach((s) => people.set(s.id, s.name));

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const body = { title: form.title.trim(), assignee_id: form.assignee || null, due_at: form.due ? new Date(form.due).toISOString() : null, notes: form.notes.trim() || null };
    if (await act("/tasks", "POST", body, "Task added.")) { setOpen(false); setForm({ ...form, title: "", notes: "" }); }
    setBusy(false);
  }

  const openTasks = c.tasks.filter((t) => t.status === "open");
  const finished = c.tasks.filter((t) => t.status !== "open");

  return (
    <section className="admin-card">
      <div className="card-head">
        <h2>Tasks</h2>
        {!closed && !open && <button className="btn small light" onClick={() => setOpen(true)}>Add task</button>}
      </div>
      {openTasks.length === 0 && !open && <p className="muted">No open tasks.{closed ? "" : " Routine tasks appear here as the case moves on."}</p>}
      <ul className="task-list">
        {openTasks.map((t) => (
          <li key={t.id} className={t.overdue ? "late" : undefined}>
            <button className="task-check" aria-label={`Mark "${t.title}" done`} disabled={closed} onClick={() => act(`/tasks/${t.id}`, "PATCH", { status: "done" }, "Task done.")} />
            <div>
              <b>{t.title}</b>
              <small>
                {t.assignee?.name ?? "Unassigned"}{t.due_at ? ` · due ${formatDate(t.due_at)} (${dueIn(t.due_at)})` : ""}{t.source === "playbook" ? " · routine" : ""}
              </small>
              {t.notes && <p>{t.notes}</p>}
            </div>
            {!closed && <button className="admin-link" onClick={() => act(`/tasks/${t.id}`, "PATCH", { status: "cancelled" }, "Task cancelled.")}>Cancel</button>}
          </li>
        ))}
      </ul>
      {open && (
        <form className="admin-form meeting-form" onSubmit={add}>
          <label>Task<input required minLength={2} maxLength={200} placeholder="e.g. Get the society NOC" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <div className="form-row">
            <label>Assign to
              <select value={form.assignee} onChange={(e) => setForm({ ...form, assignee: e.target.value })}>
                <option value="">{c.owner ? `${c.owner.name} (owner)` : "Me"}</option>
                {[...people].filter(([id]) => id !== c.owner?.id).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select>
            </label>
            <label>Due<input type="datetime-local" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} /></label>
          </div>
          <label>Notes (team only)<textarea rows={2} maxLength={2000} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
          <div className="form-actions">
            <button className="btn small" disabled={busy || form.title.trim().length < 2}>{busy ? "Adding…" : "Add task"}</button>
            <button type="button" className="admin-link" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      )}
      {finished.length > 0 && (
        <>
          <button className="admin-link task-toggle" onClick={() => setShowDone(!showDone)}>{showDone ? "Hide" : "Show"} {finished.length} finished</button>
          {showDone && (
            <ul className="task-list finished">
              {finished.map((t) => (
                <li key={t.id}>
                  <span className={`task-state ${t.status}`} aria-hidden>{t.status === "done" ? "✓" : "–"}</span>
                  <div><b>{t.title}</b><small>{t.status === "done" ? "Done" : "Cancelled"}{t.completed_at ? ` ${formatDate(t.completed_at)}` : ""}</small></div>
                  {!closed && <button className="admin-link" onClick={() => act(`/tasks/${t.id}`, "PATCH", { status: "open" }, "Task reopened.")}>Reopen</button>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

export function TeamCard({ ticket, staff, canManage, act }: { ticket: TicketDetail; staff: StaffUser[]; canManage: boolean; act: Act }) {
  const c = ticket.case;
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("associate");
  const [busy, setBusy] = useState(false);
  const taken = new Set([c.owner?.id, ...c.team.map((m) => m.user.id)]);
  const choices = staff.filter((s) => !taken.has(s.id));

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    if (await act("/members", "POST", { user_id: userId, role }, "Added to the case team.")) setUserId("");
    setBusy(false);
  }

  return (
    <section className="admin-card">
      <h2>Case team</h2>
      <ul className="case-team">
        <li><b>{c.owner?.name ?? "No owner yet"}</b><small>Owner</small></li>
        {c.team.map((m) => (
          <li key={m.user.id}>
            <b>{m.user.name}</b><small>{m.role_label}</small>
            {canManage && !c.closed && <button className="admin-link" onClick={() => act(`/members/${m.user.id}`, "DELETE", null, `${m.user.name} removed from the team.`)}>Remove</button>}
          </li>
        ))}
      </ul>
      {canManage && !c.closed && choices.length > 0 && (
        <form className="admin-form team-add" onSubmit={add}>
          <div className="form-row">
            <select aria-label="Staff member" required value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">Add someone…</option>
              {choices.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="associate">Associate</option>
              <option value="paralegal">Paralegal</option>
              <option value="reviewer">Reviewer</option>
            </select>
          </div>
          <button className="btn small light" disabled={busy || !userId}>Add to team</button>
          <small className="admin-footnote">Team members can open this case and take its tasks.</small>
        </form>
      )}
    </section>
  );
}

export function FeeCard({ ticket, act }: { ticket: TicketDetail; act: Act }) {
  const fee = ticket.case.fee;
  const closed = !!ticket.case.closed;
  const [mode, setMode] = useState<"" | "quote" | "paid" | "waive">("");
  const [amount, setAmount] = useState(fee.quote ? String(fee.quote) : "");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const body = { action: mode, amount: amount ? Number(amount) : null, reference: reference.trim() || null, note: note.trim() || null };
    const done = mode === "quote" ? "Fee quoted. The customer is told by SMS and email." : mode === "paid" ? "Payment recorded." : "Fee waived.";
    if (await act("/fee", "PUT", body, done)) { setMode(""); setReference(""); setNote(""); }
    setBusy(false);
  }

  return (
    <section className="admin-card">
      <h2>Case fee</h2>
      <dl className="admin-dl">
        <dt>Status</dt><dd>{fee.status_label}</dd>
        {fee.quote != null && <><dt>Quoted</dt><dd>{rupees(fee.quote)}</dd></>}
        {fee.paid != null && <><dt>Paid</dt><dd>{rupees(fee.paid)}{fee.paid_at ? ` on ${formatDay(fee.paid_at)}` : ""}</dd></>}
        {fee.reference && <><dt>Reference</dt><dd>{fee.reference}</dd></>}
        {fee.note && <><dt>Note</dt><dd>{fee.note}</dd></>}
      </dl>
      {!closed && mode === "" && fee.status !== "paid" && (
        <div className="staff-actions" style={{ marginTop: 12 }}>
          <button className="admin-link" onClick={() => setMode("quote")}>{fee.status === "quoted" ? "Change quote" : "Quote a fee"}</button>
          {fee.status === "quoted" && <button className="admin-link" onClick={() => setMode("paid")}>Record payment</button>}
          {fee.status !== "waived" && <button className="admin-link" onClick={() => setMode("waive")}>Waive</button>}
        </div>
      )}
      {mode && (
        <form className="admin-form meeting-form" onSubmit={submit}>
          {mode !== "waive" && <label>{mode === "paid" ? "Amount received (₹)" : "Fee (₹)"}<input type="number" min={1} required value={amount} onChange={(e) => setAmount(e.target.value)} /></label>}
          {mode === "paid" && <label>Reference<input required maxLength={200} placeholder="UPI ref, bank UTR or receipt no." value={reference} onChange={(e) => setReference(e.target.value)} /></label>}
          <label>{mode === "waive" ? "Why is it waived?" : "Note (team only, optional)"}<input required={mode === "waive"} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="form-actions">
            <button className="btn small" disabled={busy}>{mode === "quote" ? "Quote fee" : mode === "paid" ? "Record payment" : "Waive fee"}</button>
            <button type="button" className="admin-link" onClick={() => setMode("")}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
