"use client";
import Link from "next/link";
import { useState } from "react";
import BrandMark from "../ui/BrandMark";
import MainContent from "../ui/MainContent";
import MfaEnrollment from "./MfaEnrollment";
import { adminFetch, setToken, type StaffLogin, type StaffSession, type StaffUser } from "./api";

export default function StaffSignIn({ onSignedIn }: { onSignedIn: (user: StaffUser) => void }) {
  const [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const [code, setCode] = useState(""), [challenge, setChallenge] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [forgot, setForgot] = useState(false), [notice, setNotice] = useState("");
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  function finish(session: StaffSession) { setToken(session.access_token); onSignedIn(session.user); }
  function restart() { setForgot(false); setChallenge(""); setSetupToken(""); setCode(""); setPassword(""); setError(""); setNotice(""); }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(""); setNotice(""); setBusy(true);
    try {
      if (forgot) {
        const r = await adminFetch<{ message: string }>("/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email }) });
        setNotice(r.message);
      } else {
        const r = await adminFetch<StaffLogin>(challenge ? "/auth/login/mfa" : "/auth/login", {
          method: "POST", body: JSON.stringify(challenge ? { token: challenge, code } : { email, password }),
        });
        if ("mfa_required" in r) { setChallenge(r.challenge_token); setPassword(""); }
        else if ("mfa_setup_required" in r) setSetupToken(r.setup_token);
        else finish(r);
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Could not sign in."); }
    finally { setBusy(false); }
  }
  return <MainContent className="admin-signin"><div className="admin-card signin-card">
    <div className="admin-brand dark"><BrandMark /><span>homexo legal<small>Staff workspace</small></span></div>
    <h1>{setupToken ? "Protect your account" : forgot ? "Reset your password" : challenge ? "Two-factor sign-in" : "Sign in"}</h1>
    {setupToken ? <><p>Administrators must set up an authenticator before opening the workspace.</p><MfaEnrollment setupToken={setupToken} initialPassword={password} onEnabled={finish} /><button className="admin-link" onClick={restart}>Back to sign-in</button></> : <form className="mfa-enrollment" onSubmit={submit}>
      <p>{forgot ? "We’ll email a link to your staff account. The link expires in 20 minutes." : challenge ? "Enter your authenticator code or an unused recovery code. This sign-in request expires in five minutes." : <>For Homexo case team members. Customers can track requests on the <Link href="/#track">home page</Link>.</>}</p>
      {challenge ? <label>Authenticator or recovery code<input required autoComplete="one-time-code" maxLength={64} value={code} onChange={e => setCode(e.target.value)} autoFocus /></label> : <><label>Email<input type="email" required autoComplete="username" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>{!forgot && <label>Password<input type="password" required autoComplete="current-password" maxLength={200} value={password} onChange={e => setPassword(e.target.value)} /></label>}</>}
      {error && <p className="admin-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
      <button className="btn" disabled={busy}>{busy ? "Please wait…" : forgot ? "Send reset link" : challenge ? "Verify and sign in" : "Sign in"}</button>
      {forgot || challenge ? <button type="button" className="admin-link" disabled={busy} onClick={restart}>Back to sign-in</button> : <button type="button" className="admin-link" disabled={busy} onClick={() => { setForgot(true); setPassword(""); setError(""); }}>Forgot password?</button>}
    </form>}
  </div></MainContent>;
}
