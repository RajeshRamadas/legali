"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { useAssistant } from "./useAssistant";
import { Badge, Button, Card } from "./primitives";
import Icon from "./Icon";
import Markdown from "../Markdown";
import { ChatRequestForm, ChatTrackForm } from "../ChatWidget";
import { TicketStatusCard } from "../TrackRequest";
export default function AssistantPanel({
  compact = false,
}: {
  compact?: boolean;
}) {
  const a = useAssistant();
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => {
    log.current?.scrollTo({
      top: log.current.scrollHeight,
      behavior: matchMedia("(prefers-reduced-motion:reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [a.messages, a.thinking]);
  function exportChat() {
    const url = URL.createObjectURL(
      new Blob(
        [
          a.messages
            .map((m) => `${m.from === "user" ? "You" : "Homexo"}: ${m.text}`)
            .join("\n\n"),
        ],
        { type: "text/plain;charset=utf-8" },
      ),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "homexo-conversation.txt";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <Card
      className={`hx-assistant ${compact ? "compact" : ""}`}
      title="Legal assistant"
      icon="spark"
      action={
        compact ? (
          <Badge tone="green">Online</Badge>
        ) : (
          <div className="hx-page-actions">
            <Button icon="download" size="sm" onClick={exportChat}>
              Export
            </Button>
            <Button size="sm" onClick={a.clear} disabled={a.thinking}>
              Clear
            </Button>
          </div>
        )
      }
    >
      <div
        className="hx-assistant-log"
        ref={log}
        role="log"
        aria-label="Assistant conversation"
        aria-live="polite"
      >
        {(compact ? a.messages.slice(-2) : a.messages).map((m) => (
          <div key={m.id} className={`hx-assistant-message ${m.from}`}>
            {m.from === "bot" && (
              <span className="hx-assistant-mark">
                <Icon name="spark" size={16} />
              </span>
            )}
            <div className="hx-assistant-bubble">
              <Markdown
                source={m.text.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")}
              />
              {m.from === "bot" &&
                m.sources?.map((source, i) => (
                  <Badge tone="gray" key={i}>
                    {source.title || source.section}
                  </Badge>
                ))}
              {m.from === "bot" && m.offer && a.form?.messageId !== m.id && (
                <div className="hx-handoff">
                  <strong>A lawyer can help with {m.offer.name}</strong>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() =>
                      a.setForm({
                        kind: "request",
                        service: m.offer!,
                        messageId: m.id,
                      })
                    }
                  >
                    Start a request
                  </Button>
                </div>
              )}
              {m.from === "bot" && m.status && (
                <TicketStatusCard
                  ticket={m.status}
                  contact={
                    a.verified?.ticket_number === m.status.ticket_number
                      ? a.verified.contact
                      : undefined
                  }
                  onUpdate={(status) =>
                    a.setMessages((prev) =>
                      prev.map((x) => (x.id === m.id ? { ...x, status } : x)),
                    )
                  }
                />
              )}
              {a.form?.messageId === m.id &&
                (a.form.kind === "request" ? (
                  <ChatRequestForm
                    service={a.form.service}
                    conversationId={a.conversationId}
                    onCancel={() => a.setForm(null)}
                    onDone={(ticket, contact) => {
                      a.setForm(null);
                      a.setVerified({ ticket_number: ticket, contact });
                      a.push({
                        from: "bot",
                        text: `Your request is ${ticket}. A specialist will confirm scope, documents and fees.`,
                      });
                    }}
                  />
                ) : (
                  <ChatTrackForm
                    ticketNumber={a.form.ticketNumber}
                    onCancel={() => a.setForm(null)}
                    onDone={(status, contact) => {
                      a.setForm(null);
                      a.setVerified({
                        ticket_number: status.ticket_number,
                        contact,
                      });
                      a.push({
                        from: "bot",
                        text: `Here is the latest on ${status.ticket_number}.`,
                        status,
                      });
                    }}
                  />
                ))}
            </div>
          </div>
        ))}
        {a.thinking && <p role="status">Looking that up…</p>}
      </div>
      <div className="hx-suggestions">
        {a.suggestions.slice(0, 3).map((s) => (
          <button
            className="hx-chip"
            key={s}
            disabled={a.thinking}
            onClick={() => a.send(s)}
          >
            {s}
          </button>
        ))}
      </div>
      <form
        className="hx-assistant-input"
        onSubmit={(e) => {
          e.preventDefault();
          a.send(a.input);
        }}
      >
        <input
          value={a.input}
          onChange={(e) => a.setInput(e.target.value)}
          maxLength={1000}
          placeholder="Ask about a property, document or law…"
          aria-label="Message the legal assistant"
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={a.thinking || !a.input.trim()}
        >
          <Icon name="send" />
        </button>
      </form>
      {compact ? (
        <Link className="hx-text-link" href="/assistant">
          Open full chat →
        </Link>
      ) : (
        <small>
          Guidance, not a legal opinion. Chats are saved so your case team can
          follow up.
        </small>
      )}
    </Card>
  );
}
