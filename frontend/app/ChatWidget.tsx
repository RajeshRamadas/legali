"use client";

import { useEffect, useRef, useState } from "react";
import {
  PROPERTY_TYPES,
  type ChatReply,
  type ChatTicket,
  type PropertyType,
  type Service,
  type TicketStatus,
} from "@homexo/shared";
import { api } from "./api";
import { useAssistant } from "./ui/useAssistant";
import { TicketStatusCard } from "./TrackRequest";

export default function ChatWidget() {
  const {
    open,
    setOpen,
    messages,
    setMessages,
    suggestions,
    setSuggestions,
    input,
    setInput,
    thinking,
    form,
    setForm,
    verified,
    setVerified,
    conversationId,
    push,
    send,
  } = useAssistant();
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    logRef.current?.scrollTo({
      top: logRef.current.scrollHeight,
      behavior: matchMedia("(prefers-reduced-motion:reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [messages, form, thinking]);

  return (
    <>
      <button
        className={`chat-fab${open ? " is-open" : ""}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls="chat-panel"
      >
        <span className="chat-fab-icon">{open ? "×" : "✳"}</span>
        {open ? "Close" : "Need help?"}
      </button>
      {open && (
        <section
          className="chat-panel"
          id="chat-panel"
          aria-label="Homexo Legal assistant"
        >
          <header className="chat-head">
            <span className="brandmark">H</span>
            <div>
              <b>Homexo Legal assistant</b>
              <small>Answers instantly · specialists call back</small>
            </div>
          </header>
          <div className="chat-log" ref={logRef} aria-live="polite">
            {messages.map((m) => (
              <div key={m.id} className={`chat-msg ${m.from}`}>
                <p>{m.text}</p>
                {m.from === "bot" && m.sources && m.sources.length > 0 && (
                  <small className="chat-sources">
                    From: {m.sources.map((s) => s.section).join(" · ")}
                  </small>
                )}
                {m.from === "bot" && m.status && (
                  <TicketStatusCard
                    ticket={m.status}
                    contact={
                      verified?.ticket_number === m.status.ticket_number
                        ? verified.contact
                        : undefined
                    }
                    onUpdate={(status) =>
                      setMessages((prev) =>
                        prev.map((x) => (x.id === m.id ? { ...x, status } : x)),
                      )
                    }
                  />
                )}
                {m.from === "bot" &&
                  m.offer &&
                  !(form?.kind === "request" && form.messageId === m.id) && (
                    <button
                      className="chat-action"
                      onClick={() =>
                        setForm({
                          kind: "request",
                          service: m.offer!,
                          messageId: m.id,
                        })
                      }
                    >
                      Request a callback for {m.offer.name} →
                    </button>
                  )}
                {form &&
                  form.messageId === m.id &&
                  (form.kind === "request" ? (
                    <ChatRequestForm
                      service={form.service}
                      conversationId={conversationId}
                      onDone={(ticket, phone) => {
                        setForm(null);
                        setVerified({ ticket_number: ticket, contact: phone });
                        push({
                          from: "bot",
                          text: `Done! Your ticket number is ${ticket}. A specialist will call you to confirm scope, documents and fees. Ask me to "track my request" any time.`,
                        });
                        setSuggestions(["Track my request", "Package prices"]);
                      }}
                      onCancel={() => setForm(null)}
                    />
                  ) : (
                    <ChatTrackForm
                      ticketNumber={form.ticketNumber}
                      onDone={(status, contact) => {
                        setForm(null);
                        setVerified({
                          ticket_number: status.ticket_number,
                          contact,
                        });
                        push({
                          from: "bot",
                          text: `Here's the latest on ${status.ticket_number}. You can message your case team below, or ask me about this request.`,
                          status,
                        });
                        setSuggestions([
                          "What's happening with my request?",
                          "What do you need from me?",
                        ]);
                      }}
                      onCancel={() => setForm(null)}
                    />
                  ))}
              </div>
            ))}
            {thinking && (
              <div className="chat-msg bot typing">
                <p>
                  <i />
                  <i />
                  <i />
                </p>
              </div>
            )}
          </div>
          {suggestions.length > 0 && (
            <div className="chat-suggestions">
              {suggestions.map((s) => (
                <button key={s} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <input
              aria-label="Type your question"
              placeholder="Ask about your property…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={1000}
            />
            <button
              className="btn small"
              type="submit"
              disabled={!input.trim() || thinking}
              aria-label="Send"
            >
              ↑
            </button>
          </form>
          <small className="chat-note">
            Chats are saved so our team can follow up on your request. A
            specialist confirms scope and fees on the call.
          </small>
        </section>
      )}
    </>
  );
}

export function ChatRequestForm({
  service,
  conversationId,
  onDone,
  onCancel,
}: {
  service: Service;
  conversationId: string | null;
  onDone: (ticket: string, phone: string) => void;
  onCancel: () => void;
}) {
  const types = PROPERTY_TYPES.filter((t) =>
    service.property_types.includes(t.value),
  );
  const [values, setValues] = useState({
    name: "",
    phone: "",
    propertyType: (types[0]?.value ?? "other") as PropertyType,
    location: "",
  });
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
      setError(
        err instanceof Error ? err.message : "Could not raise the request.",
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="chat-form" onSubmit={submit}>
      <b>{service.name}</b>
      <input
        aria-label="Your name"
        placeholder="Your name"
        required
        minLength={2}
        value={values.name}
        onChange={(e) => setValues({ ...values, name: e.target.value })}
      />
      <input
        aria-label="Phone number"
        type="tel"
        placeholder="Phone number"
        required
        pattern="[0-9+\(\) \-]{8,18}"
        value={values.phone}
        onChange={(e) => setValues({ ...values, phone: e.target.value })}
      />
      <select
        aria-label="Property type"
        value={values.propertyType}
        onChange={(e) =>
          setValues({ ...values, propertyType: e.target.value as PropertyType })
        }
      >
        {types.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
      <input
        aria-label="Property location"
        placeholder="Property location (area, city)"
        required
        minLength={2}
        value={values.location}
        onChange={(e) => setValues({ ...values, location: e.target.value })}
      />
      {error && (
        <small className="form-error" role="alert">
          {error}
        </small>
      )}
      <div className="chat-form-actions">
        <button className="btn small" disabled={sending}>
          {sending ? "Sending…" : "Raise request"}
        </button>
        <button type="button" className="text-link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function ChatTrackForm({
  ticketNumber,
  onDone,
  onCancel,
}: {
  ticketNumber: string;
  onDone: (status: TicketStatus, contact: string) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState({ ticket: ticketNumber, contact: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      onDone(
        await api.lookupTicket(values.ticket.trim(), values.contact.trim()),
        values.contact.trim(),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not check that request.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="chat-form" onSubmit={submit}>
      <input
        aria-label="Ticket number"
        placeholder="Ticket number, e.g. HX-261018-ABC123"
        required
        value={values.ticket}
        onChange={(e) => setValues({ ...values, ticket: e.target.value })}
      />
      <input
        aria-label="Phone or email"
        placeholder="Phone or email you used"
        required
        value={values.contact}
        onChange={(e) => setValues({ ...values, contact: e.target.value })}
      />
      {error && (
        <small className="form-error" role="alert">
          {error}
        </small>
      )}
      <div className="chat-form-actions">
        <button className="btn small" disabled={loading}>
          {loading ? "Checking…" : "Check status"}
        </button>
        <button type="button" className="text-link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
