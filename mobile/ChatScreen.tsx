import { useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, type ScrollViewInstance, StyleSheet, Text, TextInput, View } from "react-native";
import type { ChatReply, ChatTicket, Service, TicketStatus } from "@homexo/shared";
import { api, colors } from "./theme";

type Message =
  | { id: number; from: "user"; text: string }
  | { id: number; from: "bot"; text: string; offer?: Service | null; status?: TicketStatus; sources?: ChatReply["sources"]; askTicket?: string };

const STARTERS = ["Is this property safe to buy?", "Package prices", "Track my request"];
const WELCOME: Message = {
  id: 0,
  from: "bot",
  text: "Hi! I'm the Homexo Legal assistant. Ask me about packages, title checks, registration or documents. I can also raise a callback request or track one for you.",
};

export function ChatScreen({ visible, onClose, onRequest }: {
  visible: boolean;
  onClose: () => void;
  onRequest: (service: Service, conversationId: string | null) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [suggestions, setSuggestions] = useState(STARTERS);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  // The saved conversation on the server and the ticket the customer verified in it.
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [verified, setVerified] = useState<ChatTicket | null>(null);
  const nextId = useRef(1);
  const scrollRef = useRef<ScrollViewInstance>(null);

  function push(message: Omit<Extract<Message, { from: "bot" }>, "id"> | Omit<Extract<Message, { from: "user" }>, "id">) {
    const id = nextId.current++;
    setMessages((prev) => [...prev, { ...message, id } as Message]);
  }

  function updateStatus(id: number, status: TicketStatus) {
    setMessages((prev) => prev.map((m) => (m.id === id && m.from === "bot" ? { ...m, status } : m)));
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || thinking) return;
    setInput("");
    setSuggestions([]);
    push({ from: "user", text: message });
    setThinking(true);
    try {
      const reply = await api.chat(message, { conversationId, ticket: verified });
      setConversationId(reply.conversation_id);
      if (verified && !reply.ticket_verified) setVerified(null);
      push({
        from: "bot",
        text: reply.reply,
        offer: reply.action === "request" ? reply.service : null,
        status: reply.ticket ?? undefined,
        sources: reply.sources,
        askTicket: reply.action === "track" ? reply.ticket_number ?? "" : undefined,
      });
      setSuggestions(reply.suggestions);
    } catch (error) {
      push({ from: "bot", text: error instanceof Error && /quickly/.test(error.message) ? error.message : "I couldn't reach our team just now. Please try again in a moment." });
      setSuggestions(STARTERS);
    } finally {
      setThinking(false);
    }
  }

  return (
    <KeyboardAvoidingView style={[styles.screen, !visible && { display: "none" }]} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.head}>
        <Pressable onPress={onClose} hitSlop={12}><Text style={styles.link}>← Home</Text></Pressable>
        <Text style={styles.headTitle}>Homexo Legal assistant</Text>
      </View>
      <ScrollView ref={scrollRef} contentContainerStyle={styles.log} keyboardShouldPersistTaps="handled" onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
        {messages.map((m) => (
          <View key={m.id} style={m.from === "user" ? styles.userRow : styles.botRow}>
            <View style={m.from === "user" ? styles.userBubble : styles.botBubble}>
              <Text style={m.from === "user" ? styles.userText : styles.botText}>{m.text}</Text>
            </View>
            {m.from === "bot" && m.sources && m.sources.length > 0 && <Text style={styles.sources}>From: {m.sources.map((s) => s.section).join(" · ")}</Text>}
            {m.from === "bot" && m.offer && (
              <Pressable style={styles.action} onPress={() => onRequest(m.offer!, conversationId)}>
                <Text style={styles.actionText}>Request a callback for {m.offer.name} →</Text>
              </Pressable>
            )}
            {m.from === "bot" && m.askTicket !== undefined && !m.status && (
              <TrackForm
                ticketNumber={m.askTicket}
                onDone={(status, contact) => {
                  setVerified({ ticket_number: status.ticket_number, contact });
                  updateStatus(m.id, status);
                  setSuggestions(["What's happening with my request?", "What do you need from me?"]);
                }}
              />
            )}
            {m.from === "bot" && m.status && (
              <StatusCard ticket={m.status} contact={verified?.ticket_number === m.status.ticket_number ? verified.contact : undefined} onUpdate={(status) => updateStatus(m.id, status)} />
            )}
          </View>
        ))}
        {thinking && <ActivityIndicator color={colors.green} style={{ alignSelf: "flex-start", margin: 8 }} />}
      </ScrollView>
      {suggestions.length > 0 && (
        <ScrollView horizontal style={styles.suggestions} contentContainerStyle={{ gap: 8, paddingHorizontal: 12 }} keyboardShouldPersistTaps="handled" showsHorizontalScrollIndicator={false}>
          {suggestions.map((s) => (
            <Pressable key={s} style={styles.chip} onPress={() => send(s)}><Text style={styles.chipText}>{s}</Text></Pressable>
          ))}
        </ScrollView>
      )}
      <View style={styles.inputRow}>
        <TextInput style={styles.input} value={input} onChangeText={setInput} placeholder="Ask about your property…" placeholderTextColor="#9aa59f" maxLength={1000} onSubmitEditing={() => send(input)} returnKeyType="send" />
        <Pressable style={[styles.send, (!input.trim() || thinking) && { opacity: 0.5 }]} onPress={() => send(input)} disabled={!input.trim() || thinking}>
          <Text style={styles.sendText}>↑</Text>
        </Pressable>
      </View>
      <Text style={styles.note}>Chats are saved so our team can follow up on your request. A specialist confirms scope and fees on the call.</Text>
    </KeyboardAvoidingView>
  );
}

function TrackForm({ ticketNumber, onDone }: { ticketNumber: string; onDone: (status: TicketStatus, contact: string) => void }) {
  const [ticket, setTicket] = useState(ticketNumber);
  const [contact, setContact] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setError("");
    setLoading(true);
    try {
      onDone(await api.lookupTicket(ticket.trim(), contact.trim()), contact.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not check that request.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.card}>
      <TextInput style={styles.input} value={ticket} onChangeText={setTicket} placeholder="Ticket number, e.g. HX-261018-ABC123" placeholderTextColor="#9aa59f" autoCapitalize="characters" />
      <TextInput style={styles.input} value={contact} onChangeText={setContact} placeholder="Phone or email you used" placeholderTextColor="#9aa59f" autoCapitalize="none" />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable style={[styles.button, loading && { opacity: 0.6 }]} onPress={submit} disabled={loading || !ticket.trim() || !contact.trim()}>
        <Text style={styles.buttonText}>{loading ? "Checking…" : "Check status"}</Text>
      </Pressable>
    </View>
  );
}

function StatusCard({ ticket, contact, onUpdate }: { ticket: TicketStatus; contact?: string; onUpdate: (ticket: TicketStatus) => void }) {
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  async function sendReply() {
    if (!contact || !reply.trim()) return;
    setError("");
    setSending(true);
    try {
      onUpdate(await api.replyToTicket(ticket.ticket_number, contact, reply.trim()));
      setReply("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send your message.");
    } finally {
      setSending(false);
    }
  }

  return (
    <View style={styles.card}>
      <Text style={styles.tag}>TICKET {ticket.ticket_number}</Text>
      <Text style={styles.status}>{ticket.status_label}</Text>
      <Text style={styles.muted}>{ticket.service_name}{ticket.package ? ` · ${ticket.package}` : ""}</Text>
      {ticket.history.slice(-3).map((e) => (
        <Text key={`${e.status}-${e.at}`} style={styles.muted}>• {e.label}{e.note ? `: ${e.note}` : ""}</Text>
      ))}
      {ticket.messages.map((m, i) => (
        <View key={i} style={m.from === "you" ? styles.fromYou : styles.fromTeam}>
          <Text style={styles.tiny}>{m.from === "you" ? "You" : "Homexo case team"}</Text>
          <Text style={styles.botText}>{m.message}</Text>
        </View>
      ))}
      {contact && ticket.can_reply && (
        <>
          <TextInput style={[styles.input, { minHeight: 70, textAlignVertical: "top" }]} value={reply} onChangeText={setReply} placeholder="Message the case team" placeholderTextColor="#9aa59f" multiline maxLength={4000} />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable style={[styles.button, (sending || !reply.trim()) && { opacity: 0.6 }]} onPress={sendReply} disabled={sending || !reply.trim()}>
            <Text style={styles.buttonText}>{sending ? "Sending…" : "Send message"}</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cream },
  head: { padding: 16, paddingBottom: 12, gap: 4, borderBottomWidth: 1, borderColor: colors.line },
  headTitle: { fontSize: 18, fontWeight: "700", color: colors.ink },
  link: { fontSize: 13, fontWeight: "800", color: colors.green },
  log: { padding: 14, gap: 12 },
  userRow: { alignItems: "flex-end" },
  botRow: { alignItems: "flex-start", gap: 6 },
  userBubble: { maxWidth: "85%", backgroundColor: colors.greenDark, borderRadius: 14, borderBottomRightRadius: 4, padding: 11 },
  botBubble: { maxWidth: "88%", backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line, borderRadius: 14, borderBottomLeftRadius: 4, padding: 11 },
  userText: { color: colors.white, fontSize: 14, lineHeight: 20 },
  botText: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  sources: { fontSize: 11, color: colors.muted, paddingLeft: 4 },
  action: { backgroundColor: "#eef5e7", borderWidth: 1, borderColor: "#d8e7c8", borderRadius: 10, padding: 10 },
  actionText: { color: colors.green, fontSize: 13, fontWeight: "800" },
  card: { alignSelf: "stretch", backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line, borderRadius: 12, padding: 12, gap: 8 },
  tag: { fontSize: 10, fontWeight: "800", letterSpacing: 1.2, color: colors.green },
  status: { fontSize: 16, fontWeight: "700", color: colors.ink },
  muted: { fontSize: 12, lineHeight: 18, color: colors.muted },
  tiny: { fontSize: 10, color: colors.muted },
  fromTeam: { backgroundColor: "#eef5e7", borderRadius: 10, padding: 9 },
  fromYou: { backgroundColor: colors.cream, borderRadius: 10, padding: 9, alignSelf: "flex-end", maxWidth: "90%" },
  suggestions: { flexGrow: 0, paddingVertical: 8 },
  chip: { borderWidth: 1, borderColor: "#dce4da", borderRadius: 20, paddingVertical: 8, paddingHorizontal: 12, backgroundColor: colors.white },
  chipText: { fontSize: 13, color: colors.ink },
  inputRow: { flexDirection: "row", gap: 8, paddingHorizontal: 12, paddingTop: 4 },
  input: { flex: 1, backgroundColor: colors.white, borderWidth: 1, borderColor: "#dce4da", borderRadius: 8, padding: 11, fontSize: 14, color: colors.ink },
  send: { backgroundColor: colors.green, borderRadius: 8, paddingHorizontal: 16, justifyContent: "center" },
  sendText: { color: colors.white, fontSize: 18, fontWeight: "700" },
  button: { backgroundColor: colors.green, borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  buttonText: { color: colors.white, fontSize: 14, fontWeight: "700" },
  error: { color: colors.danger, fontSize: 12 },
  note: { fontSize: 10, lineHeight: 15, color: "#7e8c83", paddingHorizontal: 12, paddingTop: 6, paddingBottom: 12 },
});
