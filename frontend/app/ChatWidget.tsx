"use client";

import { useEffect, useRef, useState } from "react";
import { PROPERTY_TYPES, type ChatReply, type ChatTicket, type PropertyType, type Service, type TicketStatus } from "@homexo/shared";
import { api } from "./api";
import { ASK_EVENT } from "./homeEvents";
import { TicketStatusCard } from "./TrackRequest";

type NewMessage =
  | { from: "user"; text: string }
  | { from: "bot"; text: string; offer?: Service | null; status?: TicketStatus; sources?: ChatReply["sources"] };
type Message = NewMessage & { id: number };

type OpenForm = { kind: "request"; service: Service; messageId: number } | { kind: "track"; ticketNumber: string; messageId: number } | null;

const WELCOME: Message = {
  id: 0,
  from: "bot",
  text: "Hi! I'm the Homexo Legal assistant. Ask me about packages, title checks, registration or documents. I can also raise a callback request or track one for you.",
};
const STARTERS = ["Is this property safe to buy?", "Package prices", "Developer services", "Track my request"];

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [suggestions, setSuggestions] = useState(STARTERS);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [form, setForm] = useState<OpenForm>(null);
  // The ticket the customer verified in this chat. Sent with each question so answers can use it.
  const [verified, setVerified] = useState<ChatTicket | null>(null);
  // The saved conversation on the server; it holds the history and is shown to staff on any ticket raised from it.
  const [conversationId, setConversationId] = useState<string | null>(null);
  const nextId = useRef(1);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, form, thinking]);

  function push(message: NewMessage) {
    const id = nextId.current++;
    setMessages((prev) => [...prev, { ...message, id }]);
    return id;
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || thinking) return;
    setInput("");
    setForm(null);
    setSuggestions([]);
    push({ from: "user", text: message });
    setThinking(true);
    try {
      const reply = await api.chat(message, { conversationId, ticket: verified });
      setConversationId(reply.conversation_id);
      if (verified && !reply.ticket_verified) setVerified(null);
      push({ from: "bot", text: reply.reply, offer: reply.action === "request" ? reply.service : null, status: reply.ticket ?? undefined, sources: reply.sources });
      setSuggestions(reply.suggestions);
      if (reply.action === "track") setForm({ kind: "track", ticketNumber: reply.ticket_number ?? "", messageId: nextId.current - 1 });
    } catch {
      push({ from: "bot", text: "I couldn't reach our team just now. Please use the callback form on this page, or try again in a moment." });
      setSuggestions(STARTERS);
    } finally {
      setThinking(false);
    }
  }

  // Elsewhere on the page (the home page's "Ask a question" box) can open the chat, with a question to send.
  const sendRef = useRef(send);
  sendRef.current = send;
  useEffect(() => {
    function onAsk(event: Event) {
      setOpen(true);
      const question = (event as CustomEvent<string>).detail;
      if (question) sendRef.current(question);
    }
    window.addEventListener(ASK_EVENT, onAsk);
    return () => window.removeEventListener(ASK_EVENT, onAsk);
  }, []);

  return (
    <>
      <button className={`chat-fab${open ? " is-open" : ""}`} onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="chat-panel">
        <span className="chat-fab-icon">{open ? "×" : "✳"}</span>{open ? "Close" : "Need help?"}
      </button>
      {open && (
        <section className="chat-panel" id="chat-panel" aria-label="Homexo Legal assistant">
          <header className="chat-head">
            <span className="brandmark">H</span>
            <div><b>Homexo Legal assistant</b><small>Answers instantly · specialists call back</small></div>
          </header>
          <div className="chat-log" ref={logRef} aria-live="polite">
            {messages.map((m) => (
              <div key={m.id} className={`chat-msg ${m.from}`}>
                <p>{m.text}</p>
                {m.from === "bot" && m.sources && m.sources.length > 0 && (
                  <small className="chat-sources">From: {m.sources.map((s) => s.section).join(" · ")}</small>
                )}
                {m.from === "bot" && m.status && (
                  <TicketStatusCard
                    ticket={m.status}
                    contact={verified?.ticket_number === m.status.ticket_number ? verified.contact : undefined}
                    onUpdate={(status) => setMessages((prev) => prev.map((x) => (x.id === m.id ? { ...x, status } : x)))}
                  />
                )}
                {m.from === "bot" && m.offer && !(form?.kind === "request" && form.messageId === m.id) && (
                  <button className="chat-action" onClick={() => setForm({ kind: "request", service: m.offer!, messageId: m.id })}>
                    Request a callback for {m.offer.name} →
                  </button>
                )}
                {form && form.messageId === m.id && (
                  form.kind === "request"
                    ? <ChatRequestForm service={form.service} conversationId={conversationId} onDone={(ticket, phone) => { setForm(null); setVerified({ ticket_number: ticket, contact: phone }); push({ from: "bot", text: `Done! Your ticket number is ${ticket}. A specialist will call you to confirm scope, documents and fees. Ask me to "track my request" any time.` }); setSuggestions(["Track my request", "Package prices"]); }} onCancel={() => setForm(null)} />
                    : <ChatTrackForm ticketNumber={form.ticketNumber} onDone={(status, contact) => { setForm(null); setVerified({ ticket_number: status.ticket_number, contact }); push({ from: "bot", text: `Here's the latest on ${status.ticket_number}. You can message your case team below, or ask me about this request.`, status }); setSuggestions(["What's happening with my request?", "What do you need from me?"]); }} onCancel={() => setForm(null)} />
                )}
              </div>
            ))}
            {thinking && <div className="chat-msg bot typing"><p><i /><i /><i /></p></div>}
          </div>
          {suggestions.length > 0 && (
            <div className="chat-suggestions">{suggestions.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
          )}
          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input aria-label="Type your question" placeholder="Ask about your property…" value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000} />
            <button className="btn small" type="submit" disabled={!input.trim() || thinking} aria-label="Send">↑</button>
          </form>
          <small className="chat-note">Chats are saved so our team can follow up on your request. A specialist confirms scope and fees on the call.</small>
        </section>
      )}
    </>
  );
}

function ChatRequestForm({ service, conversationId, onDone, onCancel }: { service: Service; conversationId: string | null; onDone: (ticket: string, phone: string) => void; onCancel: () => void }) {
  const types = PROPERTY_TYPES.filter((t) => service.property_types.includes(t.value));
  const [values, setValues] = useState({ name: "", phone: "", propertyType: (types[0]?.value ?? "other") as PropertyType, location: "" });
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSending(true);
    try {
      const data = await api.createTicket({
        customer_name: values.name.trim(),
        contact: values.phone.trim(),
        property_type: values.propertyType,
        service_slug: service.slug,
        location: values.location.trim(),
        description: "Raised from the website chat assistant.",
        source: "chat",
        conversation_id: conversationId,
      });
      onDone(data.ticket_number, values.phone.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not raise the request.");
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="chat-form" onSubmit={submit}>
      <b>{service.name}</b>
      <input aria-label="Your name" placeholder="Your name" required minLength={2} value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} />
      <input aria-label="Phone number" type="tel" placeholder="Phone number" required pattern="[0-9+\(\) \-]{8,18}" value={values.phone} onChange={(e) => setValues({ ...values, phone: e.target.value })} />
      <select aria-label="Property type" value={values.propertyType} onChange={(e) => setValues({ ...values, propertyType: e.target.value as PropertyType })}>
        {types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>
      <input aria-label="Property location" placeholder="Property location (area, city)" required minLength={2} value={values.location} onChange={(e) => setValues({ ...values, location: e.target.value })} />
      {error && <small className="form-error" role="alert">{error}</small>}
      <div className="chat-form-actions"><button className="btn small" disabled={sending}>{sending ? "Sending…" : "Raise request"}</button><button type="button" className="text-link" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}

function ChatTrackForm({ ticketNumber, onDone, onCancel }: { ticketNumber: string; onDone: (status: TicketStatus, contact: string) => void; onCancel: () => void }) {
  const [values, setValues] = useState({ ticket: ticketNumber, contact: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      onDone(await api.lookupTicket(values.ticket.trim(), values.contact.trim()), values.contact.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not check that request.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="chat-form" onSubmit={submit}>
      <input aria-label="Ticket number" placeholder="Ticket number, e.g. HX-261018-ABC123" required value={values.ticket} onChange={(e) => setValues({ ...values, ticket: e.target.value })} />
      <input aria-label="Phone or email" placeholder="Phone or email you used" required value={values.contact} onChange={(e) => setValues({ ...values, contact: e.target.value })} />
      {error && <small className="form-error" role="alert">{error}</small>}
      <div className="chat-form-actions"><button className="btn small" disabled={loading}>{loading ? "Checking…" : "Check status"}</button><button type="button" className="text-link" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}
