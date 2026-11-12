"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, getToken } from "../api";

type Session = {id:string;browser:string;device:string;created_at:string;last_seen_at:string;expires_at:string;is_current:boolean};
type Sessions = {items:Session[];checked_at:string;max_active:number;activity_interval_seconds:number};
const when = (value:string) => new Date(value).toLocaleString("en-IN", {timeZone:"Asia/Kolkata", dateStyle:"medium", timeStyle:"short"});

export default function StaffSessions() {
  const { signOut, onError } = useStaff();
  const [data, setData] = useState<Sessions|null>(null), [busy, setBusy] = useState(true);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [confirm, setConfirm] = useState("");
  const guard = useRef(false), mounted = useRef(false), feedback = useRef<HTMLParagraphElement>(null), failure = useRef<HTMLDivElement>(null);
  const load = useCallback(async () => {
    const token = getToken(); if (!token || guard.current) return;
    guard.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const value = await adminFetch<Sessions>("/auth/sessions", {cache:"no-store", headers:{Authorization:`Bearer ${token}`}});
      if (mounted.current && getToken() === token) { setData(value); setConfirm(""); }
    } catch (error) { if (mounted.current && getToken() === token) setError(onError(error)); }
    finally { guard.current = false; if (mounted.current) setBusy(false); }
  }, [onError]);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; }; }, [load]);
  useEffect(() => { if (error) failure.current?.focus(); }, [error]);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);

  async function end(id:string) {
    const token = getToken(); if (!token || guard.current) return;
    guard.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const path = id === "others" ? "/auth/sessions/revoke-others" : id === "all" ? "/auth/logout-all" : `/auth/sessions/${encodeURIComponent(id)}/revoke`;
      const result = await adminFetch<{current?:boolean}>(path, {method:"POST", headers:{Authorization:`Bearer ${token}`}});
      if (!mounted.current || getToken() !== token) return;
      if (id === "all" || result.current) { signOut(); return; }
      const value = await adminFetch<Sessions>("/auth/sessions", {cache:"no-store", headers:{Authorization:`Bearer ${token}`}});
      if (mounted.current && getToken() === token) { setData(value); setConfirm(""); setNotice(id === "others" ? "Other active staff sessions have been ended." : "The selected staff session has been ended."); }
    } catch (error) { if (mounted.current && getToken() === token) setError(onError(error)); }
    finally { guard.current = false; if (mounted.current) setBusy(false); }
  }
  return <section className="admin-card staff-session-center" aria-label="Staff sign-in sessions">
    <h2>Sign-in sessions</h2><p>Review your active staff sign-ins. Browser and device labels are approximate; activity updates about every five minutes. Times below use IST.</p>
    <p>Ending a session blocks its next authenticated request. Work already in progress may finish, and downloaded files remain on that device.</p>
    <button className="btn light" disabled={busy} onClick={load}>Refresh staff sessions</button>
    {busy && <p role="status">Loading staff sessions…</p>}
    {error && <div role="alert" tabIndex={-1} ref={failure}><p>{error}</p><p>The last loaded sessions may be out of date. Refresh before trying again.</p></div>}
    {notice && <p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {data && <><p>{data.items.length} active {data.items.length === 1 ? "session" : "sessions"} · Checked {when(data.checked_at)} IST</p>
      <ol className="staff-session-list">{data.items.map(item => <li key={item.id}><article aria-label={`${item.browser} on ${item.device}${item.is_current ? ", current session" : ""}`}>
        <h3>{item.browser} · {item.device}</h3>{item.is_current && <strong>This session</strong>}
        <dl><div><dt>Signed in</dt><dd>{when(item.created_at)} IST</dd></div><div><dt>Last activity</dt><dd>{when(item.last_seen_at)} IST</dd></div><div><dt>Expires</dt><dd>{when(item.expires_at)} IST</dd></div></dl>
        {confirm === item.id ? <div className="staff-security-actions"><p>{item.is_current ? "End this session and return to staff sign-in?" : "End this session? A fresh staff sign-in will be required."}</p><button className="btn small" disabled={busy || !!error} onClick={() => end(item.id)}>Confirm end session</button><button className="btn small light" disabled={busy} onClick={() => setConfirm("")}>Keep session</button></div> : <button className="btn small light" disabled={busy || !!error} onClick={() => setConfirm(item.id)}>{item.is_current ? "Sign out this session" : "End session"}</button>}
      </article></li>)}</ol>
      <div className="staff-security-actions">{data.items.some(item => !item.is_current) && <button className="btn light" disabled={busy || !!error} onClick={() => setConfirm("others")}>Sign out other sessions</button>}<button className="btn light" disabled={busy || !!error} onClick={() => setConfirm("all")}>Sign out all devices</button></div>
      {(confirm === "others" || confirm === "all") && <div className="staff-security-actions"><p>{confirm === "others" ? "End all other staff sessions and keep this one signed in?" : "End all staff sessions, including this one?"}</p><button className="btn" disabled={busy || !!error} onClick={() => end(confirm)}>Confirm {confirm === "others" ? "sign out other sessions" : "sign out all devices"}</button><button className="btn light" disabled={busy} onClick={() => setConfirm("")}>Keep sessions</button></div>}
      <p>Up to {data.max_active} sessions can remain active. A new sign-in beyond that limit ends the oldest active session. Activity does not extend expiry.</p>
    </>}
  </section>;
}
