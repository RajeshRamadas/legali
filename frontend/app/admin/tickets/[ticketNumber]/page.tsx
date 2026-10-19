"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PROPERTY_TYPES } from "@homexo/shared";
import { useStaff } from "../../AdminShell";
import { adminFetch, formatDate, type Meta, type StaffUser, type TicketDetail } from "../../api";

const EVENT_TEXT: Record<string, (e: TicketDetail["events"][number], labels: Record<string, string>) => string> = {
  created: () => "Request raised",
  status_changed: (e, labels) => `Status: ${labels[e.old?.status ?? ""] ?? e.old?.status} → ${labels[e.new?.status ?? ""] ?? e.new?.status}`,
  priority_changed: (e) => `Priority: ${e.old?.priority} → ${e.new?.priority}`,
  assigned: (e) => (e.old?.agent ? `Reassigned from ${e.old.agent} to ${e.new?.agent}` : `Assigned to ${e.new?.agent}`),
  unassigned: (e) => `Unassigned${e.old?.agent ? ` from ${e.old.agent}` : ""}`,
  message_sent: () => "Message sent to customer",
  note_added: () => "Internal note added",
  customer_replied: () => "Customer replied",
};

export default function TicketPage({ params }: { params: { ticketNumber: string } }) {
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
  async function act(path: string, method: "PATCH" | "POST", body: object, done: string) {
    setError("");
    setNotice("");
    try {
      setTicket(await adminFetch<TicketDetail>(`/admin/tickets/${encodeURIComponent(params.ticketNumber)}${path}`, { method, body: JSON.stringify(body) }));
      setNotice(done);
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
          <Conversation ticket={ticket} onSend={(message, visibility) => act("/messages", "POST", { message, visibility }, visibility === "internal" ? "Internal note added." : "Message sent to the customer.")} />

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
                  <small>{e.actor ? e.actor.name : e.type === "customer_replied" || e.type === "created" ? "Customer" : "System"} · {formatDate(e.at)}</small>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="ticket-side">
          <StatusCard ticket={ticket} meta={meta} onSave={(body, done) => act("", "PATCH", body, done)} />
          {user.role === "admin" && <AssignCard ticket={ticket} staff={staff} onAssign={(agent_id, note) => act("/assignment", "POST", { agent_id, note: note || null }, agent_id ? "Ticket assigned." : "Ticket unassigned.")} />}
          {user.role !== "admin" && <section className="admin-card"><h2>Assigned to</h2><p>{ticket.assignee?.name ?? "Unassigned"}</p></section>}

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
            <h2>Customer notifications</h2>
            {ticket.notifications.length === 0 ? <p className="muted">None yet.</p> : (
              <ul className="admin-notifications">
                {[...ticket.notifications].reverse().map((n, i) => (
                  <li key={i}><b>{n.template.replace(/_/g, " ")}</b><small>{n.channel.toUpperCase()} · {n.status} · {formatDate(n.at)}</small></li>
                ))}
              </ul>
            )}
            <p className="admin-footnote">Queued until an SMS or email provider is connected.</p>
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

function StatusCard({ ticket, meta, onSave }: { ticket: TicketDetail; meta: Meta | null; onSave: (body: object, done: string) => Promise<boolean> }) {
  const [status, setStatus] = useState(ticket.status);
  const [note, setNote] = useState("");
  const [priority, setPriority] = useState(ticket.priority);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setStatus(ticket.status); setPriority(ticket.priority); }, [ticket.status, ticket.priority]);

  const changed = status !== ticket.status || priority !== ticket.priority;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const body = { ...(status !== ticket.status ? { status, note: note.trim() || null } : {}), ...(priority !== ticket.priority ? { priority } : {}) };
    if (await onSave(body, "Ticket updated.")) setNote("");
    setBusy(false);
  }

  return (
    <form className="admin-card admin-form" onSubmit={submit}>
      <h2>Status</h2>
      <label>Stage
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {meta?.statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>) ?? <option value={ticket.status}>{ticket.status_label}</option>}
        </select>
      </label>
      {status !== ticket.status && (
        <label>Note for the customer (optional)
          <textarea rows={2} maxLength={1000} placeholder="e.g. Please share the Mother Deed copy." value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      )}
      <label>Priority
        <select value={priority} onChange={(e) => setPriority(e.target.value as TicketDetail["priority"])}>
          {(meta?.priorities ?? [ticket.priority]).map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
        </select>
      </label>
      <button className="btn small" disabled={!changed || busy}>{busy ? "Saving…" : "Update ticket"}</button>
      {status !== ticket.status && <small className="admin-footnote">The customer is notified of the new stage.</small>}
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
