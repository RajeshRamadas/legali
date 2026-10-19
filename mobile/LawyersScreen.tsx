import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { formatFee, type Booking, type LawyerCard, type LawyerFilters, type LawyerProfile, type LawyerSearch, type LawyerSlot, type LawyerSort } from "@homexo/shared";
import { saveBookingRef } from "./bookingsStore";
import { Avatar, Rating, SlotPicker, Tags, forest, ui } from "./lawyerUi";
import { api, colors } from "./theme";

const SORTS: [LawyerSort, string][] = [["relevance", "Relevant"], ["soonest", "Soonest"], ["rating", "Top rated"], ["experience", "Experience"], ["fee_low", "Lowest fee"]];
const DAY_NAMES: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };

function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.chip, on && styles.chipOn]} accessibilityState={{ selected: on }}>
      <Text style={[styles.chipText, on && { color: colors.white }]}>{label}</Text>
    </Pressable>
  );
}

// Find a lawyer: search, filter and open a profile to book. onBooked shows the booking in My bookings.
export function LawyersScreen({ onBooked }: { onBooked: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<LawyerSearch>({ sort: "relevance" });
  const [filters, setFilters] = useState<LawyerFilters | null>(null);
  const [results, setResults] = useState<LawyerCard[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.lawyerFilters().then(setFilters).catch(() => setFilters(null));
  }, []);
  useEffect(() => {
    setError("");
    api.searchLawyers(search).then((r) => setResults(r.items)).catch((e) => setError(e instanceof Error ? e.message : "Could not load lawyers."));
  }, [search]);

  const set = (patch: Partial<LawyerSearch>) => setSearch((prev) => ({ ...prev, ...patch }));
  const toggle = <K extends keyof LawyerSearch>(key: K, value: LawyerSearch[K]) => set({ [key]: search[key] === value ? undefined : value } as Partial<LawyerSearch>);

  if (open) return <LawyerProfileScreen slug={open} onBack={() => setOpen(null)} onBooked={onBooked} />;

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Text style={styles.brand}>homexo<Text style={{ color: colors.green }}> legal</Text></Text>
      <Text style={styles.title}>Find a lawyer</Text>
      <Text style={styles.body}>Compare advocates and book a video consultation. The Google Meet link comes on WhatsApp.</Text>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.searchInput} value={query} onChangeText={setQuery} placeholder="Divorce, RERA, Jayanagar…" placeholderTextColor="#9aa59f"
          returnKeyType="search" onSubmitEditing={() => set({ q: query.trim() || undefined })} accessibilityLabel="Search lawyers"
        />
        <Pressable style={styles.searchButton} onPress={() => set({ q: query.trim() || undefined })}><Text style={styles.searchButtonText}>Search</Text></Pressable>
      </View>

      {filters && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {filters.specialisations.map((s) => <Chip key={s.value} label={s.value} on={search.specialisation === s.value} onPress={() => toggle("specialisation", s.value)} />)}
        </ScrollView>
      )}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        <Chip label="Available today" on={search.available === "today"} onPress={() => toggle("available", "today")} />
        <Chip label="Up to ₹1,000" on={search.max_fee === 1000} onPress={() => toggle("max_fee", 1000)} />
        <Chip label="10+ years" on={search.min_experience === 10} onPress={() => toggle("min_experience", 10)} />
        {filters?.languages.slice(0, 6).map((l) => <Chip key={l.value} label={l.value} on={search.language === l.value} onPress={() => toggle("language", l.value)} />)}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        <Text style={[ui.muted, { alignSelf: "center" }]}>Sort:</Text>
        {SORTS.map(([value, label]) => <Chip key={value} label={label} on={search.sort === value} onPress={() => set({ sort: value })} />)}
      </ScrollView>

      {error ? <Text style={ui.error}>{error}</Text> : null}
      {results === null ? <ActivityIndicator color={colors.green} style={{ marginTop: 24 }} /> : (
        <Text style={ui.muted}>{results.length} lawyer{results.length === 1 ? "" : "s"}{search.specialisation ? ` for ${search.specialisation}` : ""}</Text>
      )}
      {results?.length === 0 && <View style={styles.card}><Text style={styles.body}>No lawyers match these filters. Try clearing one.</Text></View>}
      {results?.map((lawyer) => (
        <Pressable key={lawyer.slug} style={styles.card} onPress={() => setOpen(lawyer.slug)} accessibilityRole="button" accessibilityLabel={`${lawyer.name}, ${lawyer.headline}`}>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Avatar initials={lawyer.initials} />
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.cardTitle}>{lawyer.name}</Text>
              <Text style={styles.body}>{lawyer.headline}</Text>
              <Text style={ui.muted}>{lawyer.experience_years} yrs · {lawyer.locality ?? lawyer.city} · {lawyer.languages.join(", ")}</Text>
              <Rating lawyer={lawyer} />
            </View>
          </View>
          <Tags items={lawyer.specialisations} />
          <View style={styles.cardFoot}>
            <View>
              <Text style={styles.fee}>{formatFee(lawyer.consultation_fee)}</Text>
              <Text style={[styles.next, !lawyer.next_available && { color: colors.muted }]}>
                {lawyer.next_available ? `Next: ${lawyer.next_available.day}, ${lawyer.next_available.label}` : "No open slots soon"}
              </Text>
            </View>
            <View style={styles.smallButton}><Text style={styles.smallButtonText}>{lawyer.next_available ? "Book" : "View"}</Text></View>
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );
}

function LawyerProfileScreen({ slug, onBack, onBooked }: { slug: string; onBack: () => void; onBooked: () => void }) {
  const [lawyer, setLawyer] = useState<LawyerProfile | null>(null);
  const [error, setError] = useState("");
  const [slot, setSlot] = useState<(LawyerSlot & { day: string }) | null>(null);
  const [form, setForm] = useState({ name: "", phone: "", email: "", issue: "" });
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState<Booking | null>(null);
  const [slotsKey, setSlotsKey] = useState(0);

  useEffect(() => {
    api.getLawyer(slug).then(setLawyer).catch((e) => setError(e instanceof Error ? e.message : "Could not load this lawyer."));
  }, [slug]);

  async function book() {
    if (!slot) return;
    setError("");
    setBusy(true);
    try {
      const booking = await api.bookLawyer(slug, {
        starts_at: slot.starts_at, customer_name: form.name.trim(), phone: form.phone.trim(),
        email: form.email.trim() || undefined, issue: form.issue.trim(), source: "mobile",
      });
      saveBookingRef({ ticket_number: booking.ticket_number, contact: form.phone.trim() });
      setBooked(booking);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not book. Please try again.");
      setSlot(null);
      setSlotsKey((k) => k + 1);
    } finally {
      setBusy(false);
    }
  }

  if (!lawyer) {
    return (
      <View style={styles.page}>
        <Pressable onPress={onBack} hitSlop={12}><Text style={styles.link}>← All lawyers</Text></Pressable>
        {error ? <Text style={ui.error}>{error}</Text> : <ActivityIndicator color={colors.green} style={{ marginTop: 24 }} />}
      </View>
    );
  }

  if (booked) {
    return (
      <ScrollView contentContainerStyle={[styles.page, { alignItems: "center" }]}>
        <View style={styles.tick}><Text style={{ fontSize: 28, color: "#24734d" }}>✓</Text></View>
        <Text style={[styles.title, { textAlign: "center" }]}>Consultation booked</Text>
        <Text style={[styles.body, { textAlign: "center" }]}>
          {booked.meeting.when} with {booked.lawyer.name}. Details are on their way to your WhatsApp{booked.meeting.meet_link ? ", with the Google Meet link" : ", and the meeting link follows before it starts"}.
        </Text>
        <View style={[styles.summary, { alignSelf: "stretch" }]}>
          <Text style={ui.muted}>Booking number</Text>
          <Text style={styles.summaryValue} selectable>{booked.ticket_number}</Text>
        </View>
        {booked.meeting.meet_link && <Pressable style={styles.button} onPress={() => Linking.openURL(booked.meeting.meet_link!)}><Text style={styles.buttonText}>Open Google Meet link</Text></Pressable>}
        <Pressable style={[styles.button, { alignSelf: "stretch" }]} onPress={onBooked}><Text style={styles.buttonText}>See my bookings</Text></Pressable>
        <Pressable onPress={onBack} hitSlop={12}><Text style={styles.link}>Back to all lawyers</Text></Pressable>
      </ScrollView>
    );
  }

  const ready = slot && form.name.trim().length >= 2 && form.phone.trim().length >= 10 && form.issue.trim().length >= 10;
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <Pressable onPress={onBack} hitSlop={12}><Text style={styles.link}>← All lawyers</Text></Pressable>
        <View style={{ flexDirection: "row", gap: 14, alignItems: "center" }}>
          <Avatar initials={lawyer.initials} size={72} />
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={[styles.title, { fontSize: 24, lineHeight: 28 }]}>{lawyer.name}</Text>
            <Text style={styles.body}>{lawyer.headline}</Text>
            <Rating lawyer={lawyer} />
          </View>
        </View>
        <Tags items={lawyer.specialisations} />
        <Text style={ui.muted}>{lawyer.experience_years} years experience · {lawyer.locality ? `${lawyer.locality}, ` : ""}{lawyer.city} · Speaks {lawyer.languages.join(", ")}</Text>

        <View style={styles.card}>
          <View style={styles.cardFoot}>
            <View><Text style={ui.muted}>Consultation fee</Text><Text style={styles.fee}>{formatFee(lawyer.consultation_fee)}</Text></View>
            <Text style={ui.muted}>{lawyer.consultation_minutes} min · Google Meet</Text>
          </View>
          <Text style={styles.label}>Pick a time</Text>
          <SlotPicker slug={slug} selected={slot?.starts_at ?? null} onSelect={setSlot} refreshKey={slotsKey} />
          {error ? <Text style={ui.error}>{error}</Text> : null}
          {slot && (
            <View style={{ gap: 10, marginTop: 6 }}>
              <View style={styles.summary}><Text style={ui.muted}>Your slot</Text><Text style={styles.summaryValue}>{slot.day}, {slot.label}</Text></View>
              <Field label="Your name" value={form.name} onChangeText={(name) => setForm({ ...form, name })} autoComplete="name" />
              <Field label="WhatsApp number" value={form.phone} onChangeText={(phone) => setForm({ ...form, phone })} keyboardType="phone-pad" autoComplete="tel" placeholder="+91 98765 43210" />
              <Field label="Email (optional)" value={form.email} onChangeText={(email) => setForm({ ...form, email })} keyboardType="email-address" autoComplete="email" />
              <Field label="What would you like to discuss?" value={form.issue} onChangeText={(issue) => setForm({ ...form, issue })} multiline placeholder="A few lines so the lawyer can prepare." />
              <Pressable style={[styles.button, (!ready || busy) && { opacity: 0.5 }]} disabled={!ready || busy} onPress={book}>
                <Text style={styles.buttonText}>{busy ? "Booking…" : `Confirm booking · ${formatFee(lawyer.consultation_fee)}`}</Text>
              </Pressable>
              <Text style={styles.small}>Please don’t share Aadhaar numbers, passwords or bank details. Our team confirms the fee and how to pay before the call.</Text>
            </View>
          )}
        </View>

        {lawyer.bio ? <View style={styles.card}><Text style={styles.label}>About</Text><Text style={styles.body}>{lawyer.bio}</Text></View> : null}
        <View style={styles.card}>
          <Text style={styles.label}>Credentials</Text>
          {lawyer.education ? <Text style={styles.body}>{lawyer.education}</Text> : null}
          {lawyer.bar_enrolment ? <Text style={styles.body}>Bar enrolment {lawyer.bar_enrolment}</Text> : null}
          {lawyer.courts.length ? <Text style={styles.body}>Practises at {lawyer.courts.join(" · ")}</Text> : null}
          <Text style={[styles.label, { marginTop: 8 }]}>Hours</Text>
          {lawyer.hours.map((d) => <Text key={d.day} style={styles.body}>{DAY_NAMES[d.day]}: {d.hours.length ? d.hours.join(", ") : "Closed"}</Text>)}
        </View>
        <View style={styles.card}>
          <Text style={styles.label}>Reviews</Text>
          {lawyer.reviews.length === 0 ? <Text style={ui.muted}>No reviews yet.</Text> : lawyer.reviews.map((r, i) => (
            <View key={i} style={{ gap: 3, paddingVertical: 6 }}>
              <View style={ui.row}><Text style={ui.star}>★ {r.rating}</Text><Text style={{ fontWeight: "700", color: colors.ink }}>{r.reviewer_name}</Text></View>
              {r.comment ? <Text style={styles.body}>{r.comment}</Text> : null}
            </View>
          ))}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

export function Field(props: { label: string; value: string; onChangeText: (v: string) => void; placeholder?: string; multiline?: boolean } & Pick<React.ComponentProps<typeof TextInput>, "keyboardType" | "autoComplete">) {
  const { label, multiline, ...input } = props;
  return (
    <View style={{ gap: 6 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput {...input} style={[styles.input, multiline && { minHeight: 90, textAlignVertical: "top" }]} placeholderTextColor="#9aa59f" multiline={multiline} />
    </View>
  );
}

export const styles = StyleSheet.create({
  page: { padding: 20, gap: 14, paddingBottom: 48 },
  brand: { fontSize: 22, fontWeight: "800", color: colors.ink, letterSpacing: -1 },
  title: { fontSize: 30, fontWeight: "700", color: forest, letterSpacing: -1, lineHeight: 36 },
  body: { fontSize: 14, lineHeight: 21, color: colors.muted },
  link: { fontSize: 13, fontWeight: "800", color: colors.green },
  label: { fontSize: 12, fontWeight: "700", color: "#43564d" },
  small: { fontSize: 11, lineHeight: 17, color: "#7e8c83" },
  searchBox: { flexDirection: "row", gap: 6, backgroundColor: colors.white, borderWidth: 1, borderColor: "#d4e0d8", borderRadius: 12, padding: 5 },
  searchInput: { flex: 1, paddingHorizontal: 10, fontSize: 14, color: colors.ink },
  searchButton: { backgroundColor: forest, borderRadius: 8, paddingHorizontal: 14, justifyContent: "center" },
  searchButtonText: { color: colors.white, fontWeight: "800", fontSize: 13 },
  chipRow: { gap: 6, paddingRight: 20 },
  chip: { borderWidth: 1, borderColor: "#d3e0d8", backgroundColor: colors.white, borderRadius: 18, paddingVertical: 7, paddingHorizontal: 11 },
  chipOn: { backgroundColor: forest, borderColor: forest },
  chipText: { fontSize: 12, fontWeight: "700", color: forest },
  card: { backgroundColor: colors.white, borderRadius: 14, borderWidth: 1, borderColor: colors.line, padding: 16, gap: 10 },
  cardTitle: { fontSize: 17, fontWeight: "700", color: forest },
  cardFoot: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 10 },
  fee: { fontSize: 20, fontWeight: "700", color: forest },
  next: { fontSize: 12, fontWeight: "700", color: "#24734d" },
  smallButton: { backgroundColor: forest, borderRadius: 8, paddingVertical: 10, paddingHorizontal: 18 },
  smallButtonText: { color: colors.white, fontWeight: "800", fontSize: 13 },
  button: { backgroundColor: forest, borderRadius: 8, paddingVertical: 15, paddingHorizontal: 16, alignItems: "center" },
  buttonText: { color: colors.white, fontSize: 15, fontWeight: "700" },
  input: { backgroundColor: colors.white, borderWidth: 1, borderColor: "#dce4da", borderRadius: 8, padding: 12, fontSize: 14, color: colors.ink },
  summary: { backgroundColor: "#eef7f2", borderRadius: 10, padding: 12, gap: 2 },
  summaryValue: { fontSize: 16, fontWeight: "700", color: forest },
  tick: { width: 60, height: 60, borderRadius: 30, backgroundColor: "#e4f3e9", alignItems: "center", justifyContent: "center" },
});
