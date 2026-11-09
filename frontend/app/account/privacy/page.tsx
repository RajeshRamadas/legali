"use client";
import MainContent from "../../ui/MainContent";

import { useCallback, useEffect, useRef, useState } from "react";
import { PRIVACY_KIND_LABELS, PRIVACY_STATUS_LABELS, PRIVACY_RESOLUTION_LABELS, PRIVACY_REASON_LABELS, type PrivacyKind, type PrivacyNotice, type PrivacyRequestsPage, type PrivacyRequestRecord } from "@homexo/shared";
import CustomerAccess from "../CustomerAccess";
import { api } from "../../api";
import useRetryDelay from "../../ui/useRetryDelay";
import "../../ui/privacy.css";

const date = (value: string) => new Date(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const open = (item: PrivacyRequestRecord) => item.status === "submitted" || item.status === "in_review";

export default function PrivacyCenter() {
  const [notice, setNotice] = useState<PrivacyNotice | null>(null), [error, setError] = useState("");
  const load = useCallback(async () => { try { setNotice(await api.privacyNotice()); setError(""); } catch { setError("The privacy notice could not load. Please try again."); } }, []);
  useEffect(() => { load(); }, [load]);
  return <MainContent className="privacy-center"><header><div className="eyebrow">Your information</div><h1>Privacy requests</h1><p>Ask for a copy of your information, a correction, or deletion. Track the team&apos;s review here.</p></header>
    <section className="privacy-card privacy-notice"><h2>How your request is handled</h2>{notice ? <><ul>{notice.summary.map(text => <li key={text}>{text}</li>)}</ul><p className="privacy-muted">Notice version: {notice.version}</p></> : error ? <div role="alert"><p>{error}</p><button className="btn small light" onClick={load}>Reload notice</button></div> : <p role="status">Loading privacy notice…</p>}</section>
    <CustomerAccess intro="Sign in with your verified phone to send and track privacy requests for your account."><MyPrivacyRequests notice={notice} /></CustomerAccess>
  </MainContent>;
}

function MyPrivacyRequests({ notice }: { notice: PrivacyNotice | null }) {
  const [data, setData] = useState<PrivacyRequestsPage | null>(null), [page, setPage] = useState(1);
  const [kind, setKind] = useState<PrivacyKind>("access"), [details, setDetails] = useState(""), [ticket, setTicket] = useState("");
  const [error, setError] = useState(""), [listError, setListError] = useState(""), [message, setMessage] = useState("");
  const [sending, setSending] = useState(false), [withdrawing, setWithdrawing] = useState(""), [confirm, setConfirm] = useState("");
  const key = useRef<string | null>(null), sequence = useRef(0), retry = useRetryDelay();
  const load = useCallback(async (next = page) => {
    const request = ++sequence.current;
    try { const result = await api.privacyRequests(next); if (request === sequence.current) { setData(result); setListError(""); } }
    catch (e) { if (request === sequence.current) setListError(`Could not refresh your requests. ${e instanceof Error ? e.message : "Please try again."}`); }
  }, [page]);
  useEffect(() => { load(); const timer = window.setInterval(() => { if (!document.hidden) load(); }, 30000); return () => clearInterval(timer); }, [load]);
  function changed() { key.current = null; setError(""); setMessage(""); }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!notice || sending || retry.seconds > 0) return;
    setSending(true); setError(""); setMessage("");
    try {
      key.current ??= crypto.randomUUID();
      const created = await api.createPrivacyRequest({ kind, details: details.trim(), ticket_number: ticket.trim() || null, submission_key: key.current, notice_version: notice.version });
      setDetails(""); setTicket(""); key.current = null; setMessage(`Request submitted: ${created.reference}. Follow its progress below.`); setPage(1); await load(1);
    } catch (e) { retry.record(e); setError(e instanceof Error ? e.message : "Could not submit your request."); await load(1); }
    finally { setSending(false); }
  }
  async function withdraw(item: PrivacyRequestRecord) {
    setWithdrawing(item.id); setListError("");
    try { await api.withdrawPrivacyRequest(item.id, item.revision); setConfirm(""); await load(); }
    catch (e) { setListError(`Could not withdraw your request. ${e instanceof Error ? e.message : "Please try again."}`); }
    finally { setWithdrawing(""); }
  }
  return <div className="privacy-sections"><section className="privacy-card"><h2>Send a privacy request</h2><form className="privacy-form" onSubmit={submit}><fieldset disabled={sending}>
    <label htmlFor="privacy-kind">What would you like help with?<select id="privacy-kind" value={kind} onChange={e => { changed(); setKind(e.target.value as PrivacyKind); }}>{Object.entries(PRIVACY_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label htmlFor="privacy-ticket">Ticket number (optional)<input id="privacy-ticket" maxLength={40} placeholder="Leave blank for your account generally" value={ticket} onChange={e => { changed(); setTicket(e.target.value); }} /></label>
    <label htmlFor="privacy-details">Tell us what information or change you are requesting<textarea id="privacy-details" rows={4} minLength={10} maxLength={2000} required value={details} onChange={e => { changed(); setDetails(e.target.value); }} /></label>
    <p className="privacy-muted">Include enough detail to identify the information. Keep passwords, sign-in codes and card details out of this form.</p>
    <button className="btn" disabled={sending || !notice || retry.seconds > 0}>{sending ? "Sending…" : retry.seconds > 0 ? `Try again in ${retry.seconds >= 60 ? `${Math.ceil(retry.seconds / 60)} min` : `${retry.seconds}s`}` : "Send privacy request"}</button></fieldset>
    {error && <p className="privacy-error" role="alert">{error}</p>}{message && <p className="privacy-success" role="status">{message}</p>}
  </form></section>
  <section className="privacy-history"><div className="privacy-heading"><div><h2>Your privacy requests</h2><p className="privacy-muted">Progress refreshes every 30 seconds while this page is visible.</p></div><button className="btn small light" onClick={() => load()}>Refresh progress</button></div>
    {listError && <p className="privacy-error" role="alert">{listError} {data ? "The last loaded progress is shown below." : ""}</p>}
    {!data ? <p role="status">Loading your requests…</p> : data.items.length === 0 ? <div className="privacy-card"><p>You have not sent a privacy request yet.</p></div> : data.items.map(item => <article className="privacy-card" key={item.id}><div className="privacy-heading"><h3>{PRIVACY_KIND_LABELS[item.kind]}</h3><span className={`privacy-badge ${item.overdue ? "warn" : ""}`}>{PRIVACY_STATUS_LABELS[item.status]}</span></div><p className="privacy-reference">{item.reference}</p><p className="privacy-muted">Sent {date(item.created_at)} · Review target {date(item.due_at)}{item.ticket_number ? ` · ${item.ticket_number}` : ""}{item.overdue ? " · Target passed; the team is still reviewing" : ""}</p>
      <p className="privacy-text">{item.details}</p>{item.customer_response && <section className="privacy-response"><h4>Response from the team</h4><p className="privacy-text">{item.customer_response}</p></section>}
      {item.resolution && <p><b>{PRIVACY_RESOLUTION_LABELS[item.resolution]}</b>{item.retention_reason ? ` · ${PRIVACY_REASON_LABELS[item.retention_reason]}` : ""}</p>}
      {open(item) && (confirm === item.id ? <div className="privacy-confirm"><p>Withdraw this request from review?</p><button className="btn small light" disabled={!!withdrawing} onClick={() => withdraw(item)}>{withdrawing ? "Withdrawing…" : "Confirm withdrawal"}</button><button className="text-link" disabled={!!withdrawing} onClick={() => setConfirm("")}>Keep request</button></div> : <button className="text-link" onClick={() => setConfirm(item.id)}>Withdraw request</button>)}
    </article>)}
    {data && (data.total > data.page_size || page > 1) && <div className="privacy-pager"><button className="btn small light" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button><span>Page {page} · {data.total} requests</span><button className="btn small light" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Next</button></div>}
  </section></div>;
}
