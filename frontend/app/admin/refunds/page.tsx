"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { formatPaise } from "@homexo/shared";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import "./refunds.css";

type RefundRecord = { id: string; provider_refund_id: string; provider_payment_id: string; amount_paise: number; currency: string; status: string; review_code: string | null; revision: number; internal_note: string; updated_at: string };
type History = { items: RefundRecord[]; total: number; page: number; page_size: number };
type PaymentRow = { id: string; ticket_number: string; customer_name: string; provider: string; provider_payment_id: string | null; provider_order_id: string; status: string; amount_paise: number; currency: string; refunded_paise: number; pending_paise: number; remaining_paise: number; review_reason: string | null };
type Queue = { items: PaymentRow[]; counts: Record<string, number>; unmatched: number; total: number; page: number; page_size: number };
const states = { needs_action: "Needs action", pending: "Processing", completed: "Completed", review: "Needs review", all: "All refunds" };
const reason = (value: string) => ({ legacy_unverified: "Historical refund amount needs verification", conflicting_event: "Provider events disagree", currency_mismatch: "Refund currency does not match", amount_exceeds_payment: "Refund totals exceed the payment", payment_not_captured: "Payment has not been confirmed", ambiguous_payment: "Payment reference matches more than one record", conflicting_refund_event: "Repeated refund reference has conflicting details" })[value] || "Refund details need review";

export default function RefundQueue() {
  const { user, onError } = useStaff();
  const [queue, setQueue] = useState<Queue | null>(null), [state, setState] = useState("needs_action"), [page, setPage] = useState(1);
  const [input, setInput] = useState(""), [search, setSearch] = useState(""), [refresh, setRefresh] = useState(0), [error, setError] = useState("");
  const [selected, setSelected] = useState<PaymentRow | null>(null), [unmatched, setUnmatched] = useState(false);
  const history = useRef<HTMLElement>(null);
  useEffect(() => {
    if (user.role !== "admin") return;
    let active = true; setError("");
    adminFetch<Queue>(`/admin/refunds?state=${state}&page=${page}&q=${encodeURIComponent(search)}`, { cache: "no-store" })
      .then(value => { if (active) setQueue(value); }).catch(error => { if (active) setError(onError(error)); });
    return () => { active = false; };
  }, [user.role, state, page, search, refresh, onError]);
  useEffect(() => { if (selected || unmatched) history.current?.focus(); }, [selected, unmatched]);
  function choose(item: PaymentRow | null) { setSelected(item); setUnmatched(!item); }
  if (user.role !== "admin") return <MainContent className="refund-page"><h1>Refund tracking</h1><p>Administrator access is required.</p></MainContent>;
  return <MainContent className="refund-page"><header><div className="eyebrow">Payment operations</div><h1>Refund tracking</h1><p>Track provider-confirmed refunds, partial returns and cases needing follow-up. Initiate refunds in the payment provider dashboard; this queue records outcomes and internal notes.</p></header>
    <div className="refund-stats">{Object.entries(states).filter(([key]) => key !== "all").map(([key,label]) => <button key={key} className="refund-stat" onClick={() => { setState(key); setPage(1); }} aria-pressed={state === key}><span>{label}</span><strong>{queue?.counts[key] ?? "–"}</strong></button>)}</div>
    {error && <div role="alert"><p>{error}</p><button className="btn light" onClick={() => setRefresh(value => value + 1)}>Try queue again</button></div>}
    <div className="refund-toolbar"><label>Queue view<select value={state} onChange={event => { setState(event.target.value); setPage(1); }}>{Object.entries(states).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label><form onSubmit={event => { event.preventDefault(); setSearch(input.trim()); setPage(1); }}><label>Case or provider payment reference<input value={input} maxLength={120} onChange={event => setInput(event.target.value)} /></label><button className="btn light">Search</button></form><button className="btn light" onClick={() => setRefresh(value => value + 1)}>Refresh</button></div>
    <button className="refund-unmatched" onClick={() => choose(null)}>Unmatched provider refunds ({queue?.unmatched ?? 0})</button>
    <div className="refund-grid"><section aria-label="Refund payment queue">{!queue ? <p role="status">Loading refund queue…</p> : !queue.items.length ? <div className="refund-card"><h2>No payments in this view</h2><p>Change filters or refresh to check for updates.</p></div> : queue.items.map(item => <article className="refund-card" key={item.id}><div className="refund-row"><h2>{item.ticket_number}</h2><span className="refund-badge">{item.review_reason ? "Needs review" : item.status === "refunded" ? "Refunded" : item.pending_paise ? "Processing" : item.refunded_paise ? "Partial refund" : "Refund due"}</span></div><p>{item.customer_name} · {item.provider === "test" ? "Test mode" : "Razorpay"}</p><p className="refund-reference">Payment: {item.provider_payment_id || "Not yet confirmed"}</p>
      {item.review_reason ? <p className="refund-warning">{reason(item.review_reason)}. Confirm amounts with the provider before relying on this record.</p> : <dl><div><dt>Paid amount</dt><dd>{formatPaise(item.amount_paise, item.currency)}</dd></div><div><dt>Processed refund</dt><dd>{formatPaise(item.refunded_paise, item.currency)}</dd></div><div><dt>Pending provider refund</dt><dd>{formatPaise(item.pending_paise, item.currency)}</dd></div><div><dt>Not yet refunded</dt><dd>{formatPaise(item.remaining_paise, item.currency)}</dd></div></dl>}
      <div className="refund-row"><Link className="text-link" href={`/admin/tickets/${encodeURIComponent(item.ticket_number)}`}>Open case</Link><button className="btn light" onClick={() => choose(item)}>View refund history</button></div></article>)}
      {queue && (queue.total > queue.page_size || page > 1) && <div className="refund-row"><button className="btn light" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous payments</button><span>Page {page} · {queue.total} payments</span><button className="btn light" disabled={page * queue.page_size >= queue.total} onClick={() => setPage(value => value + 1)}>Next payments</button></div>}
    </section><section className="refund-card" ref={history} tabIndex={-1} aria-label="Selected refund history">{selected || unmatched ? <RefundHistory key={selected?.id || "unmatched"} path={selected ? `/admin/refunds/payments/${selected.id}` : "/admin/refunds/unmatched"} title={selected ? `${selected.ticket_number} refund history` : "Unmatched provider refunds"} onError={onError} /> : <><h2>Choose a payment</h2><p>View refund references and record follow-up notes. Notes do not issue a refund or verify settlement.</p></>}</section></div>
  </MainContent>;
}

function RefundHistory({ path, title, onError }: { path: string; title: string; onError: (error: unknown) => string }) {
  const [data, setData] = useState<History | null>(null), [page, setPage] = useState(1), [error, setError] = useState(""), [refresh, setRefresh] = useState(0);
  const load = useCallback(() => setRefresh(value => value + 1), []);
  useEffect(() => {
    let active = true; setData(null); setError("");
    adminFetch<History>(`${path}?page=${page}`, { cache: "no-store" }).then(value => { if (active) setData(value); }).catch(error => { if (active) setError(onError(error)); });
    return () => { active = false; };
  }, [path, page, refresh, onError]);
  return <><h2>{title}</h2><p>Only processed provider events count as returned money. A failed or pending refund is not a completed refund.</p>{error && <div role="alert"><p>{error}</p><button className="btn light" onClick={load}>Reload refund history</button></div>}
    {!data ? !error && <p role="status">Loading refund history…</p> : !data.items.length ? <p>No refund events have been recorded. Check the provider dashboard before initiating or repeating a refund.</p> : data.items.map(item => <RefundNote key={`${item.id}:${item.revision}`} item={item} onReload={load} onError={onError} />)}
    {data && (data.total > data.page_size || page > 1) && <div className="refund-row"><button className="btn light" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous refunds</button><span>Page {page}</span><button className="btn light" disabled={page * data.page_size >= data.total} onClick={() => setPage(value => value + 1)}>Next refunds</button></div>}
  </>;
}

function RefundNote({ item, onReload, onError }: { item: RefundRecord; onReload: () => void; onError: (error: unknown) => string }) {
  const [note, setNote] = useState(item.internal_note), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const guard = useRef(false);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (guard.current) return; guard.current = true; setBusy(true); setError("");
    try { await adminFetch(`/admin/refunds/${item.id}/note`, { method: "PATCH", body: JSON.stringify({ revision: item.revision, internal_note: note }) }); onReload(); }
    catch (error) { setError(onError(error)); }
    finally { guard.current = false; setBusy(false); }
  }
  return <article className="refund-record"><h3>{item.provider_refund_id}</h3><p><strong>{formatPaise(item.amount_paise, item.currency)}</strong> · {item.status}</p><p className="refund-reference">Provider payment: {item.provider_payment_id}</p><p>{new Date(item.updated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</p>{item.review_code && <p className="refund-warning">{reason(item.review_code)}</p>}
    <form onSubmit={save}><label>Internal follow-up note<textarea rows={3} maxLength={2000} required value={note} disabled={busy} onChange={event => setNote(event.target.value)} /></label><button className="btn light" disabled={busy}>{busy ? "Saving…" : "Save internal note"}</button></form>
    {error && <div role="alert"><p>{error} Your note is kept here.</p><button className="btn light" disabled={busy} onClick={onReload}>Reload history (replaces note)</button></div>}
  </article>;
}
