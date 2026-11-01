"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, formatTime, joinable, type Meeting, type StaffUser } from "../api";

const DAY = 86400000;
const dayHead = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" });
const rangeFormat = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" });

function startOfWeek(date: Date): Date {
  const monday = new Date(date);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

function startsIn(meeting: Meeting, now: number): string {
  const minutes = Math.round((new Date(meeting.starts_at).getTime() - now) / 60000);
  if (minutes <= 0) return "Happening now";
  if (minutes < 60) return `Starts in ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `Starts in ${hours}h` : `Starts ${dayHead.format(new Date(meeting.starts_at))}`;
}

export default function CalendarPage() {
  const { user, onError } = useStaff();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  useEffect(()=>{const day=new URLSearchParams(location.search).get("day");if(day&&/^\d{4}-\d{2}-\d{2}$/.test(day)){const date=new Date(day+"T12:00:00+05:30");if(!Number.isNaN(date.getTime()))setWeekStart(startOfWeek(date))}},[]);
  const [lawyer, setLawyer] = useState(user.role === "admin" ? "all" : "me");
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [nextUp, setNextUp] = useState<Meeting | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());

  const load = useCallback(() => {
    const end = new Date(weekStart.getTime() + 7 * DAY);
    const params = new URLSearchParams({ start: weekStart.toISOString(), end: end.toISOString(), lawyer });
    adminFetch<{ items: Meeting[] }>(`/admin/meetings?${params}`).then((r) => { setMeetings(r.items); setError(""); }).catch((e) => setError(onError(e)));
    // Your own next meeting, whatever week is on screen.
    const soon = new URLSearchParams({ start: new Date(Date.now() - 2 * 3600000).toISOString(), end: new Date(Date.now() + 14 * DAY).toISOString(), lawyer: "me" });
    adminFetch<{ items: Meeting[] }>(`/admin/meetings?${soon}`)
      .then((r) => setNextUp(r.items.find((m) => m.status === "scheduled" && new Date(m.ends_at).getTime() > Date.now()) ?? null))
      .catch(() => setNextUp(null));
  }, [weekStart, lawyer, onError]);

  // Keeps the calendar current while it stays open: new bookings, moves and cancellations show up within a minute.
  useEffect(() => {
    load();
    const refresh = setInterval(load, 60000);
    return () => clearInterval(refresh);
  }, [load]);
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 20000);
    return () => clearInterval(tick);
  }, []);
  useEffect(() => {
    if (user.role === "admin") adminFetch<{ items: StaffUser[] }>("/admin/staff").then((r) => setStaff(r.items.filter((s) => s.account_status === "active"))).catch(onError);
  }, [user.role, onError]);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => new Date(weekStart.getTime() + i * DAY)), [weekStart]);
  const today = new Date(now);
  const showLawyer = lawyer === "all";
  const weekCount = meetings?.filter((m) => m.status === "scheduled").length ?? 0;

  return (
    <>
      <header className="admin-head">
        <div>
          <div className="eyebrow">Video meetings</div>
          <h1>Calendar</h1>
        </div>
        <div className="calendar-controls">
          {user.role === "admin" && (
            <select value={lawyer} onChange={(e) => setLawyer(e.target.value)} aria-label="Whose calendar">
              <option value="all">Everyone</option>
              <option value="me">My meetings</option>
              {staff.filter((s) => s.id !== user.id).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          <div className="calendar-nav">
            <button className="admin-link" onClick={() => setWeekStart(new Date(weekStart.getTime() - 7 * DAY))} aria-label="Previous week">←</button>
            <button className="admin-link" onClick={() => setWeekStart(startOfWeek(new Date()))}>This week</button>
            <button className="admin-link" onClick={() => setWeekStart(new Date(weekStart.getTime() + 7 * DAY))} aria-label="Next week">→</button>
          </div>
        </div>
      </header>

      {error && <p className="admin-error" role="alert">{error}</p>}

      {nextUp && (
        <section className={`next-meeting${joinable(nextUp, now) ? " live" : ""}`} aria-live="polite">
          <div>
            <span className="tiny-label">{joinable(nextUp, now) ? "Time to join" : "Your next meeting"}</span>
            <b>{nextUp.customer_name} · {nextUp.service_name}</b>
            <small>{nextUp.when} · {startsIn(nextUp, now)} · <Link href={`/admin/tickets/${nextUp.ticket_number}`}>{nextUp.ticket_number}</Link></small>
          </div>
          {nextUp.meet_link && <a className={`btn small${joinable(nextUp, now) ? " gold" : " light"}`} href={nextUp.meet_link} target="_blank" rel="noreferrer">Join Google Meet</a>}
        </section>
      )}

      <section className="admin-card">
        <div className="card-head">
          <h2>{rangeFormat.format(days[0])} – {rangeFormat.format(days[6])}</h2>
          <small className="muted">{meetings === null ? "Loading…" : `${weekCount} meeting${weekCount === 1 ? "" : "s"}`}</small>
        </div>
        <div className="calendar-week">
          {days.map((day) => {
            const todays = (meetings ?? []).filter((m) => sameDay(new Date(m.starts_at), day));
            return (
              <div key={day.toISOString()} className={`calendar-day${sameDay(day, today) ? " today" : ""}${day < today && !sameDay(day, today) ? " past" : ""}`}>
                <h3>{dayHead.format(day)}</h3>
                {todays.length === 0 ? <p className="calendar-empty">No meetings</p> : todays.map((m) => (
                  <article key={m.id} className={`calendar-meeting status-${m.status}${joinable(m, now) ? " live" : ""}`}>
                    <span className="calendar-time">{formatTime(m.starts_at)} – {formatTime(m.ends_at)}</span>
                    <b>{m.customer_name}</b>
                    <small>{m.service_name}</small>
                    {showLawyer && <small>with {m.lawyer.name}</small>}
                    <div className="calendar-actions">
                      <Link href={`/admin/tickets/${m.ticket_number}`}>{m.ticket_number}</Link>
                      {m.status === "scheduled" && m.meet_link ? <a href={m.meet_link} target="_blank" rel="noreferrer">{joinable(m, now) ? "Join now" : "Meet link"}</a> : <span>{m.status_label}</span>}
                    </div>
                  </article>
                ))}
              </div>
            );
          })}
        </div>
        <p className="admin-footnote">Times are in your browser&apos;s time zone. The calendar refreshes every minute. Lawyers with a WhatsApp number on file also get each booking, change and reminder there, plus the day&apos;s list each morning.</p>
      </section>
    </>
  );
}
