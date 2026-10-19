import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { formatFee, type Booking, type BookingRef, type LawyerSlot } from "@homexo/shared";
import { forgetBookingRef, saveBookingRef, useBookingRefs } from "./bookingsStore";
import { Field, styles } from "./LawyersScreen";
import { Avatar, SlotPicker, ui } from "./lawyerUi";
import { api, colors } from "./theme";

const upcoming = (b: Booking) => b.meeting.status === "scheduled" && new Date(b.meeting.ends_at).getTime() > Date.now();

function BookingItem({ bookingRef }: { bookingRef: BookingRef }) {
  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"" | "move" | "cancel" | "review">("");
  const [slot, setSlot] = useState<(LawyerSlot & { day: string }) | null>(null);
  const [reason, setReason] = useState("");
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.lookupBooking(bookingRef).then(setBooking).catch((e) => setError(e instanceof Error ? e.message : "Not found"));
  }, [bookingRef]);

  async function run(action: () => Promise<Booking>) {
    setError("");
    setBusy(true);
    try {
      setBooking(await action());
      setMode("");
      setSlot(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (!booking) {
    return (
      <View style={styles.card}>
        {error ? (
          <>
            <Text style={ui.error}>{bookingRef.ticket_number}: {error}</Text>
            <Pressable onPress={() => forgetBookingRef(bookingRef.ticket_number)}><Text style={styles.link}>Remove</Text></Pressable>
          </>
        ) : <ActivityIndicator color={colors.green} />}
      </View>
    );
  }

  const m = booking.meeting;
  const live = upcoming(booking);
  return (
    <View style={[styles.card, !live && { backgroundColor: "#f7f8f4" }]}>
      <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
        <Avatar initials={booking.lawyer.initials} size={46} />
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>{booking.lawyer.name}</Text>
          <Text style={ui.muted}>{booking.ticket_number} · {m.status_label}</Text>
        </View>
      </View>
      <View style={styles.summary}>
        <Text style={styles.summaryValue}>{m.when}</Text>
        <Text style={ui.muted}>{Math.round((new Date(m.ends_at).getTime() - new Date(m.starts_at).getTime()) / 60000)} min on Google Meet{booking.fee !== null ? ` · ${formatFee(booking.fee)}` : ""}</Text>
      </View>
      {live && (m.meet_link
        ? <Pressable style={styles.button} onPress={() => Linking.openURL(m.meet_link!)}><Text style={styles.buttonText}>Join on Google Meet</Text></Pressable>
        : <Text style={ui.muted}>The meeting link will come on WhatsApp before it starts.</Text>)}
      {booking.review && <Text style={ui.muted}>You rated this {"★".repeat(booking.review.rating)}</Text>}
      {error ? <Text style={ui.error}>{error}</Text> : null}

      {mode === "" && (
        <View style={ui.row}>
          {booking.can_change && <Pressable onPress={() => setMode("move")} hitSlop={8}><Text style={styles.link}>Reschedule</Text></Pressable>}
          {booking.can_change && <Text style={ui.muted}>·</Text>}
          {booking.can_change && <Pressable onPress={() => setMode("cancel")} hitSlop={8}><Text style={styles.link}>Cancel</Text></Pressable>}
          {booking.can_review && <Pressable onPress={() => setMode("review")} hitSlop={8}><Text style={styles.link}>Rate this consultation</Text></Pressable>}
          {live && !booking.can_change && <Text style={ui.muted}>To change it now, please call us.</Text>}
          {!live && <Pressable onPress={() => forgetBookingRef(bookingRef.ticket_number)} hitSlop={8}><Text style={styles.link}>Remove from list</Text></Pressable>}
        </View>
      )}
      {mode === "move" && booking.lawyer.slug && (
        <View style={{ gap: 10 }}>
          <SlotPicker slug={booking.lawyer.slug} selected={slot?.starts_at ?? null} onSelect={setSlot} />
          <Pressable style={[styles.button, (!slot || busy) && { opacity: 0.5 }]} disabled={!slot || busy} onPress={() => slot && run(() => api.rescheduleBooking(bookingRef, slot.starts_at))}>
            <Text style={styles.buttonText}>{slot ? `Move to ${slot.day}, ${slot.label}` : "Pick a new time"}</Text>
          </Pressable>
          <Pressable onPress={() => setMode("")}><Text style={styles.link}>Back</Text></Pressable>
        </View>
      )}
      {mode === "cancel" && (
        <View style={{ gap: 10 }}>
          <Field label="Reason (optional, shared with the lawyer)" value={reason} onChangeText={setReason} />
          <Pressable style={[styles.button, { backgroundColor: colors.danger }, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => run(() => api.cancelBooking(bookingRef, reason.trim()))}>
            <Text style={styles.buttonText}>Cancel this consultation</Text>
          </Pressable>
          <Pressable onPress={() => setMode("")}><Text style={styles.link}>Keep it</Text></Pressable>
        </View>
      )}
      {mode === "review" && (
        <View style={{ gap: 10 }}>
          <View style={{ flexDirection: "row", gap: 6 }} accessibilityRole="radiogroup">
            {[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} onPress={() => setRating(n)} accessibilityRole="radio" accessibilityState={{ checked: rating === n }} accessibilityLabel={`${n} stars`}>
                <Text style={{ fontSize: 32, color: n <= rating ? "#d6ad66" : "#cdd8d1" }}>★</Text>
              </Pressable>
            ))}
          </View>
          <Field label="Your review (optional)" value={comment} onChangeText={setComment} multiline />
          <Pressable style={[styles.button, (!rating || busy) && { opacity: 0.5 }]} disabled={!rating || busy} onPress={() => run(() => api.reviewBooking(bookingRef, rating, comment.trim()))}>
            <Text style={styles.buttonText}>Submit rating</Text>
          </Pressable>
          <Pressable onPress={() => setMode("")}><Text style={styles.link}>Back</Text></Pressable>
        </View>
      )}
    </View>
  );
}

export function BookingsScreen({ onFindLawyer }: { onFindLawyer: () => void }) {
  const refs = useBookingRefs();
  const [ticket, setTicket] = useState("");
  const [contact, setContact] = useState("");
  const [error, setError] = useState("");
  const [finding, setFinding] = useState(false);

  async function find() {
    setError("");
    setFinding(true);
    const ref = { ticket_number: ticket.trim().toUpperCase(), contact: contact.trim() };
    try {
      await api.lookupBooking(ref);
      saveBookingRef(ref);
      setTicket("");
      setContact("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't find that booking.");
    } finally {
      setFinding(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>My bookings</Text>
        <Text style={styles.body}>Join, move, cancel or rate your consultations.</Text>
        {refs.length === 0 && (
          <View style={styles.card}>
            <Text style={styles.body}>No bookings on this phone yet.</Text>
            <Pressable style={styles.button} onPress={onFindLawyer}><Text style={styles.buttonText}>Find a lawyer</Text></Pressable>
          </View>
        )}
        {refs.map((ref) => <BookingItem key={ref.ticket_number} bookingRef={ref} />)}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Find a booking</Text>
          <Text style={ui.muted}>Booked on the website or another phone? Enter the booking number and the phone or email you used.</Text>
          <TextInput style={styles.input} value={ticket} onChangeText={setTicket} placeholder="HX-261019-AB12CD" autoCapitalize="characters" placeholderTextColor="#9aa59f" accessibilityLabel="Booking number" />
          <TextInput style={styles.input} value={contact} onChangeText={setContact} placeholder="Phone or email" placeholderTextColor="#9aa59f" accessibilityLabel="Phone or email" />
          {error ? <Text style={ui.error}>{error}</Text> : null}
          <Pressable style={[styles.button, (finding || !ticket.trim() || !contact.trim()) && { opacity: 0.5 }]} disabled={finding || !ticket.trim() || !contact.trim()} onPress={find}>
            <Text style={styles.buttonText}>{finding ? "Finding…" : "Find booking"}</Text>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
