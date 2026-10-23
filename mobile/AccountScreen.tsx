import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { ApiError, paymentLabel, type AccountOverview, type AccountRequest, type LoginCodeSent, type TicketStatus } from "@homexo/shared";
import { signIn, signOut, updateProfile, useSession, type Session } from "./accountStore";
import { saveBookingRef } from "./bookingsStore";
import { Field, styles } from "./LawyersScreen";
import { ui } from "./lawyerUi";
import { api, colors } from "./theme";

const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export function AccountScreen({ onOpenBookings }: { onOpenBookings: () => void }) {
  const session = useSession();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      {session === undefined ? <ActivityIndicator color={colors.green} style={{ marginTop: 40 }} />
        : session ? <Overview session={session} onOpenBookings={onOpenBookings} />
        : (
          <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
            <Text style={styles.title}>Your account</Text>
            <Text style={styles.body}>Sign in with your phone to see every request, consultation and payment made with your number, on the website or in the app.</Text>
            <SignIn />
          </ScrollView>
        )}
    </KeyboardAvoidingView>
  );
}

function SignIn() {
  const [phone, setPhone] = useState("");
  const [sent, setSent] = useState<LoginCodeSent | null>(null);
  const [code, setCode] = useState("");
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  async function sendCode() {
    setError("");
    setBusy(true);
    try {
      const result = await api.startLogin(phone.trim());
      setSent(result);
      setWait(result.resend_after);
      setCode("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't send a code.");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setError("");
    setBusy(true);
    try {
      signIn(await api.verifyLogin(phone.trim(), code.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "That code didn't work.");
      setBusy(false);
    }
  }

  const ready = sent ? code.length === 6 : phone.replace(/\D/g, "").length >= 10;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Sign in with your phone</Text>
      {!sent ? (
        <Field label="Mobile number" value={phone} onChangeText={setPhone} placeholder="98765 43210" keyboardType="phone-pad" autoComplete="tel" />
      ) : (
        <>
          <View style={styles.summary}>
            <Text style={ui.muted}>{sent.channel === "whatsapp" ? `We sent a 6-digit code to ${sent.phone} on WhatsApp.` : `Test mode: no WhatsApp is set up, so your code is ${sent.dev_code}.`}</Text>
          </View>
          <Field label="6-digit code" value={code} onChangeText={(v) => setCode(v.replace(/\D/g, "").slice(0, 6))} placeholder="123456" keyboardType="number-pad" autoComplete="sms-otp" />
        </>
      )}
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <Pressable style={[styles.button, (busy || !ready) && { opacity: 0.5 }]} disabled={busy || !ready} onPress={sent ? verify : sendCode}>
        <Text style={styles.buttonText}>{busy ? "Please wait…" : sent ? "Sign in" : "Send code"}</Text>
      </Pressable>
      {sent && (
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Pressable onPress={() => { setSent(null); setError(""); }} hitSlop={8}><Text style={styles.link}>Change number</Text></Pressable>
          <Pressable onPress={sendCode} disabled={wait > 0 || busy} hitSlop={8}><Text style={[styles.link, wait > 0 && { color: colors.muted }]}>{wait > 0 ? `Resend in ${wait}s` : "Send a new code"}</Text></Pressable>
        </View>
      )}
    </View>
  );
}

function Overview({ session, onOpenBookings }: { session: Session; onOpenBookings: () => void }) {
  const [data, setData] = useState<AccountOverview | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const overview = await api.getAccount(session.token);
      setData(overview);
      updateProfile(overview.profile);
      // My bookings lists the refs kept on this phone, so add the account's consultations.
      [...overview.bookings].reverse().forEach((b) => saveBookingRef({ ticket_number: b.ticket_number, contact: overview.profile.contact }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) signOut();
      else setError(e instanceof Error ? e.message : "We couldn't load your account.");
    }
  }, [session.token]);
  useEffect(() => { load(); }, [load]);

  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  const { profile } = session;
  return (
    <ScrollView contentContainerStyle={styles.page} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.green} />}>
      <Text style={styles.title}>{profile.name ? `Hello, ${profile.name.split(" ")[0]}` : "Your account"}</Text>
      <Text style={styles.body}>Requests, consultations and payments made with {profile.phone}.</Text>
      {error ? (
        <View style={styles.card}>
          <Text style={ui.error}>{error}</Text>
          <Pressable style={styles.button} onPress={load}><Text style={styles.buttonText}>Try again</Text></Pressable>
        </View>
      ) : !data ? <ActivityIndicator color={colors.green} /> : (
        <>
          {data.requests.length === 0 && <View style={styles.card}><Text style={styles.body}>Nothing on this number yet. Requests and consultations you make show up here.</Text></View>}
          {data.requests.map((r) => (
            <RequestCard key={r.ticket_number} request={r} token={session.token} expanded={open === r.ticket_number}
              onToggle={() => (r.kind === "consultation" ? onOpenBookings() : setOpen(open === r.ticket_number ? null : r.ticket_number))} />
          ))}
          {data.payments.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Payments</Text>
              {data.payments.map((p) => (
                <View key={p.ticket_number} style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>{p.description}</Text>
                    <Text style={ui.muted}>{p.when}{p.reference ? ` · Ref ${p.reference}` : ""}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.label}>{paymentLabel(p)}</Text>
                    {p.can_pay && <Pressable onPress={onOpenBookings}><Text style={styles.link}>Pay now</Text></Pressable>}
                  </View>
                </View>
              ))}
            </View>
          )}
        </>
      )}
      <Profile session={session} />
    </ScrollView>
  );
}

function RequestCard({ request: r, token, expanded, onToggle }: { request: AccountRequest; token: string; expanded: boolean; onToggle: () => void }) {
  const [detail, setDetail] = useState<TicketStatus | null>(null);
  useEffect(() => {
    if (expanded && !detail) api.getAccountRequest(token, r.ticket_number).then(setDetail).catch(() => undefined);
  }, [expanded, detail, token, r.ticket_number]);

  return (
    <Pressable style={styles.card} onPress={onToggle} accessibilityRole="button" accessibilityState={{ expanded }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>{r.kind === "consultation" ? r.title : r.service_name}</Text>
          <Text style={ui.muted}>{r.ticket_number} · {dateFormat.format(new Date(r.created_at))}</Text>
        </View>
        <Text style={ui.tagText}>{r.status_label}</Text>
      </View>
      {r.next_meeting && <Text style={styles.next}>Meeting {r.next_meeting.when}</Text>}
      {r.report && <Text style={ui.muted}>{r.report.status_label}{r.report.signed ? "" : ` · ${r.report.progress.done} of ${r.report.progress.total} done`}</Text>}
      {r.needs_you && <Text style={[styles.label, { color: "#8a6420" }]}>{r.needs_you}</Text>}
      {expanded && (detail ? (
        <View style={{ gap: 6, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 10 }}>
          {detail.history.map((h, i) => (
            <View key={i}><Text style={styles.label}>{h.label}</Text>{h.note ? <Text style={ui.muted}>{h.note}</Text> : null}</View>
          ))}
          {detail.messages.slice(-3).map((m, i) => (
            <Text key={`m${i}`} style={ui.muted}><Text style={styles.label}>{m.from === "you" ? "You: " : "Homexo: "}</Text>{m.message}</Text>
          ))}
          {r.documents > 0 && <Text style={ui.muted}>{r.documents} document{r.documents === 1 ? "" : "s"} on file. Upload and download them on the website under My documents.</Text>}
        </View>
      ) : <ActivityIndicator color={colors.green} />)}
      <Text style={styles.link}>{r.kind === "consultation" ? "Manage in My bookings →" : expanded ? "Hide details" : "Show details"}</Text>
    </Pressable>
  );
}

function Profile({ session }: { session: Session }) {
  const { profile } = session;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(profile.name ?? "");
  const [email, setEmail] = useState(profile.email ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setBusy(true);
    setError("");
    try {
      updateProfile(await api.updateAccount(session.token, { full_name: name.trim() || undefined, email: email.trim() }));
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't save that.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Your details</Text>
      {editing ? (
        <>
          <Field label="Name" value={name} onChangeText={setName} placeholder="Full name" autoComplete="name" />
          <Field label="Email" value={email} onChangeText={setEmail} placeholder="you@example.com" keyboardType="email-address" autoComplete="email" />
          {error ? <Text style={ui.error}>{error}</Text> : null}
          <Pressable style={[styles.button, busy && { opacity: 0.5 }]} disabled={busy} onPress={save}><Text style={styles.buttonText}>{busy ? "Saving…" : "Save"}</Text></Pressable>
          <Pressable onPress={() => setEditing(false)}><Text style={styles.link}>Cancel</Text></Pressable>
        </>
      ) : (
        <>
          <Text style={styles.body}>{profile.name || "No name added"}{"\n"}{profile.phone}{"\n"}{profile.email || "No email added"}</Text>
          <Pressable onPress={() => { setName(profile.name ?? ""); setEmail(profile.email ?? ""); setEditing(true); }}><Text style={styles.link}>Edit details</Text></Pressable>
        </>
      )}
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 6 }}>
        <Pressable onPress={signOut} hitSlop={8}><Text style={styles.link}>Sign out</Text></Pressable>
        <Pressable onPress={() => api.signOutEverywhere(session.token).finally(signOut)} hitSlop={8}><Text style={[styles.link, { color: colors.danger }]}>Sign out on all devices</Text></Pressable>
      </View>
    </View>
  );
}
