import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Linking, Platform, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { ApiError, COURIER_STATUS_LABELS, paymentLabel, type AccountOverview, type AccountRequest, type CustomerMeeting, type LoginCodeSent, type TicketStatus } from "@homexo/shared";
import { expireSession, signIn, signOut, updateProfile, useSession, type Session } from "./accountStore";
import { saveBookingRef } from "./bookingsStore";
import { Field, styles } from "./LawyersScreen";
import { ui } from "./lawyerUi";
import { api, colors } from "./theme";
import { CaseProgressPanel } from "./CaseProgressPanel";
import { CaseDocuments } from "./CaseDocuments";

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

  const [query, setQuery] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const term = query.trim().toLowerCase();
  const requests = data?.requests ?? [];
  const matches = requests.filter((request) =>
    (!attentionOnly || request.needs_you) &&
    [request.ticket_number, request.service_name, request.title].some(
      (value) => value?.toLowerCase().includes(term),
    ),
  );

  const matchingTickets = new Set(matches.map((request) => request.ticket_number));

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
          <UpcomingMeetings data={data} />
          {data.requests.length === 0 && <View style={styles.card}><Text style={styles.body}>Nothing on this number yet. Requests and consultations you make show up here.</Text></View>}
          {requests.length > 0 && (
            <View style={styles.card}>
              <Field label="Search requests" placeholder="Ticket number, service or title" value={query} onChangeText={setQuery} />
              <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: attentionOnly }}
                onPress={() => setAttentionOnly(!attentionOnly)}>
                <Text style={styles.link}>{attentionOnly ? "☑" : "☐"} Needs your attention</Text>
              </Pressable>
              <Text style={ui.muted}>{matches.length === 0 ? "No matching requests." : `${matches.length} ${matches.length === 1 ? "request" : "requests"}`}</Text>
              {(query.length > 0 || attentionOnly) && (
                <Pressable accessibilityRole="button" onPress={() => { setQuery(""); setAttentionOnly(false); }}>
                  <Text style={styles.link}>Clear filters</Text>
                </Pressable>
              )}
            </View>
          )}
          {requests.filter((r) => matchingTickets.has(r.ticket_number) || r.ticket_number === open).map((r) => (
            <View key={r.ticket_number} style={!matchingTickets.has(r.ticket_number) && { display: "none" }}>
            <RequestCard request={r} token={session.token} contact={data.profile.contact} expanded={open === r.ticket_number}
              onToggle={() => (r.kind === "consultation" ? onOpenBookings() : setOpen(open === r.ticket_number ? null : r.ticket_number))} />
            </View>
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

function UpcomingMeetings({ data }: { data: AccountOverview }) {
  const [now, setNow] = useState(Date.now);
  const [failedId, setFailedId] = useState<string | null>(null);
  const byId = new Map<string, CustomerMeeting>();
  for (const request of data.requests) {
    if (request.next_meeting) byId.set(request.next_meeting.id, request.next_meeting);
  }
  for (const booking of data.bookings) byId.set(booking.meeting.id, booking.meeting);
  const meetings = [...byId.values()]
    .filter((meeting) => meeting.status === "scheduled" && Date.parse(meeting.ends_at) > now)
    .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));

  useEffect(() => {
    if (!meetings.length) return;
    const timer = setInterval(() => setNow(Date.now()), 10000);
    return () => clearInterval(timer);
  }, [meetings.length]);

  async function join(meeting: CustomerMeeting) {
    const time = Date.now();
    setNow(time);
    if (!meeting.meet_link || time < Date.parse(meeting.starts_at) - 15 * 60000 || time >= Date.parse(meeting.ends_at)) return;
    setFailedId(null);
    try {
      await Linking.openURL(meeting.meet_link);
    } catch {
      setFailedId(meeting.id);
    }
  }

  if (!meetings.length) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Upcoming meetings</Text>
      {meetings.map((meeting) => (
        <View key={meeting.id} style={{ gap: 4 }}>
          <Text style={styles.label}>{meeting.title || "Consultation"}</Text>
          <Text style={ui.muted}>{meeting.when}{meeting.lawyer_name ? ` · ${meeting.lawyer_name}` : ""}</Text>
          {meeting.meet_link && now >= Date.parse(meeting.starts_at) - 15 * 60000 ? (
            <Pressable accessibilityRole="button" onPress={() => join(meeting)}>
              <Text style={styles.link}>Join meeting</Text>
            </Pressable>
          ) : <Text style={ui.muted}>{meeting.meet_link ? "Joining opens 15 minutes before the meeting." : "Meeting link pending."}</Text>}
          {failedId === meeting.id && <Text style={ui.error}>Could not open the meeting link. Tap Join meeting to retry.</Text>}
        </View>
      ))}
    </View>
  );
}

function PreliminaryReport({ report }: { report: NonNullable<TicketStatus["report"]> }) {
  const [expanded, setExpanded] = useState(false);
  const sections = report.sections.filter((section) => section.text.trim());
  if (!sections.length) return null;

  return (
    <View style={{ gap: 6 }}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(!expanded)}>
        <Text style={styles.link}>{expanded ? "Hide preliminary report" : "Read preliminary report"}</Text>
      </Pressable>
      {expanded && (
        <View style={{ gap: 8 }}>
          {report.lawyer_name && <Text style={ui.muted}>Prepared by {report.lawyer_name}</Text>}
          {report.issued_at && <Text style={ui.muted}>Issued {dateFormat.format(new Date(report.issued_at))}</Text>}
          {sections.map((section) => (
            <View key={section.key}>
              <Text accessibilityRole="header" style={styles.label}>{section.heading}</Text>
              <Text selectable style={styles.body}>{section.text}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function RequestCard({ request: r, token, contact, expanded, onToggle }: { request: AccountRequest; token: string; contact: string; expanded: boolean; onToggle: () => void }) {
  const [detail, setDetail] = useState<TicketStatus | null>(null);
  const [detailError, setDetailError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const submitting = useRef(false);

  async function sendReply() {
    const message = draft.trim();
    if (!detail?.can_reply || !message || submitting.current) return;
    submitting.current = true;
    setSending(true);
    setReplyError("");
    try {
      const updated = await api.replyToTicket(r.ticket_number, contact, message);
      setDetail(updated);
      setDraft("");
    } catch (error) {
      setReplyError(error instanceof ApiError ? error.message : "Could not confirm delivery. Reopen this case to check the conversation before retrying.");
    } finally {
      submitting.current = false;
      setSending(false);
    }
  }

  useEffect(() => {
    if (!expanded) return;
    setDetail(null);
    setDetailError("");
    let active = true;
    api.getAccountRequest(token, r.ticket_number).then((next) => {
      if (active) {
        setDetail(next);
        setDetailError("");
      }
    }).catch(() => {
      if (active) setDetailError("Could not refresh this request. Close it and open it again to retry.");
    });
    return () => { active = false; };
  }, [expanded, token, r.ticket_number]);

  return (
    <View style={styles.card}>
      <Pressable onPress={onToggle} disabled={sending} accessibilityRole="button" accessibilityState={{ expanded }}>
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
      <Text style={styles.link}>{r.kind === "consultation" ? "Manage in My bookings →" : expanded ? "Hide details" : "Show details"}</Text>
      </Pressable>
      {expanded && detailError && <Text style={ui.error}>{detailError}</Text>}
      {expanded && (detail ? (
        <View style={{ gap: 6, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 10 }}>
          {detail.progress && <CaseProgressPanel progress={detail.progress} />}
          {detail.report && <PreliminaryReport report={detail.report} />}
          {detail.courier !== undefined && (
            <View>
              <Text style={styles.label}>Courier tracking</Text>
              {detail.courier ? (
                <>
                  <Text style={styles.body}>{COURIER_STATUS_LABELS[detail.courier.status]} · {detail.courier.carrier}</Text>
                  <Text style={styles.body}>Tracking number {detail.courier.tracking_number}</Text>
                  <Text style={ui.muted}>Updated {dateFormat.format(new Date(detail.courier.updated_at))}</Text>
                </>
              ) : <Text style={ui.muted}>No dispatch has been recorded yet.</Text>}
            </View>
          )}
          {detail.history.map((h, i) => (
            <View key={i}><Text style={styles.label}>{h.label}</Text>{h.note ? <Text style={ui.muted}>{h.note}</Text> : null}</View>
          ))}
          <Text accessibilityRole="header" style={styles.label}>Case messages</Text>
          {detail.messages.length > 3 && (
            <Pressable accessibilityRole="button" onPress={() => setShowHistory(!showHistory)}>
              <Text style={styles.link}>{showHistory ? "Show recent messages" : "Show earlier messages"}</Text>
            </Pressable>
          )}
          {(showHistory ? detail.messages : detail.messages.slice(-3)).map((m, i) => (
            <Text key={`m${i}`} style={ui.muted}><Text style={styles.label}>{m.from === "you" ? "You: " : "Homexo: "}</Text>{m.message}</Text>
          ))}
          {detail.can_reply && (
            <View style={{ gap: 8 }}>
              <TextInput multiline maxLength={4000} editable={!sending} value={draft}
                accessibilityLabel="Message to your case team" placeholder="Message your case team"
                onChangeText={setDraft} style={styles.input} />
              {replyError ? <Text accessibilityLiveRegion="polite" style={ui.error}>{replyError}</Text> : null}
              <Pressable accessibilityRole="button" disabled={sending || !draft.trim()} onPress={sendReply}
                style={[styles.button, (sending || !draft.trim()) && { opacity: 0.5 }]}>
                <Text style={styles.buttonText}>{sending ? "Sending…" : "Send reply"}</Text>
              </Pressable>
            </View>
          )}
          <CaseDocuments ticket={detail} contact={contact} onUpdate={setDetail} />
        </View>
      ) : !detailError && <ActivityIndicator color={colors.green} />)}
    </View>
  );
}

function Profile({ session }: { session: Session }) {
  const { profile } = session;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(profile.name ?? "");
  const [email, setEmail] = useState(profile.email ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [signOutError, setSignOutError] = useState("");

  async function endSessions(all: boolean) {
    if (busy) return;
    setBusy(true);
    setSignOutError("");
    try {
      if (all) await api.signOutEverywhere(session.token);
      else await api.revokeCurrentCustomerSession(session.token);
      expireSession(session.token);
    } catch (e) {
      setSignOutError(e instanceof ApiError ? e.message : "Could not confirm sign-out. Please try again.");
    } finally {
      setBusy(false);
    }
  }

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
      {signOutError ? <Text style={ui.error}>{signOutError}</Text> : null}
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 6 }}>
        <Pressable onPress={() => endSessions(false)} disabled={busy} hitSlop={8}><Text style={styles.link}>Sign out</Text></Pressable>
        <Pressable onPress={() => endSessions(true)} disabled={busy} hitSlop={8}><Text style={[styles.link, { color: colors.danger }]}>Sign out on all devices</Text></Pressable>
      </View>
    </View>
  );
}
