"use client";

import { useEffect, useState } from "react";
import type { TicketStatus } from "@homexo/shared";
import { api } from "./api";

const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });

// With `contact`, the customer can also reply to the case team from the card.
export function TicketStatusCard({ ticket, contact, onUpdate }: { ticket: TicketStatus; contact?: string; onUpdate?: (ticket: TicketStatus) => void }) {
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function sendReply(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contact || !reply.trim()) return;
    setError("");
    setSending(true);
    try {
      onUpdate?.(await api.replyToTicket(ticket.ticket_number, contact, reply.trim()));
      setReply("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send your message.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="ticket-status">
      <div className="ticket-status-top">
        <div><span className="tiny-label">Ticket</span><b>{ticket.ticket_number}</b></div>
        <span className={`status-pill status-${ticket.status}`}>{ticket.status_label}</span>
      </div>
      <p className="ticket-service">{ticket.service_name}{ticket.package ? ` · ${ticket.package}` : ""}</p>
      <ol className="ticket-timeline">
        {ticket.history.map((event) => (
          <li key={`${event.status}-${event.at}`}>
            <b>{event.label}</b>
            <small>{dateFormat.format(new Date(event.at))}</small>
            {event.note && <p>{event.note}</p>}
          </li>
        ))}
      </ol>
      {ticket.meetings?.length > 0 && <TicketMeetings meetings={ticket.meetings} />}
      {ticket.messages.length > 0 && (
        <div className="ticket-messages">
          <span className="tiny-label">Messages</span>
          {ticket.messages.map((m, i) => (
            <div key={i} className={`ticket-message from-${m.from}`}>
              <small>{m.from === "you" ? "You" : "Homexo case team"} · {dateFormat.format(new Date(m.at))}</small>
              <p>{m.message}</p>
            </div>
          ))}
        </div>
      )}
      {contact && ticket.can_reply && (
        <form className="ticket-reply" onSubmit={sendReply}>
          <label htmlFor={`reply-${ticket.ticket_number}`}>Message the case team</label>
          <textarea id={`reply-${ticket.ticket_number}`} rows={2} maxLength={4000} placeholder="Answer a question or share an update" value={reply} onChange={(e) => setReply(e.target.value)} />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="btn small" disabled={sending || !reply.trim()}>{sending ? "Sending…" : "Send message"}</button>
        </form>
      )}
    </div>
  );
}

// Join opens 15 minutes before the start; the button turns prominent then, and the card re-checks every 20 seconds.
function TicketMeetings({ meetings }: { meetings: TicketStatus["meetings"] }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 20000);
    return () => clearInterval(tick);
  }, []);
  const open = (m: TicketStatus["meetings"][number]) => m.status === "scheduled" && !!m.meet_link && now >= new Date(m.starts_at).getTime() - 15 * 60000 && now <= new Date(m.ends_at).getTime();
  const visible = meetings.filter((m) => m.status !== "cancelled" || new Date(m.starts_at).getTime() > now);

  if (visible.length === 0) return null;
  return (
    <div className="ticket-meetings">
      <span className="tiny-label">Video consultation</span>
      {visible.map((m) => (
        <div key={m.id} className={`ticket-meeting${open(m) ? " live" : ""}${m.status === "scheduled" ? "" : " done"}`}>
          <div>
            <b>{m.when}</b>
            <small>{m.status === "scheduled" ? `With ${m.lawyer_name} on Google Meet` : m.status_label}</small>
            {m.agenda && m.status === "scheduled" && <p>{m.agenda}</p>}
          </div>
          {m.status === "scheduled" && m.meet_link && (
            <a className={`btn small${open(m) ? " gold" : " light"}`} href={m.meet_link} target="_blank" rel="noreferrer">{open(m) ? "Join now" : "Meeting link"}</a>
          )}
        </div>
      ))}
    </div>
  );
}

export default function TrackRequest({ initialTicket = "", initialContact = "" }: { initialTicket?: string; initialContact?: string }) {
  const [ticketNumber, setTicketNumber] = useState(initialTicket);
  const [contact, setContact] = useState(initialContact);
  const [result, setResult] = useState<TicketStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function lookup() {
    setError("");
    setLoading(true);
    try {
      setResult(await api.lookupTicket(ticketNumber.trim(), contact.trim()));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "We couldn't check that request. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  // Coming from a just-created ticket: show its status straight away.
  useEffect(() => {
    if (initialTicket && initialContact) lookup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="track-band" id="track">
      <div className="wrap track-grid">
        <div>
          <div className="eyebrow">Track your request</div>
          <h2>Know where your case stands.</h2>
          <p>Enter the ticket number from your confirmation with the phone number or email you used. Updates reflect what our case team has recorded.</p>
        </div>
        <div>
          <form className="track-form" onSubmit={(e) => { e.preventDefault(); lookup(); }}>
            <div className="field"><label htmlFor="trackTicket">Ticket number</label><input id="trackTicket" placeholder="HX-261018-ABC123" required value={ticketNumber} onChange={(e) => setTicketNumber(e.target.value)} /></div>
            <div className="field"><label htmlFor="trackContact">Phone or email</label><input id="trackContact" placeholder="Used when you raised it" required value={contact} onChange={(e) => setContact(e.target.value)} /></div>
            <button className="btn" type="submit" disabled={loading}>{loading ? "Checking…" : "Check status →"}</button>
          </form>
          {error && <p className="form-error" role="alert">{error}</p>}
          {result && <TicketStatusCard ticket={result} contact={contact.trim()} onUpdate={setResult} />}
        </div>
      </div>
    </section>
  );
}
