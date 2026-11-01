"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type Service } from "@homexo/shared";
import { api } from "../api";
import {
  Badge,
  Button,
  Card,
  CaseCard,
  PageHeader,
  Skeleton,
  StatTile,
  Tabs,
} from "../ui/primitives";
import StaffSchedule from "../ui/StaffSchedule";
import { dateLabel, greeting } from "../ui/utils";
import { useStaff } from "./AdminShell";
import {
  adminFetch,
  timeAgo,
  type Meta,
  type StaffUser,
  type Summary,
  type TicketSummary,
  type UrgentTicket,
} from "./api";

type Filters = {
  status: string;
  service: string;
  assignee: string;
  q: string;
  needsReply: boolean;
  page: number;
};
const PAGE_SIZE = 20;

export default function TicketQueue() {
  const { user, onError } = useStaff();
  const [filters, setFilters] = useState<Filters>({
    status: "open",
    service: "",
    assignee: "",
    q: "",
    needsReply: false,
    page: 1,
  });
  const [search, setSearch] = useState("");
  const [data, setData] = useState<{
    items: TicketSummary[];
    total: number;
  } | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [urgent, setUrgent] = useState<UrgentTicket[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("active");
  const [retry, setRetry] = useState(0);
  const [urgentOnly, setUrgentOnly] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const value = params.get("tab");
    if (params.get("q")) setSearch(params.get("q")!);
    if (value) applyTab(value);
    const handler = (e: Event) => setSearch((e as CustomEvent<string>).detail);
    window.addEventListener("hx-staff-search", handler);
    return () => window.removeEventListener("hx-staff-search", handler);
  }, []);

  useEffect(() => {
    adminFetch<Meta>("/admin/meta").then(setMeta).catch(onError);
    setSummaryError("");
    adminFetch<Summary>("/admin/reports/summary")
      .then(setSummary)
      .catch((e) => setSummaryError(onError(e)));
    adminFetch<{ items: UrgentTicket[] }>("/admin/urgent")
      .then((r) => setUrgent(r.items))
      .catch(onError);
    api
      .listServices()
      .then(setServices)
      .catch(() => setServices([]));
    if (user.role === "admin")
      adminFetch<{ items: StaffUser[] }>("/admin/staff")
        .then((r) =>
          setStaff(r.items.filter((s) => s.account_status === "active")),
        )
        .catch(onError);
  }, [user.role, onError, retry]);

  useEffect(() => {
    const params = new URLSearchParams({
      page: String(filters.page),
      page_size: String(PAGE_SIZE),
    });
    for (const key of ["status", "service", "assignee", "q"] as const)
      if (filters[key]) params.set(key, filters[key]);
    if (filters.needsReply) params.set("needs_reply", "true");
    setError("");
    let active = true;
    adminFetch<{ items: TicketSummary[]; total: number }>(
      `/admin/tickets?${params}`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) setError(onError(e));
      });
    return () => {
      active = false;
    };
  }, [filters, onError, retry]);

  // Debounce the search box so typing doesn't fire a request per key.
  useEffect(() => {
    const timer = setTimeout(
      () =>
        setFilters((f) =>
          f.q === search.trim() ? f : { ...f, q: search.trim(), page: 1 },
        ),
      300,
    );
    return () => clearTimeout(timer);
  }, [search]);
  const set = (patch: Partial<Filters>) => {
    setUrgentOnly(false);
    setFilters((f) => ({
      ...f,
      needsReply: false,
      ...patch,
      page: patch.page ?? 1,
    }));
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  function applyTab(id: string) {
    setUrgentOnly(false);
    setTab(id);
    setFilters((f) => ({
      ...f,
      status:
        id === "completed"
          ? "closed"
          : id === "new"
            ? "submitted"
            : id === "waiting"
              ? "waiting_for_customer"
              : "open",
      needsReply: id === "replied",
      page: 1,
    }));
    const params = new URLSearchParams(location.search);
    params.set("tab", id);
    history.replaceState(null, "", `?${params}`);
  }
  function exportQueue() {
    if (!data) return;
    const cell = (value: string) =>
      '"' +
      (/^[=+@-]/.test(value) ? "'" + value : value).replaceAll('"', '""') +
      '"';
    const rows = [
      ["Ticket", "Customer", "Service", "Status", "Priority"],
      ...(urgentOnly ? urgent : data.items).map((t) => [
        t.ticket_number,
        t.customer_name,
        t.service_name,
        t.status_label,
        t.priority,
      ]),
    ];
    const url = URL.createObjectURL(
      new Blob([rows.map((row) => row.map(cell).join(",")).join("\n")], {
        type: "text/csv;charset=utf-8",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "homexo-ticket-queue.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <PageHeader
        eyebrow={<Badge tone="violet">Property legal</Badge>}
        title={greeting(user.name)}
        subtitle={dateLabel()}
        actions={
          <>
            <Button icon="download" onClick={exportQueue} disabled={!data}>
              Export
            </Button>
            <Button
              icon="filter"
              onClick={() =>
                document
                  .getElementById("queue-filters")
                  ?.scrollIntoView({ block: "center" })
              }
            >
              Filter
            </Button>
            <a
              className="hx-button primary"
              href="/#callback"
              target="_blank"
              rel="noreferrer"
            >
              New ticket
            </a>
          </>
        }
      />
      <Tabs
        panelId="staff-case-panel"
        value={tab}
        label="Ticket views"
        onChange={applyTab}
        items={[
          { id: "active", label: "Active cases" },
          { id: "new", label: "New requests" },
          ...(meta?.statuses.some((s) => s.value === "waiting_for_customer")
            ? [{ id: "waiting", label: "Waiting on customer" }]
            : []),
          { id: "replied", label: "Customer replied" },
          { id: "completed", label: "Completed" },
        ]}
      />
      {urgent.length > 0 && (
        <section className="admin-card admin-urgent" aria-label="Urgent tasks">
          <h2>
            ⚑ Urgent {user.role === "admin" ? "tasks" : "for you"} (
            {urgent.length})
          </h2>
          <ul>
            {urgent.map((t) => (
              <li key={t.ticket_number}>
                <Link href={`/admin/tickets/${t.ticket_number}`}>
                  <b>
                    {t.title || t.service_name} · {t.ticket_number}
                  </b>
                  {t.urgent_note && <p>{t.urgent_note}</p>}
                  <small>
                    {t.customer_name} · {t.status_label}
                    {t.assignee && user.role === "admin"
                      ? ` · ${t.assignee.name}`
                      : ""}{" "}
                    · flagged {t.flagged_by ? `by ${t.flagged_by} ` : ""}
                    {timeAgo(t.flagged_at)}
                  </small>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summaryError && (
        <Card title="Summary unavailable">
          <p role="alert">{summaryError}</p>
          <Button onClick={() => setRetry((n) => n + 1)}>Retry</Button>
        </Card>
      )}
      <div className="hx-stat-grid">
        <StatTile
          tone="violet"
          icon="case"
          label="Open tickets"
          value={summary?.open ?? "—"}
          onClick={() => set({ status: "open", assignee: "" })}
        />
        <StatTile
          tone="blue"
          icon="inbox"
          label="New today"
          value={summary?.new_today ?? "—"}
          onClick={() => set({ status: "submitted", assignee: "" })}
        />
        <StatTile
          tone="amber"
          icon="alert"
          label="Urgent"
          value={summary?.urgent ?? "—"}
          onClick={() => setUrgentOnly(true)}
        />
        <StatTile
          tone="pink"
          icon="chat"
          label="Customer replied"
          value={summary?.needs_reply ?? "—"}
          onClick={() => set({ status: "open", needsReply: true })}
        />
        {user.role === "admin" && (
          <StatTile
            tone="green"
            icon="users"
            label="Unassigned"
            value={summary?.unassigned ?? "—"}
            onClick={() => set({ status: "open", assignee: "unassigned" })}
          />
        )}
      </div>
      <div className="hx-dashboard-grid staff">
        <div>
          <section className="admin-card">
            <div className="admin-filters" id="queue-filters">
              <input
                type="search"
                placeholder="Search ticket, customer, phone or area"
                aria-label="Search tickets"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <select
                aria-label="Status"
                value={filters.status}
                onChange={(e) => set({ status: e.target.value })}
              >
                <option value="open">Open</option>
                <option value="">All statuses</option>
                <option value="closed">Closed</option>
                {meta?.statuses.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="Service"
                value={filters.service}
                onChange={(e) => set({ service: e.target.value })}
              >
                <option value="">All services</option>
                {services.map((s) => (
                  <option key={s.slug} value={s.slug}>
                    {s.name}
                  </option>
                ))}
              </select>
              {user.role === "admin" && (
                <select
                  aria-label="Assignee"
                  value={filters.assignee}
                  onChange={(e) => set({ assignee: e.target.value })}
                >
                  <option value="">Anyone</option>
                  <option value="me">Me</option>
                  <option value="unassigned">Unassigned</option>
                  {staff
                    .filter((s) => s.id !== user.id)
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                </select>
              )}
            </div>

            {error && (
              <p className="admin-error" role="alert">
                {error}
              </p>
            )}

            {error && (
              <Button onClick={() => setRetry((n) => n + 1)}>Retry</Button>
            )}
            {urgentOnly && (
              <p>
                <Badge tone="amber">Urgent cases</Badge>{" "}
                <button
                  className="hx-text-link"
                  onClick={() => setUrgentOnly(false)}
                >
                  Clear urgent filter
                </button>
              </p>
            )}
            <div
              className="hx-case-list"
              id="staff-case-panel"
              role="tabpanel"
              aria-labelledby={`staff-case-panel-tab-${tab}`}
            >
              {!data && !error && <Skeleton height={260} />}
              {(urgentOnly ? urgent : data?.items)?.map((t) => (
                <CaseCard
                  key={t.ticket_number}
                  title={t.customer_name}
                  subtitle={`${t.service_name}${t.package ? ` · ${t.package}` : ""}`}
                  stage={t.status_label}
                  progress={
                    Math.max(
                      0,
                      meta?.statuses.findIndex((s) => s.value === t.status) ??
                        0,
                    ) / Math.max(1, (meta?.statuses.length ?? 1) - 1)
                  }
                  badge={{
                    tone:
                      t.priority === "urgent"
                        ? "red"
                        : t.priority === "high"
                          ? "amber"
                          : t.priority === "low"
                            ? "gray"
                            : "blue",
                    label: t.priority,
                  }}
                  meta={
                    <>
                      <strong>{t.ticket_number}</strong>
                      <small>{t.location}</small>
                    </>
                  }
                  actions={
                    <>
                      <Link
                        className="hx-button sm"
                        href={`/admin/tickets/${t.ticket_number}#documents`}
                      >
                        Documents
                      </Link>
                      <Link
                        className="hx-button sm"
                        href={`/admin/tickets/${t.ticket_number}`}
                      >
                        Update
                      </Link>
                    </>
                  }
                />
              ))}
              {data && !(urgentOnly ? urgent : data.items).length && (
                <p>
                  No cases match these filters.{" "}
                  <button
                    className="hx-text-link"
                    onClick={() => {
                      setSearch("");
                      applyTab("active");
                    }}
                  >
                    View active cases
                  </button>
                </p>
              )}
            </div>

            {!urgentOnly && data && data.total > PAGE_SIZE && (
              <div className="admin-pager">
                <button
                  className="btn small light"
                  disabled={filters.page <= 1}
                  onClick={() =>
                    setFilters((f) => ({ ...f, page: f.page - 1 }))
                  }
                >
                  ← Previous
                </button>
                <span>
                  Page {filters.page} of {pages} · {data.total} tickets
                </span>
                <button
                  className="btn small light"
                  disabled={filters.page >= pages}
                  onClick={() =>
                    setFilters((f) => ({ ...f, page: f.page + 1 }))
                  }
                >
                  Next →
                </button>
              </div>
            )}
          </section>
        </div>
        <aside className="hx-dashboard-rail">
          <StaffSchedule admin={user.role === "admin"} />
        </aside>
      </div>
    </>
  );
}
