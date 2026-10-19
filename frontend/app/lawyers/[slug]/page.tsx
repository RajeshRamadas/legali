"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { formatFee, type Booking, type LawyerProfile, type LawyerSlot } from "@homexo/shared";
import { api } from "../../api";
import LawyerShell from "../LawyerShell";
import Rating from "../Rating";
import SlotPicker from "../SlotPicker";
import { saveBooking } from "../store";

const DAY_NAMES: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
const reviewDate = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const emptyForm = { name: "", phone: "", email: "", issue: "" };

export default function LawyerPage({ params }: { params: { slug: string } }) {
  const [lawyer, setLawyer] = useState<LawyerProfile | null>(null);
  const [loadError, setLoadError] = useState("");
  const [slot, setSlot] = useState<(LawyerSlot & { day: string }) | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [booked, setBooked] = useState<Booking | null>(null);
  const [slotsKey, setSlotsKey] = useState(0);

  useEffect(() => {
    api.getLawyer(params.slug).then(setLawyer).catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load this lawyer."));
  }, [params.slug]);

  async function book(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!slot) return;
    setError("");
    setBusy(true);
    try {
      const booking = await api.bookLawyer(params.slug, {
        starts_at: slot.starts_at, customer_name: form.name.trim(), phone: form.phone.trim(),
        email: form.email.trim() || undefined, issue: form.issue.trim(), source: "website",
      });
      saveBooking({ ticket_number: booking.ticket_number, contact: form.phone.trim() });
      setBooked(booking);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not book. Please try again.");
      // The slot may have just gone; show the latest times.
      setSlot(null);
      setSlotsKey((k) => k + 1);
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return <LawyerShell><div className="wrap" style={{ padding: "40px 0" }}><p className="lw-error">{loadError}</p><Link className="btn small light" href="/lawyers">← All lawyers</Link></div></LawyerShell>;
  }
  if (!lawyer) return <LawyerShell><div className="wrap" style={{ padding: "40px 0" }}><p className="lw-fine">Loading…</p></div></LawyerShell>;

  return (
    <LawyerShell>
      <div className="wrap lw-profile">
        <div>
          <Link href="/lawyers" className="admin-back" style={{ display: "inline-block", fontSize: 12, fontWeight: 800, color: "var(--forest2)", marginBottom: 14 }}>← All lawyers</Link>
          <section className="lw-panel">
            <div className="lw-hero">
              <div className="lw-avatar big" aria-hidden>{lawyer.initials}</div>
              <div>
                <h1>{lawyer.name}</h1>
                <p className="lw-headline" style={{ fontSize: 14 }}>{lawyer.headline}</p>
                <div className="lw-tags">{lawyer.specialisations.map((s) => <span key={s} className="lw-tag">{s}</span>)}</div>
                <ul className="lw-facts">
                  <li><b>{lawyer.experience_years} years</b> experience</li>
                  <li>{lawyer.locality ? `${lawyer.locality}, ` : ""}{lawyer.city}</li>
                  <li>Speaks {lawyer.languages.join(", ")}</li>
                  {lawyer.consultations > 0 && <li>{lawyer.consultations} consultations on Homexo</li>}
                </ul>
                <div style={{ marginTop: 8 }}><Rating lawyer={lawyer} /></div>
              </div>
            </div>
          </section>

          {lawyer.bio && <section className="lw-panel"><h2>About</h2><p style={{ whiteSpace: "pre-wrap" }}>{lawyer.bio}</p></section>}

          <section className="lw-panel">
            <h2>Credentials</h2>
            <dl className="lw-dl">
              {lawyer.education && <><dt>Education</dt><dd>{lawyer.education}</dd></>}
              {lawyer.bar_enrolment && <><dt>Bar enrolment</dt><dd>{lawyer.bar_enrolment}</dd></>}
              {lawyer.courts.length > 0 && <><dt>Practises at</dt><dd>{lawyer.courts.join(" · ")}</dd></>}
              <dt>Consultation</dt><dd>{formatFee(lawyer.consultation_fee)} for {lawyer.consultation_minutes} minutes on Google Meet</dd>
            </dl>
          </section>

          <section className="lw-panel">
            <h2>Consultation hours</h2>
            <div className="lw-hours">
              {lawyer.hours.map((d) => (
                <div key={d.day}><b>{DAY_NAMES[d.day]}</b>{d.hours.length ? d.hours.map((h) => <span key={h}>{h}</span>) : <span className="off">Closed</span>}</div>
              ))}
            </div>
          </section>

          <section className="lw-panel">
            <h2>Reviews {lawyer.review_count > 0 && <span className="lw-rating" style={{ marginLeft: 8 }}><span className="lw-star">★ {lawyer.rating?.toFixed(1)}</span></span>}</h2>
            {lawyer.reviews.length === 0 ? <p className="lw-fine">No reviews yet. Customers can rate a consultation after it takes place.</p> : (
              <ul className="lw-reviews">
                {lawyer.reviews.map((r, i) => (
                  <li key={i}>
                    <span className="lw-rating"><span className="lw-star">★ {r.rating}</span></span> <b style={{ fontSize: 13 }}>{r.reviewer_name}</b> <small>· {reviewDate.format(new Date(r.at))}</small>
                    {r.comment && <p>{r.comment}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="lw-sticky">
          <section className="lw-panel" aria-live="polite">
            {booked ? (
              <div className="lw-done">
                <div className="lw-tick" aria-hidden>✓</div>
                <h2>Consultation booked</h2>
                <p>{booked.meeting.when} with {booked.lawyer.name}. We have sent the details to your WhatsApp{booked.meeting.meet_link ? ", with the Google Meet link" : " and will send the meeting link before it starts"}.</p>
                <div className="lw-summary" style={{ width: "100%" }}><span>Booking number<b>{booked.ticket_number}</b></span><span>{booked.fee !== null ? formatFee(booked.fee) : ""}</span></div>
                {booked.meeting.meet_link && <a className="btn" href={booked.meeting.meet_link} target="_blank" rel="noreferrer">Google Meet link</a>}
                <Link className="btn light small" href="/bookings">View my bookings</Link>
                <p className="lw-fine">Keep the booking number. With it and your phone number you can move, cancel or rate this consultation.</p>
              </div>
            ) : (
              <>
                <h2>Book a video consultation</h2>
                <div className="lw-summary" style={{ marginBottom: 14 }}>
                  <span>Consultation fee<b>{formatFee(lawyer.consultation_fee)}</b></span>
                  <span>{lawyer.consultation_minutes} min · Google Meet</span>
                </div>
                <SlotPicker slug={lawyer.slug} selected={slot?.starts_at ?? null} onSelect={setSlot} refreshKey={slotsKey} />
                {error && <p className="lw-error" role="alert">{error}</p>}
                {slot && (
                  <form className="lw-form" onSubmit={book}>
                    <div className="lw-summary"><span>Your slot<b>{slot.day}, {slot.label}</b></span><button type="button" className="lw-clear" onClick={() => setSlot(null)}>Change</button></div>
                    <label>Your name<input required minLength={2} maxLength={120} autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
                    <label>WhatsApp number<input required type="tel" inputMode="tel" autoComplete="tel" placeholder="+91 98765 43210" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
                    <label>Email (optional, for the calendar invite)<input type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
                    <label>What would you like to discuss?<textarea required minLength={10} maxLength={2000} rows={4} placeholder="A few lines about your situation, so the lawyer can prepare." value={form.issue} onChange={(e) => setForm({ ...form, issue: e.target.value })} /></label>
                    <button className="btn" disabled={busy}>{busy ? "Booking…" : `Confirm booking · ${formatFee(lawyer.consultation_fee)}`}</button>
                    <p className="lw-fine">Please don’t share Aadhaar numbers, passwords or bank details here. Our team confirms the fee and how to pay before the call.</p>
                  </form>
                )}
              </>
            )}
          </section>
        </aside>
      </div>
    </LawyerShell>
  );
}
