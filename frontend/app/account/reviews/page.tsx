"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { REVIEW_MODERATION_LABELS, type CustomerReview, type CustomerReviewsPage } from "@homexo/shared";
import { api } from "../../api";
import CustomerAccess from "../CustomerAccess";
import MainContent from "../../ui/MainContent";
import useRetryDelay from "../../ui/useRetryDelay";
import "./reviews.css";

const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

export default function MyReviewsPage() {
  return <MainContent className="my-reviews"><header><div className="eyebrow">Your feedback</div><h1>My reviews</h1><p>See feedback you left after consultations and control whether it can be published.</p></header>
    <section className="my-review-notice"><h2>Withdrawing a review</h2><p>Withdrawal removes feedback from public profiles and ratings. The review and its history stay in your private booking record, and it cannot be published again from here.</p><p>For questions about retained information, you can <Link href="/account/privacy">send a privacy request</Link>.</p></section>
    <CustomerAccess intro="Sign in with the phone used for your consultation to manage your reviews."><MyReviews /></CustomerAccess>
  </MainContent>;
}

function MyReviews() {
  const [data, setData] = useState<CustomerReviewsPage | null>(null), [page, setPage] = useState(1), [error, setError] = useState("");
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState("");
  const sequence = useRef(0), guard = useRef(false);
  const listHeading = useRef<HTMLHeadingElement>(null), previousPage = useRef(page);
  useEffect(() => { if (previousPage.current !== page) { previousPage.current = page; listHeading.current?.focus(); } }, [page]);
  const load = useCallback(async () => {
    const request = ++sequence.current; setLoading(true); setError("");
    try { const next = await api.myReviews(page); if (request === sequence.current) setData(next); }
    catch (error) { if (request === sequence.current) setError(error instanceof Error ? error.message : "Your reviews could not load."); }
    finally { if (request === sequence.current) setLoading(false); }
  }, [page]);
  const invalidate = useCallback(() => { sequence.current++; }, []);
  useEffect(() => { load(); return invalidate; }, [load, invalidate]);
  async function withdraw(id: string) {
    if (guard.current) throw new Error("A withdrawal is already being recorded. Please wait.");
    guard.current = true; setBusy(id);
    try {
      const next = await api.withdrawMyReview(id);
      sequence.current++;
      setData(current => current ? { ...current, items: current.items.map(item => item.id === id ? next : item) } : current);
      setLoading(false);
      return next;
    } finally { guard.current = false; setBusy(""); }
  }
  return <section aria-label="Your consultation feedback"><div className="my-review-toolbar"><h2 ref={listHeading} tabIndex={-1}>Your consultation feedback</h2><button className="btn light" disabled={!!busy || loading} onClick={load}>Refresh reviews</button></div>
    {error && <p role="alert">{error}</p>}{loading && <p role="status">Loading your reviews…</p>}
    {data && !data.items.length ? <section className="my-review-card"><h3>No reviews on this page</h3><p>You can leave feedback after a consultation from <Link href="/bookings">your bookings</Link>.</p></section> : data?.items.map(review => <ReviewCard key={review.id} review={review} busy={!!busy || loading} onWithdraw={withdraw} />)}
    {data && (data.total > data.page_size || page > 1) && <nav className="my-review-toolbar" aria-label="Review pages"><button className="btn light" disabled={page === 1 || !!busy || loading} onClick={() => setPage(value => value - 1)}>Previous reviews</button><span>Page {page} · {data.total} reviews</span><button className="btn light" disabled={page * data.page_size >= data.total || !!busy || loading} onClick={() => setPage(value => value + 1)}>Next reviews</button></nav>}
  </section>;
}

function ReviewCard({ review, busy, onWithdraw }: { review: CustomerReview; busy: boolean; onWithdraw: (id: string) => Promise<CustomerReview> }) {
  const [confirm, setConfirm] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const heading = useRef<HTMLHeadingElement>(null), prompt = useRef<HTMLHeadingElement>(null), opener = useRef<HTMLButtonElement>(null);
  const submitting = useRef(false), restore = useRef(false);
  const retry = useRetryDelay();
  useEffect(() => {
    if (confirm) prompt.current?.focus();
    else if (restore.current) { restore.current = false; opener.current?.focus(); }
  }, [confirm]);
  useEffect(() => {
    if (review.status === "withdrawn" && (notice || confirm)) { setConfirm(false); heading.current?.focus(); }
  }, [review.status, notice, confirm]);
  async function submit() {
    if (busy || submitting.current || retry.seconds > 0) return;
    submitting.current = true;
    setError("");
    try { await onWithdraw(review.id); setConfirm(false); setNotice("Your review has been withdrawn. It is no longer included in public profiles or ratings."); }
    catch (error) { retry.record(error); setError(error instanceof Error ? error.message : "Withdrawal could not be confirmed. Refresh your reviews before trying again."); }
    finally { submitting.current = false; }
  }
  return <article className="my-review-card" aria-labelledby={`review-title-${review.id}`}>
    <span className="my-review-status">{REVIEW_MODERATION_LABELS[review.status]}</span><h2 ref={heading} tabIndex={-1} id={`review-title-${review.id}`}>{review.lawyer_name}</h2>
    <p><strong>{review.rating} / 5 stars</strong> · Submitted {date(review.created_at)}</p><p className="my-review-reference">Booking {review.ticket_number}</p><p className="my-review-text">{review.comment || "You submitted a star rating without a written comment."}</p>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    {review.status === "withdrawn" ? <p>Withdrawn {review.withdrawn_at ? date(review.withdrawn_at) : "by you"}. No further publication is allowed.</p> : confirm ? <section className="my-review-confirm" aria-label="Confirm review withdrawal">
      <h3 ref={prompt} tabIndex={-1}>Withdraw this review?</h3><p>This is final for this review. It will be removed from public profiles and ratings, and kept privately with your booking record.</p>
      <div className="my-review-actions"><button className="btn light" disabled={busy} onClick={() => { restore.current = true; setConfirm(false); setError(""); }}>Keep review</button><button className="btn" disabled={busy || retry.seconds > 0} onClick={submit}>{busy ? "Please wait…" : retry.seconds > 0 ? `Try again in ${retry.seconds}s` : "Confirm withdrawal"}</button></div>
    </section> : <button ref={opener} className="btn light" disabled={busy} onClick={() => { setConfirm(true); setNotice(""); setError(""); }}>Withdraw review</button>}
  </article>;
}
