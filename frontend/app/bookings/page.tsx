"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { formatFee, type Booking, type BookingRef, type LawyerSlot } from "@homexo/shared";
import { api } from "../api";
import LawyerShell from "../lawyers/LawyerShell";
import SlotPicker from "../lawyers/SlotPicker";
import { forgetBooking, saveBooking, savedBookings } from "../lawyers/store";

type Entry = { ref: BookingRef; booking: Booking | null; error?: string };

const upcoming = (b: Booking) => b.meeting.status === "scheduled" && new Date(b.meeting.ends_at).getTime() > Date.now();
const joinable = (b: Booking) => upcoming(b) && new Date(b.meeting.starts_at).getTime() - Date.now() < 15 * 60000;

function BookingCard({ entry, onChange, onForget }: { entry: Entry; onChange: (b: Booking) => void; onForget: () => void }) {
  const { ref, booking } = entry;
  const [mode, setMode] = useState<"" | "move" | "cancel" | "review">("");
  const [slot, setSlot] = useState<LawyerSlot & { day: string } | null>(null);
  const [reason, setReason] = useState("");
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!booking) {
    return (
      <article className="lw-booking past">
        <p className="lw-error">{ref.ticket_number}: {entry.error ?? "Loading…"}</p>
        {entry.error && <div className="lw-actions"><button onClick={onForget}>Remove from this list</button></div>}
      </article>
    );
  }

  async function run(action: () => Promise<Booking>) {
    setError("");
    setBusy(true);
    try {
      onChange(await action());
      setMode("");
      setSlot(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const m = booking.meeting;
  return (
    <article className={`lw-booking${upcoming(booking) ? "" : " past"}`}>
      <div className="lw-booking-top">
        <div className="lw-avatar" aria-hidden>{booking.lawyer.initials}</div>
        <div>
          <h3>{booking.lawyer.slug ? <Link href={`/lawyers/${booking.lawyer.slug}`}>{booking.lawyer.name}</Link> : booking.lawyer.name}</h3>
          <small>{booking.lawyer.headline || "Video consultation"} · {booking.ticket_number}</small>
        </div>
        <span className={`lw-pill ${m.status}`} style={{ marginLeft: "auto" }}>{m.status_label}</span>
      </div>
      <div className="lw-when">
        <div><b>{m.when}</b><small>{Math.round((new Date(m.ends_at).getTime() - new Date(m.starts_at).getTime()) / 60000)} min on Google Meet{booking.fee !== null ? ` · ${formatFee(booking.fee)}` : ""}</small></div>
        {upcoming(booking) && (m.meet_link
          ? <a className={`btn small${joinable(booking) ? " gold" : " light"}`} href={m.meet_link} target="_blank" rel="noreferrer">{joinable(booking) ? "Join now" : "Meeting link"}</a>
          : <small>Link coming on WhatsApp</small>)}
      </div>
      {booking.review && <p className="lw-fine">You rated this {"★".repeat(booking.review.rating)}{booking.review.comment ? `: “${booking.review.comment}”` : ""}</p>}
      {error && <p className="lw-error" role="alert">{error}</p>}

      {mode === "" && (
        <div className="lw-actions">
          {booking.can_change && <button onClick={() => setMode("move")}>Reschedule</button>}
          {booking.can_change && <button onClick={() => setMode("cancel")}>Cancel booking</button>}
          {booking.can_review && <button onClick={() => setMode("review")}>Rate this consultation</button>}
          {booking.lawyer.slug && !upcoming(booking) && <Link href={`/lawyers/${booking.lawyer.slug}`} style={{ color: "var(--forest2)", fontWeight: 800 }}>Book again</Link>}
          {upcoming(booking) && !booking.can_change && <span className="lw-fine">To change this booking now, please call us.</span>}
          {!upcoming(booking) && <button onClick={onForget}>Remove from this list</button>}
        </div>
      )}
      {mode === "move" && booking.lawyer.slug && (
        <div>
          <SlotPicker slug={booking.lawyer.slug} selected={slot?.starts_at ?? null} onSelect={setSlot} />
          <div className="lw-actions" style={{ alignItems: "center" }}>
            <button className="btn small" style={{ color: "white" }} disabled={!slot || busy} onClick={() => slot && run(() => api.rescheduleBooking(ref, slot.starts_at))}>
              {slot ? `Move to ${slot.day}, ${slot.label}` : "Pick a new time"}
            </button>
            <button onClick={() => setMode("")}>Back</button>
          </div>
        </div>
      )}
      {mode === "cancel" && (
        <form className="lw-form" onSubmit={(e) => { e.preventDefault(); run(() => api.cancelBooking(ref, reason.trim())); }}>
          <label>Reason (optional, shared with the lawyer)<input maxLength={400} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="lw-actions" style={{ alignItems: "center" }}>
            <button className="btn small" style={{ color: "white" }} disabled={busy}>Cancel this consultation</button>
            <button type="button" onClick={() => setMode("")}>Keep it</button>
          </div>
        </form>
      )}
      {mode === "review" && (
        <form className="lw-form" onSubmit={(e) => { e.preventDefault(); if (rating) run(() => api.reviewBooking(ref, rating, comment.trim())); }}>
          <div className="lw-stars" role="radiogroup" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((n) => <button type="button" key={n} role="radio" aria-checked={rating === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} className={n <= rating ? "on" : undefined} onClick={() => setRating(n)}>★</button>)}
          </div>
          <label>Your review (optional, shown on the lawyer’s profile with your first name)<textarea rows={3} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
          <div className="lw-actions" style={{ alignItems: "center" }}>
            <button className="btn small" style={{ color: "white" }} disabled={!rating || busy}>Submit rating</button>
            <button type="button" onClick={() => setMode("")}>Back</button>
          </div>
        </form>
      )}
    </article>
  );
}

export default function BookingsPage() {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [find, setFind] = useState({ ticket: "", contact: "" });
  const [findError, setFindError] = useState("");
  const [finding, setFinding] = useState(false);

  const load = useCallback(() => {
    const refs = savedBookings();
    setEntries(refs.map((ref) => ({ ref, booking: null })));
    refs.forEach((ref) => {
      api.lookupBooking(ref)
        .then((booking) => setEntries((prev) => prev?.map((e) => (e.ref.ticket_number === ref.ticket_number ? { ref, booking } : e)) ?? null))
        .catch((err) => setEntries((prev) => prev?.map((e) => (e.ref.ticket_number === ref.ticket_number ? { ref, booking: null, error: err instanceof Error ? err.message : "Not found" } : e)) ?? null));
    });
  }, []);
  useEffect(load, [load]);

  async function findBooking(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFindError("");
    setFinding(true);
    const ref = { ticket_number: find.ticket.trim().toUpperCase(), contact: find.contact.trim() };
    try {
      const booking = await api.lookupBooking(ref);
      saveBooking(ref);
      setEntries((prev) => [{ ref, booking }, ...(prev ?? []).filter((e) => e.ref.ticket_number !== ref.ticket_number)]);
      setFind({ ticket: "", contact: "" });
    } catch (e) {
      setFindError(e instanceof Error ? e.message : "We couldn't find that booking.");
    } finally {
      setFinding(false);
    }
  }

  const sorted = [...(entries ?? [])].sort((a, b) => {
    // Upcoming first, soonest first; then past, most recent first.
    const au = a.booking && upcoming(a.booking), bu = b.booking && upcoming(b.booking);
    if (au !== bu) return au ? -1 : 1;
    const at = a.booking ? new Date(a.booking.meeting.starts_at).getTime() : 0, bt = b.booking ? new Date(b.booking.meeting.starts_at).getTime() : 0;
    return au ? at - bt : bt - at;
  });

  return (
    <LawyerShell>
      <section className="lw-band">
        <div className="wrap">
          <div className="eyebrow">Your consultations</div>
          <h1>My bookings</h1>
          <p>Join, move, cancel or rate your consultations. Bookings made on this browser show here; find others with the booking number and your phone or email.</p>
        </div>
      </section>
      <div className="wrap lw-bookings">
        <section className="lw-list" aria-live="polite">
          {entries !== null && entries.length === 0 && (
            <div className="lw-empty">No bookings on this browser yet. <Link href="/lawyers" style={{ color: "var(--forest2)", fontWeight: 800 }}>Find a lawyer</Link> to book a consultation.</div>
          )}
          {sorted.map((entry) => (
            <BookingCard
              key={entry.ref.ticket_number} entry={entry}
              onChange={(booking) => setEntries((prev) => prev?.map((e) => (e.ref.ticket_number === entry.ref.ticket_number ? { ...e, booking } : e)) ?? null)}
              onForget={() => { forgetBooking(entry.ref.ticket_number); setEntries((prev) => prev?.filter((e) => e.ref.ticket_number !== entry.ref.ticket_number) ?? null); }}
            />
          ))}
        </section>
        <aside>
          <form className="lw-panel lw-form" style={{ marginTop: 0, borderTop: "1px solid var(--line)" }} onSubmit={findBooking}>
            <h2>Find a booking</h2>
            <label>Booking number<input required placeholder="HX-261019-AB12CD" value={find.ticket} onChange={(e) => setFind({ ...find, ticket: e.target.value })} /></label>
            <label>Phone or email used to book<input required value={find.contact} onChange={(e) => setFind({ ...find, contact: e.target.value })} /></label>
            {findError && <p className="lw-error" role="alert">{findError}</p>}
            <button className="btn small" disabled={finding}>{finding ? "Finding…" : "Find booking"}</button>
          </form>
        </aside>
      </div>
    </LawyerShell>
  );
}
