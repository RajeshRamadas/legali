import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import {
  PROPERTY_TYPES,
  type PropertyType,
  type Service,
} from "@homexo/shared";

import { ChatScreen } from "./ChatScreen";
import { api, colors } from "./theme";

const emptyForm = { name: "", contact: "", propertyType: "apartment" as PropertyType, location: "", description: "" };

export default function App() {
  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
        <StatusBar style="dark" />
        <HomeScreen />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

function HomeScreen() {
  const [services, setServices] = useState<Service[]>([]);
  const [loadError, setLoadError] = useState("");
  const [selected, setSelected] = useState<{ service: Service; conversationId?: string | null } | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  async function loadServices() {
    setLoadError("");
    try {
      setServices(await api.listServices());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not load services.");
    }
  }

  useEffect(() => {
    loadServices();
  }, []);

  // The chat stays mounted while a request opened from it is on screen, so going back keeps the conversation.
  const chat = <ChatScreen visible={chatOpen && !selected} onClose={() => setChatOpen(false)} onRequest={(service, conversationId) => setSelected({ service, conversationId })} />;
  if (selected) return <>{chat}<RequestScreen service={selected.service} conversationId={selected.conversationId} onBack={() => setSelected(null)} /></>;
  if (chatOpen) return chat;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.brand}>homexo<Text style={{ color: colors.green }}>.</Text></Text>
      <Text style={styles.title}>Property services, <Text style={{ color: colors.green }}>made simpler.</Text></Text>
      <Text style={styles.body}>Choose a service to start a request. Our team reviews scope and availability.</Text>
      <Pressable style={styles.button} onPress={() => setChatOpen(true)}>
        <Text style={styles.buttonText}>Ask the assistant or track a request</Text>
      </Pressable>

      {loadError ? (
        <View style={styles.card}>
          <Text style={[styles.body, { color: colors.danger }]}>Couldn’t reach Homexo: {loadError}</Text>
          <Pressable style={styles.button} onPress={loadServices}><Text style={styles.buttonText}>Try again</Text></Pressable>
        </View>
      ) : services.length === 0 ? (
        <ActivityIndicator color={colors.green} style={{ marginTop: 32 }} />
      ) : (
        services.map((service) => (
          <Pressable key={service.slug} style={styles.card} onPress={() => setSelected({ service })}>
            <Text style={styles.tag}>{service.category.toUpperCase()}</Text>
            <Text style={styles.cardTitle}>{service.name}</Text>
            <Text style={styles.body}>{service.description}</Text>
            <Text style={styles.link}>Request this service →</Text>
          </Pressable>
        ))
      )}
    </ScrollView>
  );
}

function RequestScreen({ service, conversationId, onBack }: { service: Service; conversationId?: string | null; onBack: () => void }) {
  const [form, setForm] = useState({
    ...emptyForm,
    propertyType: service.property_types[0] ?? emptyForm.propertyType,
  });
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);

  const propertyTypes = PROPERTY_TYPES.filter((p) => service.property_types.includes(p.value));

  async function submit() {
    setNotice("");
    setSending(true);
    try {
      const data = await api.createTicket({
        customer_name: form.name,
        contact: form.contact,
        property_type: form.propertyType,
        service_slug: service.slug,
        location: form.location,
        description: form.description,
        source: "mobile",
        conversation_id: conversationId,
      });
      setNotice(`Request received. Your ticket number is ${data.ticket_number}. Save it to track your request in the assistant.`);
      setForm({ ...form, name: "", contact: "", location: "", description: "" });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not connect to Homexo. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <Pressable onPress={onBack} hitSlop={12}><Text style={styles.link}>{conversationId ? "← Back to the chat" : "← All services"}</Text></Pressable>
        <Text style={styles.tag}>HOMEXO REQUEST</Text>
        <Text style={styles.title}>{service.name}</Text>

        <Field label="Your name" value={form.name} onChangeText={(name) => setForm({ ...form, name })} placeholder="Full name" />
        <Field label="Email or phone" value={form.contact} onChangeText={(contact) => setForm({ ...form, contact })} placeholder="How can we reach you?" />

        <Text style={styles.label}>Property type</Text>
        <View style={styles.chips}>
          {propertyTypes.map((p) => (
            <Pressable
              key={p.value}
              onPress={() => setForm({ ...form, propertyType: p.value })}
              style={[styles.chip, form.propertyType === p.value && styles.chipActive]}
            >
              <Text style={[styles.chipText, form.propertyType === p.value && styles.chipTextActive]}>{p.label}</Text>
            </Pressable>
          ))}
        </View>

        <Field label="Property location" value={form.location} onChangeText={(location) => setForm({ ...form, location })} placeholder="City / locality" />
        <Field
          label="Briefly describe what you need"
          value={form.description}
          onChangeText={(description) => setForm({ ...form, description })}
          placeholder="For example, I need help with an EC for my apartment..."
          multiline
        />

        <Text style={styles.small}>Please don’t submit Aadhaar numbers, passwords, bank details or sensitive documents in this form.</Text>
        {notice ? <View style={styles.notice}><Text style={styles.noticeText}>{notice}</Text></View> : null}
        <Pressable style={[styles.button, sending && { opacity: 0.6 }]} onPress={submit} disabled={sending}>
          <Text style={styles.buttonText}>{sending ? "Submitting…" : "Submit request →"}</Text>
        </Pressable>
        <Text style={styles.small}>Submitting a request does not guarantee service acceptance, a government outcome or a legal conclusion.</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field(props: { label: string; value: string; onChangeText: (v: string) => void; placeholder: string; multiline?: boolean }) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={styles.label}>{props.label}</Text>
      <TextInput
        style={[styles.input, props.multiline && { minHeight: 90, textAlignVertical: "top" }]}
        value={props.value}
        onChangeText={props.onChangeText}
        placeholder={props.placeholder}
        placeholderTextColor="#9aa59f"
        multiline={props.multiline}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.cream },
  page: { padding: 20, gap: 14, paddingBottom: 48 },
  brand: { fontSize: 24, fontWeight: "800", color: colors.ink, letterSpacing: -1 },
  title: { fontSize: 30, fontWeight: "700", color: colors.ink, letterSpacing: -1, lineHeight: 36 },
  body: { fontSize: 14, lineHeight: 21, color: colors.muted },
  card: { backgroundColor: colors.white, borderRadius: 12, borderWidth: 1, borderColor: colors.line, padding: 18, gap: 6 },
  tag: { fontSize: 10, fontWeight: "800", letterSpacing: 1.5, color: colors.green },
  cardTitle: { fontSize: 18, fontWeight: "700", color: colors.ink },
  link: { fontSize: 13, fontWeight: "800", color: colors.green },
  label: { fontSize: 12, fontWeight: "700", color: "#43564d" },
  input: { backgroundColor: colors.white, borderWidth: 1, borderColor: "#dce4da", borderRadius: 8, padding: 12, fontSize: 14, color: colors.ink },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { borderWidth: 1, borderColor: "#dce4da", borderRadius: 20, paddingVertical: 8, paddingHorizontal: 12, backgroundColor: colors.white },
  chipActive: { backgroundColor: colors.green, borderColor: colors.green },
  chipText: { fontSize: 13, color: colors.ink },
  chipTextActive: { color: colors.white, fontWeight: "700" },
  button: { backgroundColor: colors.green, borderRadius: 8, paddingVertical: 15, alignItems: "center", marginTop: 4 },
  buttonText: { color: colors.white, fontSize: 15, fontWeight: "700" },
  small: { fontSize: 11, lineHeight: 17, color: "#7e8c83" },
  notice: { backgroundColor: "#eef5e7", borderWidth: 1, borderColor: "#d8e7c8", borderRadius: 8, padding: 12 },
  noticeText: { color: "#315c3e", fontSize: 13 },
});
