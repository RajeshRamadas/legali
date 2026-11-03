"use client";
import Image from "next/image";
import { useState } from "react";
import { adminFetch, type StaffSession } from "./api";

export function RecoveryCodes({ codes }: { codes: string[] }) {
  function download() {
    const url = URL.createObjectURL(new Blob(["Homexo Legal staff recovery codes\nEach code works once. Keep these somewhere private.\n\n" + codes.join("\n")], { type: "text/plain" }));
    const link = document.createElement("a"); link.href = url; link.download = "homexo-recovery-codes.txt"; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="staff-recovery"><h2>Save your recovery codes</h2><p>Each code works once if you lose your authenticator. These codes are shown only now. Keep them in a password manager or another private place.</p><ul>{codes.map(code => <li key={code}><code>{code}</code></li>)}</ul><button className="btn light" type="button" onClick={download}>Download recovery codes</button></div>;
}

export default function MfaEnrollment({ initialPassword = "", setupToken, onEnabled }: {
  initialPassword?: string; setupToken?: string; onEnabled: (session: StaffSession) => void;
}) {
  const [password, setPassword] = useState(initialPassword);
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{ secret: string; qr_image: string } | null>(null);
  const [session, setSession] = useState<StaffSession | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      const init = { method: "POST", body: JSON.stringify({ password, code }), ...(setupToken ? { headers: { Authorization: `Bearer ${setupToken}` } } : {}) };
      if (setup) {
        const next = await adminFetch<StaffSession>("/auth/mfa/enable", init);
        setPassword(""); setCode(""); setSetup(null); setSession(next);
      } else setSetup(await adminFetch("/auth/mfa/setup", init));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not set up the authenticator."); }
    finally { setBusy(false); }
  }
  if (session) return <div className="mfa-enrollment"><RecoveryCodes codes={session.recovery_codes ?? []} /><label><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} />I saved my recovery codes</label><button className="btn" disabled={!saved} onClick={() => onEnabled(session)}>Continue to workspace</button></div>;
  return <form className="mfa-enrollment" onSubmit={submit}>
    <p>Use an authenticator app such as Google Authenticator, Microsoft Authenticator or 1Password.</p>
    <label>Current password<input type="password" autoComplete="current-password" required maxLength={200} value={password} onChange={e => setPassword(e.target.value)} /></label>
    {setup && <><Image src={setup.qr_image} alt="Scan this QR code with your authenticator" width={216} height={216} unoptimized /><p>Or enter this setup key manually: <code>{setup.secret}</code></p><p>Then enter a code to finish within 10 minutes.</p><label>Authenticator code<input required inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={6} value={code} onChange={e => setCode(e.target.value)} /></label></>}
    {error && <p className="admin-error" role="alert">{error}</p>}
    <button className="btn" disabled={busy}>{busy ? "Please wait…" : setup ? "Enable two-factor sign-in" : "Set up authenticator"}</button>
    {setup && <button type="button" className="admin-link" disabled={busy} onClick={() => { setSetup(null); setCode(""); }}>Start setup again</button>}
  </form>;
}
