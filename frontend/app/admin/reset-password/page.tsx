"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { adminFetch, setToken } from "../api";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setResetToken] = useState(""), [ready, setReady] = useState(false);
  const [password, setPassword] = useState(""), [confirm, setConfirm] = useState(""), [code, setCode] = useState("");
  const [error, setError] = useState(""), [done, setDone] = useState(false), [busy, setBusy] = useState(false);
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    setResetToken(new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
    window.history.replaceState(null, "", window.location.pathname); setReady(true);
  }, []);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError("");
    if (password !== confirm) { setError("The passwords do not match."); return; }
    setBusy(true);
    try {
      await adminFetch("/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token, password, code }) });
      setToken(null); setResetToken(""); setPassword(""); setConfirm(""); setCode(""); setDone(true);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not reset your password."); }
    finally { setBusy(false); }
  }
  return <div className="admin-signin"><div className="admin-card signin-card"><h1>{done ? "Password updated" : "Choose a new password"}</h1>
    {done ? <p>Your staff sessions have been signed out on every device. Sign in again to open the workspace.</p> : !ready ? <p>Opening your reset link…</p> : !token ? <p>This link is missing or has already been opened in this tab. Request a new link from staff sign-in.</p> : <form className="mfa-enrollment" onSubmit={submit}>
      <label>New password<input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label>Confirm new password<input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
      <label>Authenticator or recovery code (if enabled)<input autoComplete="one-time-code" maxLength={64} value={code} onChange={e => setCode(e.target.value)} /></label>
      {error && <p className="admin-error" role="alert">{error}</p>}<button className="btn" disabled={busy}>{busy ? "Updating…" : "Update password"}</button>
    </form>}
    <button className="admin-link" onClick={() => router.push("/admin")}>Back to staff sign-in</button>
  </div></div>;
}
