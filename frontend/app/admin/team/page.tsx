"use client";

import { useCallback, useEffect, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, timeAgo, type StaffUser, type TeamMember } from "../api";

// Who on the team can take a call now. Numbers here are for the team only; customers never see them.
export default function TeamPage() {
  const { user, setUser, onError } = useStaff();
  const [team, setTeam] = useState<TeamMember[] | null>(null);
  const [available, setAvailable] = useState(user.available_for_calls);
  const [note, setNote] = useState(user.availability_note ?? "");
  const [phone, setPhone] = useState(user.phone ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const load = useCallback(() => {
    adminFetch<{ items: TeamMember[] }>("/admin/team").then((r) => setTeam(r.items)).catch((e) => setError(onError(e)));
  }, [onError]);
  useEffect(load, [load]);
  useEffect(() => setAvailable(user.available_for_calls), [user.available_for_calls]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const me = await adminFetch<StaffUser>("/admin/me/availability", {
        method: "PUT", body: JSON.stringify({ available, note: note.trim() || null, phone: phone.trim() }),
      });
      setUser(me);
      setSaved(me.available_for_calls ? "You're shown as taking team calls." : "You're shown as not taking calls.");
      load();
    } catch (e) {
      setError(onError(e).replace(/^phone: /, ""));
    } finally {
      setBusy(false);
    }
  }

  const free = team?.filter((m) => m.available_for_calls) ?? [];
  return (
    <>
      <header className="admin-head">
        <div>
          <div className="eyebrow">Inside the team</div>
          <h1>Team calls</h1>
        </div>
      </header>

      <div className="staff-layout">
        <section className="admin-card">
          <h2>{team ? `${free.length} of ${team.length} taking calls now` : "Loading…"}</h2>
          <ul className="team-list">
            {team?.map((m) => (
              <li key={m.id} className={m.available_for_calls ? "on" : undefined}>
                <span className="dot" aria-hidden />
                <div>
                  <b>{m.name}{m.id === user.id ? " (you)" : ""}</b>
                  <small>
                    {m.available_for_calls ? "Taking calls" : "Not taking calls"}{m.availability_note ? ` · ${m.availability_note}` : ""}
                    {m.lawyer ? " · Lawyer" : ""}{m.availability_updated_at ? ` · updated ${timeAgo(m.availability_updated_at)}` : ""}
                  </small>
                </div>
                {m.available_for_calls && m.phone && m.id !== user.id && <a className="btn small" href={`tel:${m.phone.replace(/\s/g, "")}`}>Call {m.phone}</a>}
              </li>
            ))}
          </ul>
        </section>

        <form className="admin-card admin-form" onSubmit={save}>
          <h2>Your availability</h2>
          <label className="admin-check">
            <input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} /> I can take calls from the team now
          </label>
          <label>Note for the team (optional)
            <input maxLength={120} placeholder="e.g. Till 6 pm, or only urgent matters" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <label>Your mobile number
            <input type="tel" inputMode="tel" autoComplete="tel" placeholder="+91 98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          {error && <p className="admin-error" role="alert">{error}</p>}
          {saved && <p className="admin-notice" role="status">{saved}</p>}
          <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          <small className="admin-footnote">Only the Homexo team sees your number. Customers never get it: meeting invites, reminders and the booking pages show your name only, and messages come from the Homexo WhatsApp number. The same number gets your urgent task alerts and daily agenda.</small>
        </form>
      </div>
    </>
  );
}
