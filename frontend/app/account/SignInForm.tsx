"use client";

import { useEffect, useState } from "react";
import type { LoginCodeSent } from "@homexo/shared";
import { api } from "../api";
import { signIn } from "./session";

// Phone number, then the 6-digit code sent to it on WhatsApp.
export default function SignInForm({ intro }: { intro?: string }) {
  const [phone, setPhone] = useState("");
  const [sent, setSent] = useState<LoginCodeSent | null>(null);
  const [code, setCode] = useState("");
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  async function sendCode() {
    setError("");
    setBusy(true);
    try {
      const result = await api.startLogin(phone.trim());
      setSent(result);
      setWait(result.resend_after);
      setCode("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't send a code.");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setError("");
    setBusy(true);
    try {
      signIn(await api.verifyLogin(phone.trim(), code.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "That code didn't work.");
      setBusy(false);
    }
  }

  return (
    <form className="dc-card dc-signin" onSubmit={(e) => { e.preventDefault(); if (sent) verify(); else sendCode(); }}>
      <h2>Sign in with your phone</h2>
      <p className="dc-muted" style={{ margin: 0 }}>{intro ?? "We send a 6-digit code on WhatsApp. Your requests, bookings and payments made with this number show up straight away."}</p>
      {!sent ? (
        <label>Mobile number<input required type="tel" inputMode="tel" autoComplete="tel" placeholder="98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
      ) : (
        <>
          <p className="dc-banner" role="status">
            {sent.channel === "whatsapp" ? `We sent a code to ${sent.phone} on WhatsApp.` : `Test mode: no WhatsApp is set up, so your code is ${sent.dev_code}.`}
          </p>
          <label>6-digit code<input required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></label>
        </>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="btn" disabled={busy}>{busy ? "Please wait…" : sent ? "Sign in" : "Send code"}</button>
      {sent && (
        <div className="ac-row">
          <button type="button" className="dc-link ac-plain" onClick={() => { setSent(null); setError(""); }}>Change number</button>
          <button type="button" className="dc-link ac-plain" disabled={wait > 0 || busy} onClick={sendCode}>{wait > 0 ? `Resend in ${wait}s` : "Send a new code"}</button>
        </div>
      )}
    </form>
  );
}
