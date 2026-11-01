"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  paymentLabel,
  type AccountOverview,
  type AccountRequest,
} from "@homexo/shared";
import { api } from "../api";
import { openDocuments } from "../documents/ref";
import {
  AttentionCard,
  Avatar,
  Badge,
  Button,
  Card,
  CaseCard,
  ListRow,
  PageHeader,
  Skeleton,
  StatTile,
  Tabs,
} from "../ui/primitives";
import AssistantPanel from "../ui/AssistantPanel";
import { useRequestSearch } from "../ui/CustomerShell";
import {
  dateLabel,
  dayKey,
  greeting,
  initials,
  joinable,
  timeLabel,
} from "../ui/utils";
import "../ui/views/documents-documents.css";
import { saveBooking } from "../lawyers/store";
import "../ui/views/account-account.css";
import { signOut, updateProfile, useSession, type Session } from "./session";
import SignInForm from "./SignInForm";

const dateFormat = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
});

export default function AccountPage() {
  const session = useSession();
  return session ? (
    <Overview session={session} />
  ) : (
    <main className="hx-signin-page">
      <PageHeader
        title="Everything in one place"
        subtitle="Sign in to follow requests, upload documents and manage consultations."
      />
      {session === null ? <SignInForm /> : <Skeleton height={300} />}
    </main>
  );
}

// "Step 3 of 6 · Lawyer assigned" from the case milestones (customer_progress in backend/app/case_management.py).
function caseStage(r: AccountRequest): string {
  const steps = r.progress?.milestones;
  if (!steps) return r.status_label;
  const at = steps.findIndex((m) => m.current);
  if (at < 0) return r.status_label;
  return `${r.status_label} · step ${at + 1} of ${steps.length}: ${steps[at].label}`;
}

function Overview({ session }: { session: Session }) {
  const router = useRouter();
  const [data, setData] = useState<AccountOverview | null>(null);
  const [error, setError] = useState("");
  const query = useRequestSearch();
  const [tab, setTab] = useState("active");
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);

  const load = useCallback(async () => {
    setError("");
    try {
      const overview = await api.getAccount(session.token);
      setData(overview);
      updateProfile(overview.profile);
      // My bookings lists what this browser remembers, so add the account's consultations there too.
      [...overview.bookings]
        .reverse()
        .forEach((b) =>
          saveBooking({
            ticket_number: b.ticket_number,
            contact: overview.profile.contact,
          }),
        );
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) signOut();
      else
        setError(
          e instanceof Error ? e.message : "We couldn't load your account.",
        );
    }
    // Only the token matters; the profile changes as it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.token]);
  useEffect(() => {
    load();
  }, [load]);

  if (error)
    return (
      <p className="dc-error" role="alert">
        {error}{" "}
        <button className="dc-link ac-plain" onClick={load}>
          Try again
        </button>
      </p>
    );
  if (!data) return <Skeleton height={400} />;

  const openRequest = (r: AccountRequest) => {
    openDocuments({
      ticket_number: r.ticket_number,
      contact: data.profile.contact,
    });
    router.push("/documents");
  };
  const todo = data.requests.filter((r) => r.needs_you);
  const allMeetings = [
    ...data.requests.map((r) => ({
      meeting: r.next_meeting,
      label: r.service_name,
    })),
    ...data.bookings.map((b) => ({ meeting: b.meeting, label: b.lawyer.name })),
  ].filter(
    (
      m,
    ): m is {
      meeting: NonNullable<AccountRequest["next_meeting"]>;
      label: string;
    } =>
      !!m.meeting &&
      m.meeting.status === "scheduled" &&
      new Date(m.meeting.ends_at) > now,
  );
  const meetings = Array.from(
    new Map(allMeetings.map((m) => [m.meeting.id, m])).values(),
  ).sort((a, b) => a.meeting.starts_at.localeCompare(b.meeting.starts_at));
  const next = meetings[0];
  const closed = (r: AccountRequest) =>
    ["completed", "cancelled", "rejected"].includes(r.status);
  const shown = data.requests.filter(
    (r) =>
      (tab === "completed" ? closed(r) : !closed(r)) &&
      `${r.ticket_number} ${r.service_name} ${r.title}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const signed = data.requests.filter((r) => r.report?.signed);
  const attention = [
    ...todo.map((r) => ({
      key: r.ticket_number,
      title: r.needs_you!,
      meta: `${r.service_name} · ${r.ticket_number}`,
      tone: "amber" as const,
      label: "Waiting on you",
      run: () => openRequest(r),
    })),
    ...meetings
      .filter((m) => dayKey(m.meeting.starts_at) === dayKey(now))
      .map((m) => ({
        key: m.meeting.id,
        title: `Call at ${timeLabel(m.meeting.starts_at)}`,
        meta: m.label,
        tone: "blue" as const,
        label: "Today",
        run: () => router.push("/bookings"),
      })),
    ...signed.map((r) => ({
      key: `report-${r.ticket_number}`,
      title: "Download your signed report",
      meta: r.service_name,
      tone: "green" as const,
      label: "Ready",
      run: () => openRequest(r),
    })),
  ].slice(0, 4);
  return (
    <main className="hx-customer-dashboard">
      <PageHeader
        title={greeting(session.profile.name || "there", now)}
        subtitle={dateLabel(now)}
        actions={
          <>
            <Button href="/lawyers" icon="video">
              Book a consultation
            </Button>
            <Button href="/#callback" icon="plus" variant="primary">
              New request
            </Button>
          </>
        }
      />
      <div className="hx-stat-grid">
        <StatTile
          tone="violet"
          icon="case"
          label="Open requests"
          value={data.requests.filter((r) => !closed(r)).length}
          onClick={() => {
            setTab("active");
            document
              .getElementById("requests")
              ?.scrollIntoView({ block: "start" });
          }}
        />
        <StatTile
          tone="amber"
          icon="upload"
          label="Needs your attention"
          value={todo.length}
          onClick={() =>
            todo[0] ? openRequest(todo[0]) : router.push("/documents")
          }
        />
        <StatTile
          tone="blue"
          icon="video"
          label={
            next && dayKey(next.meeting.starts_at) === dayKey(now)
              ? "Consultation today"
              : "Next consultation"
          }
          value={next ? timeLabel(next.meeting.starts_at) : "None scheduled"}
          onClick={() => router.push("/bookings")}
        />
        <StatTile
          tone="green"
          icon="check"
          label="Reports ready"
          value={signed.length}
          onClick={() =>
            signed[0] ? openRequest(signed[0]) : router.push("/documents")
          }
        />
      </div>
      <div className="hx-dashboard-grid">
        <div className="hx-dashboard-rail">
          <Card title="Needs your attention" icon="alert">
            {attention.length ? (
              <div className="hx-attention-grid">
                {attention.map((a, i) => (
                  <AttentionCard
                    key={a.key}
                    featured={i === 0}
                    title={a.title}
                    meta={a.meta}
                    badge={{ tone: a.tone, label: a.label }}
                    onClick={a.run}
                  />
                ))}
              </div>
            ) : (
              <p>
                You are all caught up.{" "}
                <Link className="hx-text-link" href="/#callback">
                  Start a new request
                </Link>
              </p>
            )}
          </Card>
          <section id="requests">
            <Card
              title="My requests"
              icon="case"
              action={
                <Tabs
                  panelId="customer-case-panel"
                  value={tab}
                  onChange={setTab}
                  label="My requests"
                  items={[
                    { id: "active", label: "Active" },
                    { id: "completed", label: "Completed" },
                  ]}
                />
              }
            >
              <div
                className="hx-case-list"
                id="customer-case-panel"
                role="tabpanel"
                aria-labelledby={`customer-case-panel-tab-${tab}`}
              >
                {shown.map((r) => {
                  const payment = data.payments.find(
                    (p) => p.ticket_number === r.ticket_number,
                  );
                  return (
                    <CaseCard
                      key={r.ticket_number}
                      title={
                        r.kind === "consultation" ? r.title : r.service_name
                      }
                      subtitle={`${r.ticket_number} · started ${dateFormat.format(new Date(r.created_at))}`}
                      stage={caseStage(r)}
                      progress={
                        r.progress
                          ? r.progress.milestones.filter((m) => m.done).length / r.progress.milestones.length
                          : r.report && r.report.progress.total
                          ? r.report.progress.done / r.report.progress.total
                          : closed(r)
                            ? 1
                            : undefined
                      }
                      badge={
                        r.package
                          ? { label: r.package, tone: "violet" }
                          : undefined
                      }
                      meta={
                        payment ? (
                          <>
                            <strong>{paymentLabel(payment)}</strong>
                            <small>{payment.status}</small>
                          </>
                        ) : undefined
                      }
                      actions={
                        <>
                          {r.kind === "consultation" ? (
                            <Button size="sm" href="/bookings">
                              Manage booking
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              icon="file"
                              onClick={() => openRequest(r)}
                            >
                              Documents
                            </Button>
                          )}
                          <Button
                            size="sm"
                            icon="chat"
                            onClick={() => {
                              openDocuments({
                                ticket_number: r.ticket_number,
                                contact: data.profile.contact,
                              });
                              router.push("/documents#messages");
                            }}
                          >
                            Message
                          </Button>
                        </>
                      }
                    />
                  );
                })}
                {!shown.length && (
                  <p>
                    {query
                      ? "No requests match your search."
                      : tab === "completed"
                        ? "No completed requests yet."
                        : "No active requests yet."}{" "}
                    <Link className="hx-text-link" href="/#callback">
                      New request
                    </Link>
                  </p>
                )}
              </div>
            </Card>
          </section>
          <section id="payments">
            <Card title="Payments" icon="card">
              {data.payments.length ? (
                data.payments.map((p) => (
                  <ListRow
                    key={p.ticket_number}
                    title={p.description}
                    meta={p.when}
                    trailing={
                      <>
                        <strong>{paymentLabel(p)}</strong>
                        {p.can_pay && (
                          <Button size="sm" href="/bookings">
                            Pay now
                          </Button>
                        )}
                      </>
                    }
                  />
                ))
              ) : (
                <p>
                  Consultation payments will appear here.{" "}
                  <Link className="hx-text-link" href="/lawyers">
                    Find a lawyer
                  </Link>
                </p>
              )}
            </Card>
          </section>
          <section id="profile">
            <Profile session={session} />
          </section>
        </div>
        <aside className="hx-dashboard-rail">
          <AssistantPanel compact />
          <Card
            title="Upcoming"
            icon="video"
            action={
              <Link className="hx-text-link" href="/bookings">
                See all
              </Link>
            }
          >
            {meetings.slice(0, 3).map((m) => (
              <ListRow
                key={m.meeting.id}
                leading={
                  <Avatar
                    initials={initials(m.meeting.lawyer_name || m.label)}
                  />
                }
                title={m.meeting.lawyer_name || m.label}
                meta={`${dateFormat.format(new Date(m.meeting.starts_at))} · ${timeLabel(m.meeting.starts_at)}`}
                trailing={
                  joinable(m.meeting, now.getTime()) ? (
                    <a
                      className="hx-button primary sm"
                      href={m.meeting.meet_link!}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Join
                    </a>
                  ) : undefined
                }
              />
            ))}
            {!meetings.length && <p>No consultations scheduled.</p>}
            <Button href="/bookings" variant="primary" icon="video">
              See all consultations
            </Button>
          </Card>
        </aside>
      </div>
    </main>
  );
}

function Profile({ session }: { session: Session }) {
  const { profile } = session;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    full_name: profile.name ?? "",
    email: profile.email ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      updateProfile(
        await api.updateAccount(session.token, {
          full_name: form.full_name.trim() || undefined,
          email: form.email.trim(),
        }),
      );
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't save that.");
    } finally {
      setBusy(false);
    }
  }

  async function signOutEverywhere() {
    try {
      await api.signOutEverywhere(session.token);
    } finally {
      signOut();
    }
  }

  return (
    <section className="dc-card">
      <div className="dc-card-head">
        <h2>Your details</h2>
        {!editing && (
          <button
            className="dc-link ac-plain"
            onClick={() => {
              setForm({
                full_name: profile.name ?? "",
                email: profile.email ?? "",
              });
              setEditing(true);
            }}
          >
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <form className="ac-edit" onSubmit={save}>
          <label>
            Name
            <input
              className="dc-input"
              minLength={2}
              maxLength={120}
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </label>
          <label>
            Email
            <input
              className="dc-input"
              type="email"
              maxLength={254}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="ac-actions">
            <button className="btn small" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="btn small light"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <dl className="ac-dl">
          <dt>Name</dt>
          <dd>{profile.name || "Not added"}</dd>
          <dt>Phone</dt>
          <dd>{profile.phone}</dd>
          <dt>Email</dt>
          <dd>{profile.email || "Not added"}</dd>
        </dl>
      )}
      <div className="ac-row" style={{ marginTop: 16 }}>
        <button className="dc-link ac-plain" onClick={signOut}>
          Sign out
        </button>
        <button className="dc-link" onClick={signOutEverywhere}>
          Sign out on all devices
        </button>
      </div>
    </section>
  );
}
