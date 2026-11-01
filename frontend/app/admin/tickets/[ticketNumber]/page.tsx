"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PROPERTY_TYPES } from "@homexo/shared";
import { useStaff } from "../../AdminShell";
import CaseFile from "../../CaseFile";
import { CaseOverview, FeeCard, TasksCard, TeamCard } from "../../CasePanel";
import VerificationPanel from "../../VerificationPanel";
import VerificationOverview from "../../VerificationOverview";
import { adminFetch, formatDate, joinable, toLocalInput, type Meeting, type Meta, type StaffUser, type TicketDetail } from "../../api";

const EVENT_TEXT: Record<string, (e: TicketDetail["events"][number], labels: Record<string, string>) => string> = {
  created: () => "Request raised",
  status_changed: (e, labels) => `Status: ${labels[e.old?.status ?? ""] ?? e.old?.status} → ${labels[e.new?.status ?? ""] ?? e.new?.status}`,
  priority_changed: (e) => `Priority: ${e.old?.priority} → ${e.new?.priority}`,
  assigned: (e) => (e.old?.agent ? `Reassigned from ${e.old.agent} to ${e.new?.agent}` : `Assigned to ${e.new?.agent}`),
  unassigned: (e) => `Unassigned${e.old?.agent ? ` from ${e.old.agent}` : ""}`,
  message_sent: () => "Message sent to customer",
  note_added: () => "Internal note added",
  customer_replied: () => "Customer replied",
  meeting_scheduled: (e) => `Meeting booked for ${e.new?.when} with ${e.new?.lawyer}`,
  meeting_rescheduled: (e) => `Meeting moved from ${e.old?.when} to ${e.new?.when}`,
  meeting_cancelled: (e) => `Meeting on ${e.old?.when} cancelled`,
  meeting_completed: (e) => `Meeting on ${e.old?.when} marked done`,
  document_uploaded: (e) => `${e.new?.by === "customer" ? "Customer" : "Staff"} uploaded ${e.new?.filename}${e.new?.tag ? ` under #${e.new.tag}` : ""}`,
  document_removed: (e) => `${e.old?.by === "customer" ? "Customer" : "Staff"} removed ${e.old?.filename}`,
  report_started: () => "Preliminary report started",
  report_issued: () => "Preliminary report issued to the customer",
  report_updated: () => "Customer told about checklist changes",
  report_item_reviewed: (e) => `#${e.new?.tag}: ${e.old?.status} → ${e.new?.status}`,
  final_report_generated: () => "Final report PDF generated for signature",
  report_signed: () => "Signed final report uploaded",
  intake_updated: () => "Property intake and document request updated",
  agent_report_drafted: () => "Evidence-based report drafted for advocate review",
  payment_received: (e) => `Fee of ₹${e.new?.amount} paid online${e.new?.method ? ` by ${String(e.new.method).toUpperCase()}` : ""}${e.new?.reference ? ` (${e.new.reference})` : ""}`,
  payment_failed: (e) => `Online payment of ₹${e.new?.amount} failed`,
  payment_refund_due: (e) => `Refund of ₹${e.new?.amount} due: refund it in the Razorpay dashboard${e.new?.reference ? ` (payment ${e.new.reference})` : ""}`,
  payment_refunded: (e) => `₹${e.new?.amount} refunded`,
  case_closed: (e) => `Case closed: ${String(e.new?.outcome ?? "").replace(/_/g, " ")}${e.new?.override ? " (closure checks overridden)" : ""}${Number(e.new?.cancelled_tasks) ? `, ${e.new?.cancelled_tasks} open tasks cancelled` : ""}`,
  due_date_changed: (e) => `Due date moved${e.old?.due_at ? ` from ${formatDate(e.old.due_at)}` : ""} to ${formatDate(e.new?.due_at ?? "")}`,
  task_added: (e) => `Task added for ${e.new?.assignee}: ${e.new?.title}`,
  task_done: (e) => `Task done: ${e.new?.title}`,
  task_cancelled: (e) => `Task cancelled: ${e.new?.title}`,
  task_reopened: (e) => `Task reopened: ${e.new?.title}`,
  member_added: (e) => `${e.new?.name} joined the case team as ${e.new?.role}`,
  member_removed: (e) => `${e.old?.name} left the case team`,
  fee_quoted: (e) => `Fee of ₹${Number(e.new?.amount).toLocaleString("en-IN")} quoted`,
  fee_paid: (e) => `Fee of ₹${Number(e.new?.amount).toLocaleString("en-IN")} received (${e.new?.reference})`,
  fee_waived: () => "Fee waived",
  fee_cleared: () => "Fee quote withdrawn",
};

const TEMPLATE_TEXT: Record<string, string> = {
  meeting_scheduled: "meeting invite",
  meeting_rescheduled: "meeting moved",
  meeting_reminder: "meeting reminder",
  meeting_cancelled: "meeting cancelled",
  report_issued: "preliminary report",
  document_rejected: "document asked again",
  report_signed: "signed report ready",
  urgent_task: "urgent task alert",
};

export default function TicketPage() {
  const params = useParams<{ ticketNumber: string }>();
  const { user, onError } = useStaff();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    adminFetch<TicketDetail>(`/admin/tickets/${encodeURIComponent(params.ticketNumber)}`).then(setTicket).catch((e) => setError(onError(e)));
  }, [params.ticketNumber, onError]);

  useEffect(() => {
    load();
    adminFetch<Meta>("/admin/meta").then(setMeta).catch(onError);
    if (user.role === "admin") adminFetch<{ items: StaffUser[] }>("/admin/staff").then((r) => setStaff(r.items.filter((s) => s.account_status === "active"))).catch(onError);
  }, [load, user.role, onError]);

  // Every action returns the updated ticket, so the page re-renders from the server's answer.
  async function act(path: string, method: "PATCH" | "POST" | "PUT" | "DELETE", body: object | null, done: string) {
    setError("");
    setNotice("");
    try {
      setTicket(await adminFetch<TicketDetail>(`/admin/tickets/${encodeURIComponent(params.ticketNumber)}${path}`, { method, ...(body ? { body: JSON.stringify(body) } : {}) }));
      setNotice(done);
      return true;
    } catch (e) {
      setError(onError(e));
      return false;
    }
  }

  async function changeMeeting(meeting: Meeting, body: object, done: string) {
    setError("");
    setNotice("");
    try {
      await adminFetch<Meeting>(`/admin/meetings/${meeting.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setNotice(done);
      load();
      return true;
    } catch (e) {
      setError(onError(e));
      return false;
    }
  }

  if (!ticket) {
    return (
      <>
        <Link className="admin-back" href="/admin">← Ticket queue</Link>
        {error ? <p className="admin-error" role="alert">{error}</p> : <p className="admin-empty">Loading ticket…</p>}
      </>
    );
  }

  const labels = Object.fromEntries((meta?.statuses ?? []).map((s) => [s.value, s.label]));
  const propertyLabel = PROPERTY_TYPES.find((p) => p.value === ticket.property?.type)?.label ?? ticket.property?.type;

  return (
    <>
      <Link className="admin-back" href="/admin">← Ticket queue</Link>
      <header className="admin-head ticket-head">
        <div>
          <div className="eyebrow">{ticket.ticket_number} · raised {formatDate(ticket.created_at)} via {ticket.source}</div>
          <h1>{ticket.service_name}</h1>
          <div className="ticket-badges">
            <span className={`admin-pill pill-${ticket.status}`}>{ticket.status_label}</span>
            <span className={`priority priority-${ticket.priority}`}>{ticket.priority} priority</span>
            {ticket.package && <span className="admin-tag">{ticket.package}</span>}
            {ticket.needs_reply && <span className="needs-reply">● Customer replied</span>}
          </div>
        </div>
      </header>

      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}

      <div className="ticket-layout">
        <div className="ticket-main">
          <CaseOverview ticket={ticket} act={act} />
          <TasksCard ticket={ticket} staff={user.role === "admin" ? staff : [user]} act={act} />
          <Conversation ticket={ticket} onSend={(message, visibility) => act("/messages", "POST", { message, visibility }, visibility === "internal" ? "Internal note added." : "Message sent to the customer.")} />

          <VerificationOverview ticket={ticket} />
          <VerificationPanel ticket={ticket} onTicket={setTicket} />
          <CaseFile ticket={ticket} staff={user.role === "admin" ? staff : [user]} onTicket={setTicket} onError={onError} />

          <MeetingsCard
            ticket={ticket} meta={meta} staff={user.role === "admin" ? staff : [user]} defaultLawyer={user.role === "admin" ? ticket.assignee?.id ?? user.id : user.id}
            onSchedule={(body) => act("/meetings", "POST", body, "Meeting booked. The customer and lawyer get the link on WhatsApp, with reminders before it starts.")}
            onChange={changeMeeting}
          />
          {ticket.chat_transcript.length > 0 && (
            <details className="admin-card chat-transcript">
              <summary><h2>Chat with the assistant</h2><small>{ticket.chat_transcript.filter((m) => m.from === "customer").length} customer messages · {formatDate(ticket.chat_transcript[0].at)}</small></summary>
              <ol>
                {ticket.chat_transcript.map((m, i) => (
                  <li key={i} className={`from-${m.from}`}>
                    <small>{m.from === "customer" ? "Customer" : m.from === "assistant" ? "Assistant" : "System"} · {formatDate(m.at)}</small>
                    <p>{m.message}</p>
                  </li>
                ))}
              </ol>
            </details>
          )}

          <section className="admin-card">
            <h2>Activity</h2>
            <ol className="admin-timeline">
              {[...ticket.events].reverse().map((e, i) => (
                <li key={i}>
                  <b>{(EVENT_TEXT[e.type] ?? (() => e.type))(e, labels)}</b>
                  {e.note && <p>“{e.note}”</p>}
                  <small>{e.actor ? e.actor.name : ["customer_replied", "created", "document_uploaded", "document_removed"].includes(e.type) ? "Customer" : "System"} · {formatDate(e.at)}</small>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="ticket-side">
          <StatusCard ticket={ticket} meta={meta} isAdmin={user.role === "admin"} onSave={(body, done) => act("", "PATCH", body, done)} />
          {user.role === "admin" && <AssignCard ticket={ticket} staff={staff} onAssign={(agent_id, note) => act("/assignment", "POST", { agent_id, note: note || null }, agent_id ? "Ticket assigned." : "Ticket unassigned.")} />}
          {user.role !== "admin" && <section className="admin-card"><h2>Assigned to</h2><p>{ticket.assignee?.name ?? "Unassigned"}</p></section>}
          <TeamCard ticket={ticket} staff={staff} canManage={user.role === "admin" || ticket.assignee?.id === user.id} act={act} />
          <FeeCard ticket={ticket} act={act} />

          <section className="admin-card">
            <h2>Customer</h2>
            <dl className="admin-dl">
              <dt>Name</dt><dd>{ticket.customer_name}</dd>
              <dt>Phone</dt><dd>{ticket.customer.phone ? <a href={`tel:${ticket.customer.phone.replace(/[^\d+]/g, "")}`}>{ticket.customer.phone}</a> : "–"}</dd>
              <dt>Email</dt><dd>{ticket.customer.email ? <a href={`mailto:${ticket.customer.email}`}>{ticket.customer.email}</a> : "–"}</dd>
            </dl>
          </section>

          <section className="admin-card">
            <h2>Request</h2>
            <dl className="admin-dl">
              <dt>Service</dt><dd>{ticket.service_name}</dd>
              <dt>Package</dt><dd>{ticket.package ?? "–"}</dd>
              <dt>Property</dt><dd>{propertyLabel ?? "–"}</dd>
              <dt>Location</dt><dd>{ticket.location ?? "–"}</dd>
            </dl>
            {ticket.description && <p className="admin-description">{ticket.description}</p>}
          </section>

          <section className="admin-card">
            <h2>Notifications</h2>
            {ticket.notifications.length === 0 ? <p className="muted">None yet.</p> : (
              <ul className="admin-notifications">
                {[...ticket.notifications].reverse().map((n, i) => (
                  <li key={i} className={n.status === "cancelled" ? "muted" : undefined}>
                    <b>{TEMPLATE_TEXT[n.template] ?? n.template.replace(/_/g, " ")}{n.to === "staff" && " (lawyer)"}</b>
                    <small>
                      {n.channel === "whatsapp" ? "WhatsApp" : n.channel.toUpperCase()} · {n.status === "queued" && n.send_after && new Date(n.send_after) > new Date() ? `due ${formatDate(n.send_after)}` : n.status}
                      {n.error && n.error !== "superseded" && ` (${n.error})`} · {formatDate(n.at)}
                    </small>
                  </li>
                ))}
              </ul>
            )}
            <p className="admin-footnote">
              {meta?.meetings.whatsapp ? "WhatsApp messages send automatically." : "WhatsApp messages wait in the queue until WhatsApp Business is connected."} SMS and email are queued until a provider is connected.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}

function Conversation({ ticket, onSend }: { ticket: TicketDetail; onSend: (message: string, visibility: "customer" | "internal") => Promise<boolean> }) {
  const [visibility, setVisibility] = useState<"customer" | "internal">("customer");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    if (await onSend(text.trim(), visibility)) setText("");
    setBusy(false);
  }

  return (
    <section className="admin-card">
      <h2>Conversation</h2>
      <div className="admin-thread">
        {ticket.messages.length === 0 && <p className="muted">No messages yet. Reply to the customer or leave an internal note below.</p>}
        {ticket.messages.map((m) => (
          <div key={m.id} className={`admin-msg ${m.author_type}${m.visibility === "internal" ? " internal" : ""}`}>
            <small>
              {m.author_type === "customer" ? ticket.customer_name : m.author?.name ?? "Homexo"}
              {m.visibility === "internal" && " · internal note"} · {formatDate(m.at)}
            </small>
            <p>{m.message}</p>
          </div>
        ))}
      </div>
      <form className="admin-composer" onSubmit={submit}>
        <div className="admin-toggle" role="radiogroup" aria-label="Message type">
          <button type="button" role="radio" aria-checked={visibility === "customer"} className={visibility === "customer" ? "on" : undefined} onClick={() => setVisibility("customer")}>Reply to customer</button>
          <button type="button" role="radio" aria-checked={visibility === "internal"} className={visibility === "internal" ? "on internal" : undefined} onClick={() => setVisibility("internal")}>Internal note</button>
        </div>
        <textarea rows={3} maxLength={4000} aria-label={visibility === "customer" ? "Message to the customer" : "Internal note"}
          placeholder={visibility === "customer" ? "The customer sees this when they track the request, and gets an SMS/email." : "Only staff can see internal notes."}
          value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn small" disabled={busy || !text.trim()}>{busy ? "Saving…" : visibility === "customer" ? "Send to customer" : "Add note"}</button>
      </form>
    </section>
  );
}

const CLOSED = ["completed", "cancelled", "rejected"];

function StatusCard({ ticket, meta, isAdmin, onSave }: { ticket: TicketDetail; meta: Meta | null; isAdmin: boolean; onSave: (body: object, done: string) => Promise<boolean> }) {
  const [status, setStatus] = useState(ticket.status);
  const [note, setNote] = useState("");
  const [priority, setPriority] = useState(ticket.priority);
  const [priorityNote, setPriorityNote] = useState("");
  const [outcome, setOutcome] = useState("");
  const [summary, setSummary] = useState("");
  const [override, setOverride] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setStatus(ticket.status); setPriority(ticket.priority); }, [ticket.status, ticket.priority]);

  const c = ticket.case;
  const labels = Object.fromEntries((meta?.statuses ?? []).map((s) => [s.value, s.label]));
  // Only the moves the case allows (case_management.allowed_statuses), plus where it is now.
  const options = [ticket.status, ...c.allowed_statuses];
  const moving = status !== ticket.status;
  const closing = moving && CLOSED.includes(status);
  const blocked = status === "completed" && moving && !!c.closure && !c.closure.can_close;
  const reopening = status === "reopened" && moving;
  const changed = moving || priority !== ticket.priority;
  const defaultOutcome = status === "completed" ? "delivered" : status === "cancelled" ? "withdrawn" : "not_viable";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const body = {
      ...(moving ? { status, note: note.trim() || null } : {}),
      ...(closing ? { outcome: outcome || defaultOutcome, closure_summary: summary.trim() || null } : {}),
      ...(blocked && override.trim() ? { override_reason: override.trim() } : {}),
      ...(priority !== ticket.priority ? { priority, priority_note: priorityNote.trim() || null } : {}),
    };
    if (await onSave(body, closing ? "Case closed." : reopening ? "Case reopened." : "Ticket updated.")) { setNote(""); setPriorityNote(""); setSummary(""); setOverride(""); setOutcome(""); }
    setBusy(false);
  }

  return (
    <form className="admin-card admin-form" onSubmit={submit}>
      <h2>Status</h2>
      <label>Stage
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {options.map((s) => <option key={s} value={s}>{s === ticket.status ? `${labels[s] ?? ticket.status_label} (now)` : CLOSED.includes(s) ? `Close as ${(labels[s] ?? s).toLowerCase()}` : s === "reopened" ? "Reopen case" : labels[s] ?? s}</option>)}
        </select>
      </label>
      {moving && (
        <label>{reopening ? "Why reopen it? (the customer sees this)" : "Note for the customer (optional)"}
          <textarea rows={2} maxLength={1000} required={reopening} placeholder={reopening ? "e.g. The seller shared a new deed, so we are checking it." : "e.g. Please share the Mother Deed copy."} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      )}
      {closing && (
        <>
          <label>Outcome
            <select value={outcome || defaultOutcome} onChange={(e) => setOutcome(e.target.value)}>
              {c.outcomes.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label>Closing summary (team only)
            <textarea rows={2} maxLength={2000} placeholder="What was delivered, or why it stopped" value={summary} onChange={(e) => setSummary(e.target.value)} />
          </label>
        </>
      )}
      {blocked && (
        <div className="case-closure">
          <small>Can&apos;t close yet</small>
          <ul>{c.closure!.blockers.map((b) => <li key={b} className="blocker">{b}</li>)}</ul>
          {isAdmin && (
            <label>Close anyway: reason (logged)
              <input maxLength={500} placeholder="e.g. Customer paid in cash at the office" value={override} onChange={(e) => setOverride(e.target.value)} />
            </label>
          )}
        </div>
      )}
      {!closing && (
        <>
          <label>Priority
            <select value={priority} onChange={(e) => setPriority(e.target.value as TicketDetail["priority"])}>
              {(meta?.priorities ?? [ticket.priority]).map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
            </select>
          </label>
          {priority === "urgent" && priority !== ticket.priority && (
            <label>Why is it urgent? (team only)
              <textarea rows={2} maxLength={300} placeholder="e.g. Hearing tomorrow at 10 am; needs the reply notice today." value={priorityNote} onChange={(e) => setPriorityNote(e.target.value)} />
            </label>
          )}
        </>
      )}
      <button className="btn small" disabled={!changed || busy || (blocked && !(isAdmin && override.trim())) || (reopening && !note.trim())}>
        {busy ? "Saving…" : closing ? (blocked ? "Close anyway" : "Close case") : reopening ? "Reopen case" : "Update ticket"}
      </button>
      {moving && <small className="admin-footnote">The customer is notified of the new stage.{closing && c.closure?.warnings.length ? ` ${c.closure.warnings.join(" ")}` : ""}</small>}
      {priority === "urgent" && priority !== ticket.priority && <small className="admin-footnote">{ticket.assignee ? `${ticket.assignee.name} gets an urgent alert on WhatsApp and sees it at the top of their queue.` : "Assign someone and they'll get an urgent alert on WhatsApp."}</small>}
    </form>
  );
}

function AssignCard({ ticket, staff, onAssign }: { ticket: TicketDetail; staff: StaffUser[]; onAssign: (agentId: string | null, note: string) => Promise<boolean> }) {
  const [agentId, setAgentId] = useState(ticket.assignee?.id ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setAgentId(ticket.assignee?.id ?? ""), [ticket.assignee?.id]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    if (await onAssign(agentId || null, note.trim())) setNote("");
    setBusy(false);
  }

  return (
    <form className="admin-card admin-form" onSubmit={submit}>
      <h2>Assignment</h2>
      <label>Case owner
        <select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          <option value="">Unassigned</option>
          {staff.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.role})</option>)}
        </select>
      </label>
      <label>Handover note (optional)
        <input maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Context for the agent" />
      </label>
      <button className="btn small" disabled={busy || agentId === (ticket.assignee?.id ?? "")}>{busy ? "Saving…" : "Save assignment"}</button>
    </form>
  );
}

function listReminders(minutes: number[]): string {
  const words = minutes.map((m) => (m % 1440 === 0 ? `${m / 1440} day${m > 1440 ? "s" : ""}` : m % 60 === 0 ? `${m / 60} hour${m > 60 ? "s" : ""}` : `${m} minutes`));
  return words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words.at(-1)}` : words[0];
}

function MeetingsCard({ ticket, meta, staff, defaultLawyer, onSchedule, onChange }: {
  ticket: TicketDetail;
  meta: Meta | null;
  staff: StaffUser[];
  defaultLawyer: string;
  onSchedule: (body: object) => Promise<boolean>;
  onChange: (meeting: Meeting, body: object, done: string) => Promise<boolean>;
}) {
  const tomorrow = new Date(Date.now() + 86400000);
  tomorrow.setHours(11, 0, 0, 0);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ when: toLocalInput(tomorrow), duration: 30, lawyer: defaultLawyer, agenda: "", link: "" });
  const [busy, setBusy] = useState(false);
  const google = meta?.meetings.google_calendar ?? false;
  const closed = ["completed", "cancelled", "rejected"].includes(ticket.status);
  useEffect(() => setForm((f) => ({ ...f, lawyer: defaultLawyer })), [defaultLawyer]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const body = {
      starts_at: new Date(form.when).toISOString(), duration_minutes: form.duration, lawyer_id: form.lawyer || null,
      agenda: form.agenda.trim() || null, meet_link: form.link.trim() || null,
    };
    if (await onSchedule(body)) {
      setOpen(false);
      setForm({ ...form, agenda: "", link: "" });
    }
    setBusy(false);
  }

  const upcoming = ticket.meetings.filter((m) => m.status === "scheduled");
  const past = ticket.meetings.filter((m) => m.status !== "scheduled");

  return (
    <section className="admin-card">
      <div className="card-head">
        <h2>Video meetings</h2>
        {!closed && !open && <button className="btn small light" onClick={() => setOpen(true)}>Schedule meeting</button>}
      </div>
      {ticket.meetings.length === 0 && !open && <p className="muted">No meetings yet. Book a Google Meet call to discuss the case with the customer.</p>}
      <ul className="meeting-list">
        {[...upcoming, ...past].map((m) => <MeetingItem key={m.id} meeting={m} onChange={onChange} />)}
      </ul>
      {open && (
        <form className="admin-form meeting-form" onSubmit={submit}>
          <div className="form-row">
            <label>Date and time<input type="datetime-local" required value={form.when} min={toLocalInput(new Date())} onChange={(e) => setForm({ ...form, when: e.target.value })} /></label>
            <label>Length
              <select value={form.duration} onChange={(e) => setForm({ ...form, duration: Number(e.target.value) })}>
                {[15, 30, 45, 60, 90].map((m) => <option key={m} value={m}>{m} min</option>)}
              </select>
            </label>
          </div>
          <label>Lawyer
            <select value={form.lawyer} onChange={(e) => setForm({ ...form, lawyer: e.target.value })}>
              {staff.map((s) => <option key={s.id} value={s.id}>{s.name}{s.phone ? "" : " (no WhatsApp number)"}</option>)}
            </select>
          </label>
          <label>Agenda (the customer sees this)
            <textarea rows={2} maxLength={1000} placeholder="e.g. Walk through the title chain and the missing Khata." value={form.agenda} onChange={(e) => setForm({ ...form, agenda: e.target.value })} />
          </label>
          {!google && (
            <label>Meeting link
              <input type="url" required pattern="https://.*" placeholder="https://meet.google.com/…" value={form.link} onChange={(e) => setForm({ ...form, link: e.target.value })} />
            </label>
          )}
          <div className="form-actions">
            <button className="btn small" disabled={busy}>{busy ? "Booking…" : google ? "Book and create Meet link" : "Book meeting"}</button>
            <button type="button" className="admin-link" onClick={() => setOpen(false)}>Cancel</button>
          </div>
          <small className="admin-footnote">
            {google ? "Creates a Google Calendar event with a Meet link and invites the customer and lawyer by email." : "Google Calendar isn't connected, so paste a Meet link you created."}
            {" "}Both get the link on WhatsApp{meta?.meetings.reminder_minutes.length ? `, with reminders ${listReminders(meta.meetings.reminder_minutes)} before` : ""}.
          </small>
        </form>
      )}
    </section>
  );
}

function MeetingItem({ meeting, onChange }: { meeting: Meeting; onChange: (meeting: Meeting, body: object, done: string) => Promise<boolean> }) {
  const [mode, setMode] = useState<"" | "move" | "cancel" | "link">("");
  const [when, setWhen] = useState(toLocalInput(new Date(meeting.starts_at)));
  const [reason, setReason] = useState("");
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const scheduled = meeting.status === "scheduled";
  const started = Date.now() >= new Date(meeting.starts_at).getTime();

  async function run(body: object, done: string) {
    setBusy(true);
    if (await onChange(meeting, body, done)) setMode("");
    setBusy(false);
  }

  return (
    <li className={`meeting-item${scheduled ? "" : " past"}`}>
      <div className="meeting-top">
        <div>
          <b>{meeting.when}</b>
          <small>{Math.round((new Date(meeting.ends_at).getTime() - new Date(meeting.starts_at).getTime()) / 60000)} min · {meeting.lawyer.name}{meeting.calendar === "google" ? " · Google Calendar" : ""}</small>
        </div>
        {scheduled && meeting.meet_link
          ? <a className={`btn small${joinable(meeting) ? "" : " light"}`} href={meeting.meet_link} target="_blank" rel="noreferrer">Join</a>
          : <span className={`admin-pill pill-meeting-${meeting.status}`}>{meeting.status_label}</span>}
      </div>
      {meeting.agenda && <p className="meeting-agenda">{meeting.agenda}</p>}
      {scheduled && mode === "" && (
        <div className="staff-actions">
          {!meeting.meet_link && <button className="admin-link" onClick={() => setMode("link")}>Add meeting link</button>}
          <button className="admin-link" onClick={() => setMode("move")}>Reschedule</button>
          <button className="admin-link" onClick={() => setMode("cancel")}>Cancel meeting</button>
          {started && <button className="admin-link" disabled={busy} onClick={() => run({ status: "completed" }, "Meeting marked done.")}>Mark done</button>}
        </div>
      )}
      {mode === "move" && (
        <form className="meeting-inline" onSubmit={(e) => { e.preventDefault(); run({ starts_at: new Date(when).toISOString() }, "Meeting moved. Both sides get the new time on WhatsApp."); }}>
          <input type="datetime-local" required value={when} min={toLocalInput(new Date())} onChange={(e) => setWhen(e.target.value)} aria-label="New date and time" />
          <button className="btn small" disabled={busy}>Move</button>
          <button type="button" className="admin-link" onClick={() => setMode("")}>Back</button>
        </form>
      )}
      {mode === "link" && (
        <form className="meeting-inline" onSubmit={(e) => { e.preventDefault(); run({ meet_link: link.trim() }, "Link added. The customer and lawyer get it on WhatsApp."); }}>
          <input type="url" required pattern="https://.*" placeholder="https://meet.google.com/..." value={link} onChange={(e) => setLink(e.target.value)} aria-label="Meeting link" />
          <button className="btn small" disabled={busy}>Send link</button>
          <button type="button" className="admin-link" onClick={() => setMode("")}>Back</button>
        </form>
      )}
      {mode === "cancel" && (
        <form className="meeting-inline" onSubmit={(e) => { e.preventDefault(); run({ status: "cancelled", reason: reason.trim() || null }, "Meeting cancelled. Both sides are told on WhatsApp."); }}>
          <input maxLength={500} placeholder="Reason sent to both (optional)" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" />
          <button className="btn small" disabled={busy}>Cancel it</button>
          <button type="button" className="admin-link" onClick={() => setMode("")}>Back</button>
        </form>
      )}
    </li>
  );
}
