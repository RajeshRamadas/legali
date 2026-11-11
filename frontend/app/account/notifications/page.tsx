"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type NotificationChoices, type NotificationPreferences } from "@homexo/shared";
import { api } from "../../api";
import MainContent from "../../ui/MainContent";
import CustomerAccess from "../CustomerAccess";
import useRetryDelay from "../../ui/useRetryDelay";
import "./notifications.css";

const channels = { email: "Email alerts", sms: "SMS alerts", whatsapp: "WhatsApp alerts" } as const;
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

export default function NotificationSettingsPage() {
  return <MainContent className="notification-settings"><header><div className="eyebrow">Stay informed</div><h1>Notification preferences</h1><p>Choose how you receive automated updates about your requests and consultations.</p></header>
    <CustomerAccess intro="Sign in with the phone used for your requests to manage notification preferences."><Preferences /></CustomerAccess>
  </MainContent>;
}

function Preferences() {
  const [saved, setSaved] = useState<NotificationPreferences | null>(null), [draft, setDraft] = useState<NotificationChoices | null>(null);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [conflict, setConflict] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const guard = useRef(false), sequence = useRef(0), retry = useRetryDelay();
  const feedback = useRef<HTMLParagraphElement>(null);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setLoading(true); setError(""); setNotice("");
    try {
      const value = await api.notificationPreferences();
      if (sequence.current === request) { setSaved(value); setDraft({ email: value.email, sms: value.sms, whatsapp: value.whatsapp, revision: value.revision }); setConflict(false); }
    } catch (error) { if (sequence.current === request) setError(error instanceof Error ? error.message : "Your saved choices could not load."); }
    finally { if (sequence.current === request) setLoading(false); }
  }, []);
  const invalidate = useCallback(() => { sequence.current++; }, []);
  useEffect(() => { load(); return invalidate; }, [load, invalidate]);
  useEffect(() => { if (notice || conflict) feedback.current?.focus(); }, [notice, conflict]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft || guard.current || conflict || loading || retry.seconds > 0) return;
    guard.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const value = await api.saveNotificationPreferences(draft);
      setSaved(value); setDraft({ email: value.email, sms: value.sms, whatsapp: value.whatsapp, revision: value.revision });
      setNotice("Your notification preferences are saved. Disabled channels will no longer receive automated alerts.");
    } catch (error) {
      retry.record(error);
      if (error instanceof ApiError && error.status === 409) setConflict(true);
      setError(error instanceof Error ? error.message : "Your choices could not be saved. Reload saved choices if you are unsure whether the save completed.");
    } finally { guard.current = false; setBusy(false); }
  }
  const changed = !!draft && !!saved && Object.keys(channels).some(channel => draft[channel as keyof typeof channels] !== saved[channel as keyof typeof channels]);
  return <section className="notification-settings-card" aria-label="Automated alert choices">
    <h2>Your alert channels</h2><p>These choices apply to automated case updates, payment updates, consultation reminders and support-reply alerts for your verified account. Support alerts only tell you a reply is available; sign in to read it securely.</p>
    <p id="alert-settings-help">Turning off a channel also cancels queued alerts on that channel. An alert already being sent may still arrive. Turning it back on applies to future alerts; cancelled alerts stay cancelled.</p>
    <p>Sign-in codes still arrive when you request them. Your case updates and meeting links remain available in <Link href="/account">your account</Link>. These settings do not subscribe you to marketing or change how your case team contacts you personally.</p>
    {loading && <p role="status">Loading saved choices…</p>}
    {draft && saved && <form onSubmit={save}><fieldset disabled={busy || loading} aria-describedby="alert-settings-help"><legend>Receive automated updates by</legend>
      {Object.entries(channels).map(([channel, label]) => <label className="notification-choice" key={channel}><input type="checkbox" checked={draft[channel as keyof typeof channels]} onChange={event => { setDraft({ ...draft, [channel]: event.target.checked }); setNotice(""); }} /><span>{label}</span></label>)}
      {!draft.email && !draft.sms && !draft.whatsapp && <p className="notification-settings-note">{changed ? "Save to turn off all automated alert channels." : "All automated alert channels are off."} Check your account regularly for updates and upcoming consultations.</p>}
      <button className="btn" disabled={!changed || conflict || retry.seconds > 0}>{busy ? "Saving…" : retry.seconds > 0 ? `Try again in ${retry.seconds}s` : "Save preferences"}</button>
    </fieldset><p className="notification-settings-meta">{saved.updated_at ? `Last saved ${date(saved.updated_at)}` : "Current alerts are enabled until you save a different choice. Actual delivery depends on the contact details and channels available for your request."}</p></form>}
    {error && <p ref={conflict ? feedback : undefined} tabIndex={-1} role="alert">{error}{conflict && " Your draft is kept. Reloading replaces it with the saved choices."}</p>}
    {notice && <p ref={feedback} tabIndex={-1} role="status">{notice}</p>}
    <button className="btn light" disabled={busy || loading} onClick={load}>{draft ? "Reload saved choices" : "Retry loading choices"}</button>
  </section>;
}
