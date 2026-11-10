"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { SupportRecord } from "@homexo/shared";
import { useStaff } from "../admin/AdminShell";
import { adminFetch } from "../admin/api";

type Owner = { id: string; name: string };
type History = { items: { id: string; actor: string; at: string; revision: number; owner: Owner | null; previous_owner: Owner | null }[]; total: number; page_size: number };
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });

export default function SupportAssignment({ item, disabled, onBusy, onAssigned, onReload }: {
  item: SupportRecord; disabled: boolean; onBusy: (busy: boolean) => void;
  onAssigned: (record: SupportRecord) => void; onReload: () => void;
}) {
  const { user, onError } = useStaff();
  const [owners, setOwners] = useState<Owner[] | null>(null), [ownerError, setOwnerError] = useState("");
  const [selected, setSelected] = useState(item.assignee?.id ?? ""), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [history, setHistory] = useState<History | null>(null), [page, setPage] = useState(1), [historyError, setHistoryError] = useState("");
  const guard = useRef(false), feedback = useRef<HTMLParagraphElement>(null);
  const loadOwners = useCallback(async () => {
    try { setOwners((await adminFetch<{ items: Owner[] }>("/admin/support-requests/owners")).items); setOwnerError(""); }
    catch (error) { setOwnerError(onError(error)); }
  }, [onError]);
  const loadHistory = useCallback(async () => {
    try { setHistory(await adminFetch<History>(`/admin/support-requests/${item.id}/assignments?page=${page}`)); setHistoryError(""); }
    catch (error) { setHistoryError(onError(error)); }
  }, [item.id, page, onError]);
  useEffect(() => { loadOwners(); }, [loadOwners]);
  useEffect(() => { loadHistory(); }, [loadHistory, item.revision]);
  useEffect(() => { setSelected(item.assignee?.id ?? ""); }, [item.assignee?.id]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  async function assign(owner: string) {
    if (guard.current || disabled) return;
    guard.current = true; setBusy(true); onBusy(true); setError(""); setNotice("");
    try {
      const record = await adminFetch<SupportRecord>(`/admin/support-requests/${item.id}/assignment`, {
        method: "PATCH", body: JSON.stringify({ revision: item.revision, assignee_user_id: owner || null }),
      });
      onAssigned(record); setPage(1); setNotice("Support owner saved. Reply and internal-note drafts are kept.");
    } catch (error) { setError(`${onError(error)} Your owner choice and conversation drafts are kept. Reloading the latest request replaces drafts.`); }
    finally { guard.current = false; setBusy(false); onBusy(false); }
  }
  return <section className="support-assignment" aria-label="Support ownership">
    <h3>Support owner</h3><p>{item.assignee ? `${item.assignee.name}${item.assignee.active ? "" : " · No longer an active administrator"}` : "Unassigned"}</p>
    <p className="support-muted">Ownership is private to administrators. It does not reply to the customer, change deadlines or send a notification.</p>
    <fieldset disabled={disabled || busy}><label>Assign support owner<select value={selected} disabled={!owners} onChange={event => setSelected(event.target.value)}>
      <option value="">Unassigned</option>
      {item.assignee && owners && !owners.some(owner => owner.id === item.assignee?.id) && <option value={item.assignee.id} disabled>{item.assignee.name} · unavailable</option>}
      {owners?.map(owner => <option key={owner.id} value={owner.id}>{owner.name}</option>)}
    </select></label><div className="support-row">
      <button type="button" className="btn small light" disabled={!owners || selected === (item.assignee?.id ?? "")} onClick={() => assign(selected)}>{busy ? "Saving owner…" : "Save support owner"}</button>
      <button type="button" className="btn small light" disabled={item.assignee?.id === user.id} onClick={() => assign(user.id)}>Assign to me</button>
    </div></fieldset>
    {ownerError && <p role="alert">{ownerError} <button type="button" className="text-link" onClick={loadOwners}>Reload owner choices</button></p>}
    {error && <div role="alert"><p>{error}</p><button type="button" className="btn small light" disabled={busy || disabled} onClick={onReload}>Reload latest request</button></div>}
    {notice && <p role="status" ref={feedback} tabIndex={-1}>{notice}</p>}
    <details><summary>Private assignment history</summary>
      {historyError && <p role="alert">{historyError} <button type="button" className="text-link" onClick={loadHistory}>Retry assignment history</button></p>}
      {!history ? <p role="status">Loading assignment history…</p> : !history.items.length ? <p>No ownership changes recorded.</p> : <ol className="support-assignment-history">{history.items.map(event => <li key={event.id}><strong>{event.previous_owner?.name || "Unassigned"} → {event.owner?.name || "Unassigned"}</strong><p>{event.actor} · {date(event.at)}</p></li>)}</ol>}
      {history && (history.total > history.page_size || page > 1) && <nav className="support-row" aria-label="Assignment history pages"><button type="button" className="btn small light" disabled={page === 1 || busy} onClick={() => setPage(value => value-1)}>Previous assignments</button><span>Page {page}</span><button type="button" className="btn small light" disabled={page*history.page_size >= history.total || busy} onClick={() => setPage(value => value+1)}>Next assignments</button></nav>}
    </details>
  </section>;
}
