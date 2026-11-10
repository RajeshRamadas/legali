"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import "./reviews.css";

type Status = "pending" | "published" | "hidden";
type Review = { id: string; rating: number; comment: string; reviewer_name: string; created_at: string; updated_at: string;
  status: Status; revision: number; ticket_number: string; lawyer: { id: string; name: string } };
type Decision = { id: string; from_status: Status; to_status: Status; reason: string; note: string; revision: number; actor: string; created_at: string };
type Detail = { review: Review; history: Decision[]; total: number; page: number; page_size: number };
type Queue = { items: Review[]; counts: Record<Status, number>; total: number; page: number; page_size: number };
const statuses = { pending: "Waiting for review", published: "Published", hidden: "Not published", all: "All reviews" };
const reasons = { approved: "Suitable for publication", privacy: "Personal or confidential information", abuse: "Abusive or threatening content", off_topic: "Not about the consultation", authenticity: "Authenticity needs investigation", other: "Other policy concern" };
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

export default function ReviewModeration() {
  const { user, onError } = useStaff();
  const [state, setState] = useState("pending"), [page, setPage] = useState(1), [input, setInput] = useState(""), [q, setQuery] = useState("");
  const [data, setData] = useState<Queue | null>(null), [error, setError] = useState(""), [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useRef<HTMLElement>(null);
  useEffect(() => {
    if (user.role !== "admin") return;
    let active = true; setData(null); setError("");
    adminFetch<Queue>(`/admin/reviews?status=${state}&page=${page}&q=${encodeURIComponent(q)}`, { cache: "no-store" })
      .then(value => { if (active) setData(value); }).catch(error => { if (active) setError(onError(error)); });
    return () => { active = false; };
  }, [user.role, state, page, q, refresh, onError]);
  useEffect(() => { if (selected) detail.current?.focus({ preventScroll: false }); }, [selected]);
  const changed = useCallback(() => setRefresh(value => value + 1), []);
  if (user.role !== "admin") return <MainContent className="review-page"><h1>Review moderation</h1><p>Administrator access is required.</p></MainContent>;
  return <MainContent className="review-page">
    <header><div className="eyebrow">Publication review</div><h1>Review moderation</h1>
      <p>Check feedback for privacy, abuse and relevance before publication. Apply the same policy to positive and negative ratings. Customer wording and star ratings cannot be edited here.</p></header>
    <div className="review-stats" aria-label="Review queue counts">{(["pending", "published", "hidden"] as Status[]).map(status =>
      <button className="review-stat" key={status} aria-pressed={state === status} onClick={() => { setState(status); setPage(1); }}><span>{statuses[status]}</span><strong>{data?.counts[status] ?? "–"}</strong></button>)}</div>
    <div className="review-toolbar"><label>Review status<select value={state} onChange={event => { setState(event.target.value); setPage(1); }}>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <form onSubmit={event => { event.preventDefault(); setQuery(input.trim()); setPage(1); }}><label>Lawyer or case number<input value={input} onChange={event => setInput(event.target.value)} maxLength={120} /></label><button className="btn light">Search reviews</button></form><button className="btn light" onClick={changed}>Refresh queue</button></div>
    {error && <p role="alert">{error}</p>}
    <div className="review-grid"><section aria-label="Review queue">{!data ? !error && <p role="status">Loading review queue…</p> : !data.items.length ? <section className="review-card"><h2>No reviews in this view</h2><p>New feedback waits for review before appearing on a profile or affecting its rating.</p></section> : data.items.map(item =>
      <article className="review-card" key={item.id}><span className="review-badge">{statuses[item.status]}</span><h2>{item.lawyer.name}</h2><p><strong>{item.rating} / 5 stars</strong> · {item.reviewer_name} · {date(item.created_at)}</p><p className="review-text">{item.comment || "A star rating was submitted without a written comment."}</p>
        <div className="review-actions"><Link href={`/admin/tickets/${encodeURIComponent(item.ticket_number)}`}>{item.ticket_number}</Link><button className="btn light" onClick={() => setSelected(item.id)}>Review feedback</button></div></article>)}
      {data && (data.total > data.page_size || page > 1) && <div className="review-actions"><button className="btn light" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous reviews</button><span>Page {page} · {data.total} reviews</span><button className="btn light" disabled={page * data.page_size >= data.total} onClick={() => setPage(value => value + 1)}>Next reviews</button></div>}
    </section><section className="review-card" ref={detail} tabIndex={-1} aria-label="Selected review and decisions">{selected ? <ReviewDetail key={selected} id={selected} ownId={user.id} onChanged={changed} onError={onError} /> : <><h2>Choose feedback to review</h2><p>Decisions require a private reason and keep a revision history. Do not include extra customer details in the note.</p></>}</section></div>
  </MainContent>;
}

function ReviewDetail({ id, ownId, onChanged, onError }: { id: string; ownId: string; onChanged: () => void; onError: (error: unknown) => string }) {
  const [data, setData] = useState<Detail | null>(null), [page, setPage] = useState(1), [refresh, setRefresh] = useState(0), [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const reload = useCallback(() => { setData(null); setPage(1); setRefresh(value => value + 1); heading.current?.focus(); }, []);
  useEffect(() => {
    let active = true; setError("");
    adminFetch<Detail>(`/admin/reviews/${id}?page=${page}`, { cache: "no-store" }).then(value => { if (active) setData(value); }).catch(error => { if (active) setError(onError(error)); });
    return () => { active = false; };
  }, [id, page, refresh, onError]);
  return <><h2 ref={heading} tabIndex={-1} className="review-decision-title">Review decision</h2>{notice && <p role="status">{notice}</p>}{error && <div role="alert"><p>{error}</p><button className="btn light" onClick={reload}>Reload review (replaces draft)</button></div>}
    {!data ? !error && <p role="status">Loading feedback…</p> : <>
      <DecisionForm review={data.review} ownId={ownId} onReload={reload} onSaved={() => { setNotice("Moderation decision saved."); reload(); onChanged(); }} onError={onError} />
      <h3>Private decision history</h3>{!data.history.length ? <p>No moderation decisions recorded.</p> : <ol className="review-history">{data.history.map(item => <li key={item.id}><strong>{statuses[item.to_status]} · revision {item.revision}</strong><p>{reasons[item.reason as keyof typeof reasons] || "Policy review"} · {item.actor} · {date(item.created_at)}</p><p className="review-text">{item.note}</p></li>)}</ol>}
      {(data.total > data.page_size || page > 1) && <div className="review-actions"><button className="btn light" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous decisions</button><span>History page {page}</span><button className="btn light" disabled={page * data.page_size >= data.total} onClick={() => setPage(value => value + 1)}>Next decisions</button></div>}
    </>}
  </>;
}

function DecisionForm({ review, ownId, onSaved, onReload, onError }: { review: Review; ownId: string; onSaved: () => void; onReload: () => void; onError: (error: unknown) => string }) {
  // Keep the editing revision across history pagination; only an explicit reload replaces a draft.
  const [snapshot] = useState(review);
  const [status, setStatus] = useState<"published" | "hidden">(snapshot.status === "published" ? "hidden" : "published");
  const [reason, setReason] = useState(snapshot.status === "published" ? "privacy" : "approved");
  const [note, setNote] = useState(""), [reviewed, setReviewed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const guard = useRef(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (guard.current) return; guard.current = true; setBusy(true); setError("");
    try { await adminFetch(`/admin/reviews/${snapshot.id}`, { method: "PATCH", body: JSON.stringify({ revision: snapshot.revision, status, reason, note: note.trim(), reviewed }) }); onSaved(); }
    catch (error) { setError(onError(error)); }
    finally { guard.current = false; setBusy(false); }
  }
  return <div className="review-editor"><h3>{snapshot.lawyer.name} · {snapshot.rating} / 5 stars</h3><p>From {snapshot.reviewer_name} · {statuses[snapshot.status]} · editing revision {snapshot.revision}</p><p className="review-text">{snapshot.comment || "No written comment."}</p>
    {snapshot.lawyer.id === ownId ? <p className="review-warning">Another administrator must moderate reviews of your own profile.</p> : <form onSubmit={submit}>
      <label>Publication decision<select value={status} disabled={busy} onChange={event => { const value = event.target.value as "published" | "hidden"; setStatus(value); setReason(value === "published" ? "approved" : "privacy"); }}><option value="published" disabled={snapshot.status === "published"}>Publish feedback</option><option value="hidden" disabled={snapshot.status === "hidden"}>Do not publish / hide feedback</option></select></label>
      <label>Decision reason<select value={reason} disabled={busy} onChange={event => setReason(event.target.value)}>{Object.entries(reasons).filter(([key]) => status === "published" ? key === "approved" : key !== "approved").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Private decision note<textarea required minLength={5} maxLength={1000} rows={3} value={note} disabled={busy} onChange={event => setNote(event.target.value)} /></label>
      <label className="review-confirm"><input type="checkbox" required checked={reviewed} disabled={busy} onChange={event => setReviewed(event.target.checked)} />I reviewed this feedback and its publication implications.</label>
      <button className="btn" disabled={busy || !reviewed || note.trim().length < 5}>{busy ? "Saving decision…" : "Save moderation decision"}</button>
    </form>}
    {error && <p role="alert">{error} Your draft is kept here.</p>}<button className="btn light" disabled={busy} onClick={onReload}>Reload review (replaces draft)</button>
  </div>;
}
