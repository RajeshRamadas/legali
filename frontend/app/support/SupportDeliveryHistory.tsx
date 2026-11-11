"use client";
import { useEffect, useRef, useState } from "react";
import { adminFetch, type SupportDeliveryPage } from "../admin/api";

const events = { customer_reply: "Reply available", support_deadline: "Response target missed", support_escalation: "Response target escalated" };
const statuses = { queued: "Queued", sent: "Accepted by provider", delivered: "Delivery confirmed", failed: "Failed", cancelled: "Cancelled" };
const channels = { email: "Email", sms: "SMS", whatsapp: "WhatsApp" };
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });

export default function SupportDeliveryHistory({ requestId, onError }: { requestId: string; onError: (error: unknown) => string }) {
  const [open, setOpen] = useState(false), [data, setData] = useState<SupportDeliveryPage | null>(null);
  const [recipient, setRecipient] = useState("all"), [status, setStatus] = useState("all"), [channel, setChannel] = useState("all"), [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false), [error, setError] = useState(""), [refresh, setRefresh] = useState(0);
  const errorHandler = useRef(onError);
  useEffect(() => { errorHandler.current = onError; }, [onError]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true); setData(null); setError("");
    adminFetch<SupportDeliveryPage>(`/admin/support-requests/${requestId}/deliveries?recipient=${recipient}&status=${status}&channel=${channel}&page=${page}`)
      .then(result => { if (active) setData(result); })
      .catch(error => { if (active) setError(errorHandler.current(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, requestId, recipient, status, channel, page, refresh]);
  return <details className="support-delivery" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Delivery history</summary>
    <section aria-label="Support delivery history" aria-busy={loading}>
      <p>Read-only delivery records. Refreshing or filtering keeps your unsent reply and notes. Accepted by provider does not confirm delivery or reading. Queued notices may already be in progress.</p>
      <p>Contacts, message contents and provider responses stay private. Review uncertain outcomes before arranging another message through the normal workflow.</p>
      <div className="support-filters">
        <label>Delivery recipient<select value={recipient} onChange={event => { setRecipient(event.target.value); setPage(1); }}><option value="all">All recipients</option><option value="customer">Customer</option><option value="administrator">Administrators</option></select></label>
        <label>Delivery status<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="all">All delivery states</option>{Object.entries(statuses).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>Delivery channel<select value={channel} onChange={event => { setChannel(event.target.value); setPage(1); }}><option value="all">All channels</option>{Object.entries(channels).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
      </div>
      <button type="button" className="btn small light" disabled={loading} onClick={() => setRefresh(value => value+1)}>Refresh delivery history</button>
      {loading && <p role="status">Loading delivery history…</p>}
      {error && <p role="alert" className="support-error">{error} Use Refresh delivery history to retry. Your conversation draft is unchanged.</p>}
      {data && <>
        <p className="support-muted">Customer reply notices: {data.configuration.customer_replies_enabled ? "enabled" : "off"}. Staff email notices: {data.configuration.staff_email === "unconfigured" ? "not configured" : data.configuration.staff_email === "enabled" ? "enabled" : "off"}. Channel setup: {Object.entries(data.configuration.channels).map(([name, configured]) => `${channels[name as keyof typeof channels]} ${configured ? "configured" : "not configured"}`).join(" · ")}. Configuration is current; records below describe past delivery decisions.</p>
        {!data.items.length ? <p>No delivery records match this view.</p> : <ol className="support-delivery-list">{data.items.map(item => <li key={item.id}>
          <div className="support-row"><strong>{events[item.event]}</strong><span>{statuses[item.status]}</span></div>
          <p>{item.recipient_kind === "customer" ? "Customer" : `Administrator · ${item.recipient_name}`} · {channels[item.channel]} · {item.attempts} {item.attempts === 1 ? "attempt" : "attempts"}</p>
          <p className="support-muted">Created {date(item.created_at)}{item.last_attempt_at ? ` · Last attempt ${date(item.last_attempt_at)}` : ""}{item.status === "queued" && item.scheduled_for ? ` · Scheduled ${date(item.scheduled_for)}` : ""}{item.delivered_at ? ` · Delivery confirmed ${date(item.delivered_at)}` : ""}</p>
          {item.reason && <p>{item.reason}</p>}
          <small className="support-muted">Delivery reference: {item.id}</small>
        </li>)}</ol>}
        {(data.total > data.page_size || page > 1) && <nav aria-label="Delivery history pages" className="support-row"><button type="button" className="btn small light" disabled={loading || page <= 1} onClick={() => setPage(value => value-1)}>Previous deliveries</button><span>Page {page} · {data.total} records</span><button type="button" className="btn small light" disabled={loading || page*data.page_size >= data.total} onClick={() => setPage(value => value+1)}>Next deliveries</button></nav>}
      </>}
    </section>
  </details>;
}
