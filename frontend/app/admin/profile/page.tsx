"use client";

import { useCallback, useEffect, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";

type Hours = Record<string, [string, string][]>;
// Mirrors _staff_profile_view in backend/app/lawyers.py.
type Profile = {
  user_id: string;
  name: string;
  exists: boolean;
  slug: string | null;
  headline: string;
  bio: string;
  specialisations: string[];
  languages: string[];
  courts: string[];
  experience_years: number;
  consultation_fee: number;
  consultation_minutes: number;
  city: string;
  locality: string | null;
  bar_enrolment: string | null;
  education: string | null;
  weekly_hours: Hours;
  is_listed: boolean;
  public_url: string | null;
  options: { specialisations: string[]; languages: string[] };
  timezone: string;
};
type RosterItem = { user_id: string; name: string; listed: boolean; slug: string | null };

const DAYS: [string, string][] = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];

function Chips({ label, options, value, onChange }: { label: string; options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const [other, setOther] = useState("");
  const all = [...options, ...value.filter((v) => !options.includes(v))];
  return (
    <div className="admin-form">
      <span className="profile-chips-label">{label}</span>
      <div className="profile-chips">
        {all.map((option) => {
          const on = value.includes(option);
          return <button type="button" key={option} className={on ? "on" : undefined} aria-pressed={on} onClick={() => onChange(on ? value.filter((v) => v !== option) : [...value, option])}>{option}</button>;
        })}
        <input placeholder="Add other…" value={other} onChange={(e) => setOther(e.target.value)} aria-label={`Add another ${label.toLowerCase()}`}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (other.trim() && !value.includes(other.trim())) onChange([...value, other.trim()]); setOther(""); } }} />
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { user, onError } = useStaff();
  const [roster, setRoster] = useState<RosterItem[]>([]);
  const [who, setWho] = useState(user.id);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setNotice("");
    adminFetch<Profile>(`/admin/lawyer-profile?user_id=${who}`).then((p) => { setProfile(p); setError(""); }).catch((e) => setError(onError(e)));
    if (user.role === "admin") adminFetch<{ items: RosterItem[] }>("/admin/lawyer-profiles").then((r) => setRoster(r.items)).catch(onError);
  }, [who, user.role, onError]);
  useEffect(load, [load]);

  if (!profile) return <>{error ? <p className="admin-error">{error}</p> : <p className="admin-empty">Loading…</p>}</>;
  const set = (patch: Partial<Profile>) => setProfile({ ...profile, ...patch });
  const setDay = (day: string, ranges: [string, string][]) => {
    const hours = { ...profile.weekly_hours };
    if (ranges.length) hours[day] = ranges; else delete hours[day];
    set({ weekly_hours: hours });
  };

  async function save(listed: boolean) {
    if (!profile) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const { headline, bio, specialisations, languages, courts, experience_years, consultation_fee, consultation_minutes, city, locality, bar_enrolment, education, weekly_hours } = profile;
      const saved = await adminFetch<Profile>(`/admin/lawyer-profile?user_id=${who}`, {
        method: "PUT",
        body: JSON.stringify({ headline, bio, specialisations, languages, courts, experience_years, consultation_fee, consultation_minutes, city, locality, bar_enrolment, education, weekly_hours, is_listed: listed }),
      });
      setProfile(saved);
      setNotice(listed ? "Saved. The profile is live and customers can book open slots." : "Saved. The profile is hidden from customers.");
      if (user.role === "admin") adminFetch<{ items: RosterItem[] }>("/admin/lawyer-profiles").then((r) => setRoster(r.items)).catch(onError);
    } catch (e) {
      setError(onError(e));
    } finally {
      setBusy(false);
    }
  }

  const mine = who === user.id;
  return (
    <>
      <header className="admin-head">
        <div><div className="eyebrow">Find a lawyer listing</div><h1>{mine ? "My lawyer profile" : `${profile.name}'s profile`}</h1></div>
        <div className="calendar-controls">
          {user.role === "admin" && roster.length > 0 && (
            <select value={who} onChange={(e) => setWho(e.target.value)} aria-label="Whose profile">
              {roster.map((r) => <option key={r.user_id} value={r.user_id}>{r.user_id === user.id ? "Me" : r.name}{r.listed ? " · listed" : ""}</option>)}
            </select>
          )}
          {profile.is_listed && profile.public_url && <a className="btn small light" href={`/lawyers/${profile.slug}`} target="_blank" rel="noreferrer">View public profile ↗</a>}
        </div>
      </header>
      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}

      <div className="staff-layout">
        <div className="ticket-main">
          <section className="admin-card admin-form">
            <h2>About</h2>
            <label>Headline<input maxLength={160} placeholder="e.g. Property title, RERA and builder disputes" value={profile.headline} onChange={(e) => set({ headline: e.target.value })} /></label>
            <label>About you<textarea rows={5} maxLength={3000} placeholder="What you help clients with, and how." value={profile.bio} onChange={(e) => set({ bio: e.target.value })} /></label>
            <div className="form-row">
              <label>Education<input maxLength={300} value={profile.education ?? ""} onChange={(e) => set({ education: e.target.value })} /></label>
              <label>Bar enrolment no.<input maxLength={60} placeholder="KAR/1234/2012" value={profile.bar_enrolment ?? ""} onChange={(e) => set({ bar_enrolment: e.target.value })} /></label>
            </div>
            <label>Courts you practise at (comma separated)<input value={profile.courts.join(", ")} onChange={(e) => set({ courts: e.target.value.split(",").map((c) => c.trimStart()) })} onBlur={() => set({ courts: profile.courts.map((c) => c.trim()).filter(Boolean) })} /></label>
          </section>

          <section className="admin-card">
            <h2>Practice</h2>
            <Chips label="Specialisations" options={profile.options.specialisations} value={profile.specialisations} onChange={(v) => set({ specialisations: v.slice(0, 8) })} />
            <div style={{ height: 12 }} />
            <Chips label="Languages" options={profile.options.languages} value={profile.languages} onChange={(v) => set({ languages: v.slice(0, 8) })} />
            <div className="admin-form" style={{ marginTop: 12 }}>
              <div className="form-row">
                <label>Experience (years)<input type="number" min={0} max={70} value={profile.experience_years} onChange={(e) => set({ experience_years: Number(e.target.value) })} /></label>
                <label>City<input maxLength={80} value={profile.city} onChange={(e) => set({ city: e.target.value })} /></label>
              </div>
              <label>Area / locality<input maxLength={120} placeholder="e.g. Jayanagar" value={profile.locality ?? ""} onChange={(e) => set({ locality: e.target.value })} /></label>
            </div>
          </section>
        </div>

        <div className="ticket-side">
          <section className="admin-card admin-form">
            <h2>Consultation</h2>
            <div className="form-row">
              <label>Fee (₹)<input type="number" min={0} max={100000} step={100} value={profile.consultation_fee} onChange={(e) => set({ consultation_fee: Number(e.target.value) })} /></label>
              <label>Minutes
                <select value={profile.consultation_minutes} onChange={(e) => set({ consultation_minutes: Number(e.target.value) })}>
                  {[15, 20, 30, 45, 60].map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
            </div>
          </section>

          <section className="admin-card">
            <h2>Weekly hours</h2>
            <p className="admin-footnote" style={{ marginTop: -6, marginBottom: 10 }}>Customers can book slots in these hours ({profile.timezone}). Your existing meetings are blocked out automatically.</p>
            <div className="hours-editor">
              {DAYS.map(([key, label]) => {
                const ranges = profile.weekly_hours[key] ?? [];
                return (
                  <div key={key} className="hours-day">
                    <label className="hours-toggle"><input type="checkbox" checked={ranges.length > 0} onChange={(e) => setDay(key, e.target.checked ? [["10:00", "13:00"]] : [])} />{label}</label>
                    <div className="hours-ranges">
                      {ranges.length === 0 && <span className="muted">Not available</span>}
                      {ranges.map(([from, to], i) => (
                        <div key={i} className="hours-range">
                          <input type="time" value={from} step={900} onChange={(e) => setDay(key, ranges.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} aria-label={`${label} from`} />
                          <span>–</span>
                          <input type="time" value={to} step={900} onChange={(e) => setDay(key, ranges.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} aria-label={`${label} to`} />
                          <button type="button" className="admin-link" onClick={() => setDay(key, ranges.filter((_, j) => j !== i))} aria-label="Remove">✕</button>
                        </div>
                      ))}
                      {ranges.length > 0 && ranges.length < 4 && <button type="button" className="admin-link" onClick={() => setDay(key, [...ranges, ["15:00", "18:00"]])}>+ Add hours</button>}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="admin-card admin-form">
            <h2>Listing</h2>
            <p>{profile.is_listed ? "Live on Find a lawyer. Customers can see this profile and book open slots." : "Hidden. Customers can't see or book this profile."}</p>
            <div className="form-actions">
              <button className="btn small" disabled={busy} onClick={() => save(true)}>{profile.is_listed ? "Save" : "Save and go live"}</button>
              {profile.is_listed
                ? <button className="admin-link" disabled={busy} onClick={() => save(false)}>Hide from customers</button>
                : <button className="admin-link" disabled={busy} onClick={() => save(false)}>Save as draft</button>}
            </div>
            <small className="admin-footnote">Bookings arrive as tickets assigned to {mine ? "you" : profile.name}, with the meeting on the calendar and WhatsApp reminders for both sides. Customers see your name, never your mobile number.</small>
          </section>
        </div>
      </div>
    </>
  );
}
