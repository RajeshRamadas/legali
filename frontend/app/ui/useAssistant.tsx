"use client";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type {
  ChatReply,
  ChatTicket,
  Service,
  TicketStatus,
} from "@homexo/shared";
import { api } from "../api";
import { ASK_EVENT } from "../homeEvents";
import { readSession } from "../account/session";
export type NewMessage =
  | { from: "user"; text: string }
  | {
      from: "bot";
      text: string;
      offer?: Service | null;
      status?: TicketStatus;
      sources?: ChatReply["sources"];
    };
export type Message = NewMessage & { id: number };
export type OpenForm =
  | { kind: "request"; service: Service; messageId: number }
  | { kind: "track"; ticketNumber: string; messageId: number }
  | null;
const WELCOME: Message = {
  id: 0,
  from: "bot",
  text: "Hello. I’m the Homexo Legal assistant. Ask about property checks, packages or documents, or track your request.",
};
const STARTERS = [
  "RERA check",
  "Which package?",
  "Talk to a lawyer",
  "Track my request",
];
function useCore() {
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
  const busy = useRef(false);
  const epoch = useRef(0);
  useEffect(() => {
    let token = readSession()?.token ?? null;
    const changed = () => {
      const next = readSession()?.token ?? null;
      if (next !== token) {
        token = next;
        clear();
        setOpen(false);
      }
    };
    window.addEventListener("homexo-session", changed);
    window.addEventListener("storage", changed);
    return () => {
      window.removeEventListener("homexo-session", changed);
      window.removeEventListener("storage", changed);
    };
  }, []);

  function push(message: NewMessage) {
    const id = nextId.current++;
    setMessages((prev) => [...prev, { ...message, id }]);
    return id;
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy.current) return;
    busy.current = true;
    const generation = epoch.current;
    setInput("");
    setForm(null);
    setSuggestions([]);
    push({ from: "user", text: message });
    setThinking(true);
    try {
      const reply = await api.chat(message, {
        conversationId,
        ticket: verified,
      });
      if (generation !== epoch.current) return;
      setConversationId(reply.conversation_id);
      if (verified && !reply.ticket_verified) setVerified(null);
      push({
        from: "bot",
        text: reply.reply,
        offer: reply.action === "request" ? reply.service : null,
        status: reply.ticket ?? undefined,
        sources: reply.sources,
      });
      setSuggestions(reply.suggestions);
      if (reply.action === "track")
        setForm({
          kind: "track",
          ticketNumber: reply.ticket_number ?? "",
          messageId: nextId.current - 1,
        });
    } catch {
      if (generation !== epoch.current) return;
      push({
        from: "bot",
        text: "I couldn't reach our team just now. Please use the callback form on this page, or try again in a moment.",
      });
      setSuggestions(STARTERS);
    } finally {
      if (generation === epoch.current) {
        busy.current = false;
        setThinking(false);
      }
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

  function clear() {
    epoch.current++;
    busy.current = false;
    setThinking(false);
    setMessages([WELCOME]);
    setConversationId(null);
    setVerified(null);
    setForm(null);
    setSuggestions(STARTERS);
    setInput("");
  }
  return {
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
    clear,
  };
}
const Context = createContext<ReturnType<typeof useCore> | null>(null);
export function AssistantProvider({ children }: { children: ReactNode }) {
  const value = useCore();
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useAssistant() {
  const value = useContext(Context);
  if (!value) throw Error("AssistantProvider is required");
  return value;
}
