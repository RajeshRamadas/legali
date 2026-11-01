"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { adminFetch, type Meeting } from "../admin/api";
import MiniCalendar from "./MiniCalendar";
import { Card, Button, ListRow, Badge, Skeleton } from "./primitives";
import { dayKey, timeLabel, joinable } from "./utils";
export default function StaffSchedule({ admin }: { admin: boolean }) {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null),
    [error, setError] = useState("");
  const [now, setNow] = useState(() => new Date());
  const router = useRouter();
  const load = () => {
    setError("");
    const today = new Date();
    const [year, month] = dayKey(today).split("-").map(Number);
    const start = new Date(Date.UTC(year, month - 1, 1) - 330 * 60000),
      end = new Date(Date.UTC(year, month, 1) - 330 * 60000);
    adminFetch<{ items: Meeting[] }>(
      `/admin/meetings?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}${admin ? "" : "&lawyer=me"}`,
    )
      .then((r) => setMeetings(r.items))
      .catch(() => setError("Could not load calls."));
  };
  useEffect(() => {
    load();
    const tick = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(tick);
  }, [admin]);
  if (error)
    return (
      <Card title="Calls">
        <p role="alert">{error}</p>
        <Button onClick={load}>Retry</Button>
      </Card>
    );
  if (!meetings) return <Skeleton height={320} />;
  const scheduled = meetings.filter((m) => m.status === "scheduled");
  const today = scheduled
    .filter((m) => dayKey(m.starts_at) === dayKey(now))
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  return (
    <>
      <Card
        title="Your calendar"
        icon="cal"
        action={
          <Link className="hx-text-link" href="/admin/calendar">
            View all
          </Link>
        }
      >
        <MiniCalendar
          marked={new Set(scheduled.map((m) => dayKey(m.starts_at)))}
          onSelect={(day) => router.push(`/admin/calendar?day=${day}`)}
        />
        <p className="hx-calendar-total">
          This month · {scheduled.length} scheduled calls
        </p>
      </Card>
      <Card title="Today's timeline" icon="video">
        {today.length ? (
          today.map((m) => (
            <ListRow
              key={m.id}
              leading={<Badge tone="blue">{timeLabel(m.starts_at)}</Badge>}
              title={m.title}
              meta={`${m.customer_name} · ${m.lawyer.name}`}
              trailing={
                joinable(m, now.getTime()) ? (
                  <a
                    className="hx-button primary sm"
                    href={m.meet_link!}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Join
                  </a>
                ) : (
                  <Link
                    className="hx-text-link"
                    href={`/admin/tickets/${m.ticket_number}`}
                  >
                    View
                  </Link>
                )
              }
            />
          ))
        ) : (
          <p>
            No calls scheduled today.{" "}
            <Link className="hx-text-link" href="/admin/calendar">
              Open calendar
            </Link>
          </p>
        )}
      </Card>
    </>
  );
}
