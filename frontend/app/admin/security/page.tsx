"use client";
import MainContent from "../../ui/MainContent";

import { useCallback, useEffect, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, getToken, setToken, type StaffSession } from "../api";
import StaffSessions from "./StaffSessions";
import MfaEnrollment, { RecoveryCodes } from "../MfaEnrollment";

type Status = { mfa_enabled: boolean; mfa_required: boolean; recovery_codes_remaining: number };
export default function SecurityPage() {
  const { setUser, onError } = useStaff();
  const [status, setStatus] = useState<Status | null>(null);
  const [password, setPassword] = useState(""), [code, setCode] = useState("");
  const [current, setCurrent] = useState(""), [factor, setFactor] = useState(""), [next, setNext] = useState(""), [confirm, setConfirm] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null), [saved, setSaved] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const load = useCallback(() => adminFetch<Status>("/auth/security").then(setStatus).catch(e => setError(onError(e))), [onError]);
  useEffect(() => { load(); }, [load]);
  function accept(session: StaffSession) { setToken(session.access_token); setUser(session.user); }
  function enrolled(session: StaffSession) { accept(session); setNotice("Two-factor sign-in enabled. Your other staff sessions have been signed out."); load(); }
  async function protect(action: "recovery-codes" | "disable") {
    if (!password || !code) { setError("Enter your current password and an authenticator or recovery code."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await adminFetch<StaffSession>(`/auth/mfa/${action}`, { method: "POST", body: JSON.stringify({ password, code }) });
      accept(result); setPassword(""); setCode("");
      if (result.recovery_codes) { setCodes(result.recovery_codes); setSaved(false); }
      setNotice(action === "disable" ? "Two-factor sign-in disabled. Other sessions have been signed out." : "Old recovery codes have been replaced. Other sessions have been signed out.");
      await load();
    } catch (e) { setError(onError(e)); }
    finally { setBusy(false); }
  }
  async function change(e: React.FormEvent) {
    e.preventDefault(); setError(""); setNotice("");
    if (next !== confirm) { setError("The new passwords do not match."); return; }
    setBusy(true);
    try {
      const result = await adminFetch<StaffSession>("/auth/password/change", { method: "POST", body: JSON.stringify({ password: current, new_password: next, code: factor }) });
      accept(result); setCurrent(""); setFactor(""); setNext(""); setConfirm("");
      setNotice("Password changed. Your other staff sessions have been signed out."); await load();
    } catch (e) { setError(onError(e)); }
    finally { setBusy(false); }
  }
  return <MainContent className="staff-security"><header><div className="eyebrow">Your staff account</div><h1>Security</h1><p>Protect your workspace and control your sign-in sessions.</p></header>
    {error && <p className="admin-error" role="alert">{error}</p>}{notice && <p className="staff-security-notice" role="status">{notice}</p>}
    {!status ? <p>Loading security settings…</p> : <>
      <section className="admin-card"><h2>Two-factor sign-in</h2>
        {!status.mfa_enabled ? <MfaEnrollment onEnabled={enrolled} /> : <><p className="security-enabled">Authenticator enabled</p><p>{status.recovery_codes_remaining} recovery codes remaining. A code can be used once if your authenticator is unavailable.</p>
          {codes ? <><RecoveryCodes codes={codes} /><label><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} />I saved these new codes</label><button className="btn" disabled={!saved} onClick={() => setCodes(null)}>Done</button></> : <form className="mfa-enrollment" onSubmit={e => { e.preventDefault(); protect("recovery-codes"); }}>
            <label>Current password<input required type="password" autoComplete="current-password" maxLength={200} value={password} onChange={e => setPassword(e.target.value)} /></label>
            <label>Authenticator or recovery code<input required autoComplete="one-time-code" maxLength={64} value={code} onChange={e => setCode(e.target.value)} /></label>
            <div className="staff-security-actions"><button className="btn small light" disabled={busy}>Generate new recovery codes</button>{!status.mfa_required && <button className="btn small light" type="button" disabled={busy} onClick={() => protect("disable")}>Disable two-factor sign-in</button>}</div>
            {status.mfa_required && <p>Two-factor sign-in is required for administrators.</p>}
          </form>}</>}
      </section>
      <section className="admin-card"><h2>Change password</h2><form className="mfa-enrollment" onSubmit={change}>
        <label>Current password<input type="password" autoComplete="current-password" maxLength={200} required value={current} onChange={e => setCurrent(e.target.value)} /></label>
        <label>New password<input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={next} onChange={e => setNext(e.target.value)} /></label>
        <label>Confirm new password<input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
        {status.mfa_enabled && <label>Authenticator or recovery code<input autoComplete="one-time-code" maxLength={64} required value={factor} onChange={e => setFactor(e.target.value)} /></label>}
        <p>Use at least 12 characters. Changing your password signs out other devices.</p><button className="btn" disabled={busy}>{busy ? "Please wait…" : "Change password"}</button>
      </form></section>
      <StaffSessions key={getToken() ?? ""} />
    </>}
  </MainContent>;
}
