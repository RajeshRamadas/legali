"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { SUPPORT_KIND_LABELS, SUPPORT_STATUS_LABELS, SUPPORT_STAFF_STATUS_LABELS, type SupportKind, type SupportStatus, type SupportPage, type SupportRecord, type SupportMessages, type SupportSummary } from "@homexo/shared";
import { api } from "../api";
import { adminFetch } from "../admin/api";
import useRetryDelay from "../ui/useRetryDelay";
import { readSession } from "../account/session";
import { openDocuments } from "../documents/ref";
import "./support.css";
import SupportAssignment from "./SupportAssignment";

const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
const message = (error: unknown) => error instanceof Error ? error.message : "The request could not be completed. Please try again.";

function mergeReceipt<T extends SupportSummary>(current: T, next: SupportRecord): T {
  const updates = Math.max(current.customer_update_revision ?? 0, next.customer_update_revision ?? 0);
  const read = Math.max(current.customer_read_revision ?? 0, next.customer_read_revision ?? 0);
  return { ...current, customer_update_revision: updates, customer_read_revision: read, unread_replies: updates-read };
}

export default function SupportDesk({ staff = false, onError }: { staff?: boolean; onError?: (error: unknown) => string }) {
  const labels = staff ? SUPPORT_STAFF_STATUS_LABELS : SUPPORT_STATUS_LABELS;
  const [queue, setQueue] = useState<SupportPage | null>(null), [page, setPage] = useState(1), [refresh, setRefresh] = useState(0);
  const [assignee, setAssignee] = useState("all");
  const [filterOwners, setFilterOwners] = useState<{ id: string; name: string }[]>([]);
  const [status, setStatus] = useState("active"), [kind, setKind] = useState(""), [query, setQuery] = useState(""), [search, setSearch] = useState("");
  const [selected, setSelected] = useState<SupportRecord | null>(null), [messages, setMessages] = useState<SupportMessages | null>(null);
  const [error, setError] = useState(""), [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  const panel = useRef<HTMLElement>(null);
  const fail = (error: unknown) => onError ? onError(error) : message(error);
  useEffect(() => {
    if (!staff) return;
    let active = true;
    adminFetch<{ items: { id: string; name: string }[] }>("/admin/support-requests/owners")
      .then(result => { if (active) setFilterOwners(result.items); }).catch(() => {});
    return () => { active = false; };
  }, [staff]);
  useEffect(() => {
    let active = true;
    const load = staff ? adminFetch<SupportPage>(`/admin/support-requests?status=${status}&assignee=${encodeURIComponent(assignee)}&page=${page}${kind ? `&kind=${encodeURIComponent(kind)}` : ""}&q=${encodeURIComponent(search)}`) : api.supportRequests(page);
    load.then(value => { if (active) { setQueue(value); setError(""); } }).catch(error => { if (active) setError(onError ? onError(error) : message(error)); });
    return () => { active = false; };
  }, [staff, status, kind, search, page, refresh, onError, assignee]);
  useEffect(() => {
    if (staff) return;
    const refreshList = () => setRefresh(value => value+1);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") refreshList(); }, 30000);
    window.addEventListener("hx-support-updated", refreshList);
    window.addEventListener("focus", refreshList);
    return () => { clearInterval(timer); window.removeEventListener("hx-support-updated", refreshList); window.removeEventListener("focus", refreshList); };
  }, [staff]);
  // Invalidate in-flight selections on unmount (including account changes).
  useEffect(() => () => { sequence.current += 1; }, []);
  const selectedId = selected?.id;
  useEffect(() => { if (selectedId && !loading) panel.current?.focus(); }, [selectedId, loading]);
  async function messagePage(value: number) {
    if (!selected) return;
    const current = ++sequence.current;
    try {
      const thread = staff ? await adminFetch<SupportMessages>(`/admin/support-requests/${selected.id}/messages?page=${value}`) : await api.supportMessages(selected.id, value);
      if (current === sequence.current) setMessages(thread);
    } catch (error) { if (current === sequence.current) setError(fail(error)); }
  }
  async function open(id: string, messagePage = 1) {
    const current = ++sequence.current;
    setLoading(true); setError("");
    try {
      const [record, thread] = await Promise.all([
        staff ? adminFetch<SupportRecord>(`/admin/support-requests/${id}`) : api.supportRequest(id),
        staff ? adminFetch<SupportMessages>(`/admin/support-requests/${id}/messages?page=${messagePage}`) : api.supportMessages(id, messagePage),
      ]);
      if (current === sequence.current) { setSelected(record); setMessages(thread); }
    } catch (error) { if (current === sequence.current) setError(fail(error)); }
    finally { if (current === sequence.current) setLoading(false); }
  }
  return <div className="support-grid"><div className="support-sidebar">
    {!staff && <NewRequest onCreated={item => { setPage(1); setRefresh(value => value + 1); open(item.id); }} />}
    <section className="support-card"><div className="support-row"><h2>{staff ? "Requests to review" : "Your support requests"}</h2><button className="btn small light" onClick={() => setRefresh(value => value + 1)}>Refresh list</button></div>
      {staff && <><p>{queue?.filtered_overdue ?? queue?.overdue ?? 0} requests in this view have passed their response target.</p><div className="support-filters">
        <label>Status<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="active">Active requests</option><option value="all">All requests</option>{Object.entries(labels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label>Category<select value={kind} onChange={event => { setKind(event.target.value); setPage(1); }}><option value="">All categories</option>{Object.entries(SUPPORT_KIND_LABELS).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label>Owner<select value={assignee} onChange={event => { setAssignee(event.target.value); setPage(1); }}><option value="all">All owners</option><option value="me">Assigned to me</option><option value="unassigned">Unassigned</option><option value="inactive">Owner unavailable</option>{filterOwners.map(owner => <option key={owner.id} value={owner.id}>{owner.name}</option>)}</select></label>
      </div><form className="support-search" onSubmit={event => { event.preventDefault(); setSearch(query.trim()); setPage(1); }}><label>Subject or reference<input value={query} maxLength={120} onChange={event => setQuery(event.target.value)} /></label><button className="btn small light">Search</button></form></>}
      {!queue ? <p role="status">Loading support requests…</p> : !queue.items.length ? <p>No support requests found.</p> : <ul className="support-list">{queue.items.map(item => <li key={item.id}><button className={selected?.id === item.id ? "selected" : ""} aria-current={selected?.id === item.id ? "true" : undefined} onClick={() => open(item.id)}><strong>{item.subject}</strong>{staff && <span>Owner: {item.assignee?.name || "Unassigned"}{item.assignee && !item.assignee.active ? " · inactive" : ""}</span>}{!staff && !!item.unread_replies && <span className="support-unread">{item.unread_replies} unread {item.unread_replies === 1 ? "reply" : "replies"}</span>}<span>{labels[item.status]}{item.overdue ? " · Response target passed" : ""}</span><small>{item.reference}{staff && item.customer ? ` · ${item.customer.name || "Customer"} · ••••${item.customer.phone_last4}` : ""}</small></button></li>)}</ul>}
      {queue && (queue.total > queue.page_size || page > 1) && <div className="support-row"><button className="btn small light" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous requests</button><span>Page {page}</span><button className="btn small light" disabled={page * queue.page_size >= queue.total} onClick={() => setPage(value => value + 1)}>Next requests</button></div>}
    </section></div>
    <section ref={panel} tabIndex={-1} className="support-card" aria-label="Selected support request" aria-busy={loading}>
      {error && <p role="alert" className="support-error">{error}</p>}
      {loading ? <p role="status">Opening support request…</p> : selected && messages ? <Conversation key={selected.id} item={selected} messages={messages} staff={staff} onError={fail} onAssigned={record => {
        setSelected(current => current?.id === record.id && current.revision <= record.revision ? { ...current, assignee: record.assignee, revision: record.revision, updated_at: record.updated_at } : current);
        setRefresh(value => value+1);
      }} onRead={record => {
        setSelected(current => current?.id === record.id ? mergeReceipt(current, record) : current);
        setQueue(current => current ? { ...current, items: current.items.map(row => row.id === record.id ? mergeReceipt(row, record) : row) } : current);
        window.dispatchEvent(new Event("hx-support-updated"));
      }} onReload={() => open(selected.id)} onPage={messagePage} onSaved={() => { open(selected.id); setRefresh(value => value + 1); }} /> : <><h2>Choose a support request</h2><p>Open a request to read its replies and send an update.</p></>}
    </section>
  </div>;
}

function NewRequest({ onCreated }: { onCreated: (item: SupportRecord) => void }) {
  const [kind, setKind] = useState<SupportKind>("case_update"), [subject, setSubject] = useState(""), [details, setDetails] = useState(""), [ticket, setTicket] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [sent, setSent] = useState("");
  const key = useRef<string | null>(null); const retry = useRetryDelay();
  async function send(event: React.FormEvent) {
    event.preventDefault(); if (busy || retry.seconds) return;
    setBusy(true); setError(""); key.current ||= crypto.randomUUID();
    try {
      const item = await api.createSupportRequest({ kind, subject: subject.trim(), details: details.trim(), ticket_number: ticket.trim() || null, submission_key: key.current });
      key.current = null; setSubject(""); setDetails(""); setTicket(""); setSent(item.reference); onCreated(item);
    } catch (error) { retry.record(error); setError(message(error)); }
    finally { setBusy(false); }
  }
  return <section className="support-card"><h2>Send a support request</h2><p>Don&apos;t include passwords, card details or sign-in codes. Use your case&apos;s document area for files.</p><form className="support-form" onSubmit={send}><fieldset disabled={busy}>
    <label>Category<select value={kind} onChange={event => setKind(event.target.value as SupportKind)}>{Object.entries(SUPPORT_KIND_LABELS).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Subject<input required minLength={5} maxLength={160} value={subject} onChange={event => setSubject(event.target.value)} /></label>
    <label>Case ticket number (optional)<input maxLength={40} placeholder="HX-…" value={ticket} onChange={event => setTicket(event.target.value)} /></label>
    <label>How can we help?<textarea required minLength={10} maxLength={4000} rows={5} value={details} onChange={event => setDetails(event.target.value)} /></label>
    <button className="btn" disabled={busy || retry.seconds > 0}>{busy ? "Sending…" : retry.seconds ? `Try again in ${retry.seconds}s` : "Send support request"}</button>
  </fieldset>{sent && <p role="status">Support request sent: {sent}. Follow its conversation here.</p>}{error && <p role="alert" className="support-error">{error} Your draft is kept here. Check your request list before starting a different submission.<br /><button type="button" className="btn small light" onClick={() => { key.current = null; setError(""); }}>Start a different submission</button></p>}</form></section>;
}

function Conversation({ item, messages, staff, onError, onReload, onPage, onSaved, onRead, onAssigned }: { item: SupportRecord; messages: SupportMessages; staff: boolean; onError: (error: unknown) => string; onReload: () => void; onPage: (page: number) => void; onSaved: () => void; onRead: (record: SupportRecord) => void; onAssigned: (record: SupportRecord) => void }) {
  const labels = staff ? SUPPORT_STAFF_STATUS_LABELS : SUPPORT_STATUS_LABELS;
  const [body, setBody] = useState(""), [note, setNote] = useState(""), [status, setStatus] = useState(item.status), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [assigning, setAssigning] = useState(false);
  const key = useRef<string | null>(null); const retry = useRetryDelay();
  async function send(event: React.FormEvent) {
    event.preventDefault(); if (busy || assigning || retry.seconds) return;
    setBusy(true); setError("");
    try {
      if (staff) await adminFetch(`/admin/support-requests/${item.id}`, { method: "PATCH", body: JSON.stringify({ revision: item.revision, status, customer_response: body.trim(), internal_note: note.trim() }) });
      else { key.current ||= crypto.randomUUID(); await api.replySupportRequest(item.id, body.trim(), key.current); }
      setBody(""); setNote(""); key.current = null; onSaved();
    } catch (error) { retry.record(error); setError(onError(error)); }
    finally { setBusy(false); }
  }
  return <article><div className="support-row"><h2>{item.subject}</h2><span className="support-status">{labels[item.status]}</span></div><p className="support-reference">{item.reference}</p><p>{SUPPORT_KIND_LABELS[item.kind]}{item.ticket_number ? ` · ${item.ticket_number}` : ""}</p>
    <p className="support-text">{item.details}</p><p className="support-muted">Sent {date(item.created_at)}{item.reply_due_at ? ` · Team response target ${date(item.reply_due_at)}` : ""}</p>
    {item.reply_due_at && <p className="support-muted">This is an operational target, not a statutory deadline. The team will reply here.</p>}
    {item.ticket_number && <p><Link href={staff ? `/admin/tickets/${item.ticket_number}` : "/documents"} onClick={() => {
      const session = readSession();
      if (!staff && session && item.ticket_number) openDocuments({ ticket_number: item.ticket_number, contact: session.profile.contact });
    }}>Open {staff ? "case" : "case documents"}</Link></p>}
    {staff && <SupportAssignment item={item} disabled={busy} onBusy={setAssigning} onAssigned={onAssigned} onReload={onReload} />}
    {!staff && item.unread_replies !== undefined && <ReplyReceipt item={item} messages={messages} disabled={busy} onRead={onRead} />}
    <button className="btn small light" onClick={onReload}>Reload conversation</button>
    {!staff && <p className="support-muted">Reloading replaces any unsent reply draft. Marking replies read keeps your draft.</p>}
    <h3>Conversation</h3>{!messages.items.length ? <p>No replies yet.</p> : <ol className="support-messages">{[...messages.items].reverse().map(row => <li key={row.id} className={row.visibility === "internal" ? "internal" : ""}><div><strong>{row.visibility === "internal" ? "Internal note · administrators only" : row.author_type === "staff" ? "Case team" : "Customer"}</strong><time dateTime={row.created_at}>{date(row.created_at)}</time></div><p className="support-text">{row.body}</p></li>)}</ol>}
    {(messages.total > messages.page_size || messages.page > 1) && <div className="support-row"><button className="btn small light" disabled={messages.page * messages.page_size >= messages.total} onClick={() => onPage(messages.page + 1)}>Older messages</button><span>Page {messages.page}</span><button className="btn small light" disabled={messages.page === 1} onClick={() => onPage(messages.page - 1)}>Newer messages</button></div>}
    <form className="support-form" onSubmit={send}><fieldset disabled={busy || assigning}>
      {staff && <label>Request status<select value={status} onChange={event => setStatus(event.target.value as SupportStatus)}>{Object.entries(labels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
      <label>{staff ? "Reply shown to customer" : "Your reply"}<textarea rows={4} required={!staff || (status !== item.status && (status === "resolved" || status === "waiting_for_customer"))} minLength={staff && status !== item.status && (status === "resolved" || status === "waiting_for_customer") ? 10 : 1} maxLength={4000} value={body} onChange={event => setBody(event.target.value)} /></label>
      {staff && <label>Internal note (administrators only)<textarea rows={3} maxLength={4000} value={note} onChange={event => setNote(event.target.value)} /></label>}
      {!staff && item.status === "resolved" && <p>Sending a reply reopens this support request for the team.</p>}
      <button className="btn" disabled={busy || retry.seconds > 0}>{busy ? "Saving…" : retry.seconds ? `Try again in ${retry.seconds}s` : staff ? "Save support update" : "Send reply"}</button>
    </fieldset>{error && <div className="support-error" role="alert"><p>{error}</p><p>Your draft is kept here. Reloading replaces it with the latest saved conversation.</p><button type="button" className="btn small light" onClick={onReload}>Reload latest request</button></div>}</form>
  </article>;
}

function ReplyReceipt({ item, messages, disabled, onRead }: { item: SupportRecord; messages: SupportMessages; disabled: boolean; onRead: (record: SupportRecord) => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const guard = useRef(false), feedback = useRef<HTMLParagraphElement>(null);
  const through = messages.customer_update_revision ?? 0;
  const unread = Math.max(item.customer_update_revision ?? 0, through) - (item.customer_read_revision ?? 0);
  const canRead = messages.page === 1 && through > (item.customer_read_revision ?? 0);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  async function markRead() {
    if (guard.current || !canRead) return;
    guard.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const record = await api.readSupportReplies(item.id, through);
      onRead(record);
      setNotice(record.unread_replies ? "Read status saved. Newer replies remain unread; reload when you are ready." : "Support replies marked as read. Your draft is kept.");
    } catch (error) { setError(message(error)); }
    finally { guard.current = false; setBusy(false); }
  }
  return <section className="support-receipt" aria-label="Support reply read status">
    <p>{unread} unread team {unread === 1 ? "reply" : "replies"}.</p>
    {!!unread && <><p className="support-muted">Mark replies received before this conversation was loaded as read. Newer replies stay unread.</p>
      <button type="button" className="btn small light" disabled={disabled || busy || !canRead} onClick={markRead}>{busy ? "Saving read status…" : "Mark request as read"}</button>
      {!canRead && <p className="support-muted">Reload the newest conversation to review the remaining replies before marking them read.</p>}</>}
    {error && <p role="alert">{error} Read status has not been confirmed. You can retry.</p>}
    {notice && <p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
  </section>;
}
