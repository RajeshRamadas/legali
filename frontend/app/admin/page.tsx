"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type Service } from "@homexo/shared";
import { api } from "../api";
import { useStaff } from "./AdminShell";
import { adminFetch, timeAgo, type Meta, type StaffUser, type Summary, type TicketSummary, type UrgentTicket } from "./api";

type Filters = { status: string; service: string; assignee: string; q: string; needsReply: boolean; page: number };
const PAGE_SIZE = 20;

export default function TicketQueue() {
  const { user, onError } = useStaff();
  const [filters, setFilters] = useState<Filters>({ status: "open", service: "", assignee: "", q: "", needsReply: false, page: 1 });
  const [search, setSearch] = useState("");
  const [data, setData] = useState<{ items: TicketSummary[]; total: number } | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [urgent, setUrgent] = useState<UrgentTicket[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    adminFetch<Meta>("/admin/meta").then(setMeta).catch(onError);
    adminFetch<Summary>("/admin/reports/summary").then(setSummary).catch(onError);
    adminFetch<{ items: UrgentTicket[] }>("/admin/urgent").then((r) => setUrgent(r.items)).catch(onError);
    api.listServices().then(setServices).catch(() => setServices([]));
    if (user.role === "admin") adminFetch<{ items: StaffUser[] }>("/admin/staff").then((r) => setStaff(r.items.filter((s) => s.account_status === "active"))).catch(onError);
  }, [user.role, onError]);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(filters.page), page_size: String(PAGE_SIZE) });
    for (const key of ["status", "service", "assignee", "q"] as const) if (filters[key]) params.set(key, filters[key]);
    if (filters.needsReply) params.set("needs_reply", "true");
    setError("");
    adminFetch<{ items: TicketSummary[]; total: number }>(`/admin/tickets?${params}`).then(setData).catch((e) => setError(onError(e)));
  }, [filters, onError]);

  // Debounce the search box so typing doesn't fire a request per key.
  useEffect(() => {
    const timer = setTimeout(() => setFilters((f) => (f.q === search.trim() ? f : { ...f, q: search.trim(), page: 1 })), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, needsReply: false, ...patch, page: patch.page ?? 1 }));
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const cards = [
    { label: "Open", value: summary?.open, active: filters.status === "open" && !filters.assignee && !filters.needsReply, apply: () => set({ status: "open", assignee: "" }) },
    { label: "New today", value: summary?.new_today, active: filters.status === "submitted", apply: () => set({ status: "submitted", assignee: "" }) },
    ...(user.role === "admin" ? [{ label: "Unassigned", value: summary?.unassigned, active: filters.assignee === "unassigned" && !filters.needsReply, apply: () => set({ status: "open", assignee: "unassigned" }) }] : []),
    { label: "Customer replied", value: summary?.needs_reply, active: filters.needsReply, apply: () => set({ status: "open", assignee: "", needsReply: true }), hint: "Waiting on us" },
  ];

  return (
    <>
      <header className="admin-head">
        <div>
          <div className="eyebrow">{user.role === "admin" ? "All requests" : "Assigned to you"}</div>
          <h1>Ticket queue</h1>
        </div>
      </header>

      {urgent.length > 0 && (
        <section className="admin-card admin-urgent" aria-label="Urgent tasks">
          <h2>⚑ Urgent {user.role === "admin" ? "tasks" : "for you"} ({urgent.length})</h2>
          <ul>
            {urgent.map((t) => (
              <li key={t.ticket_number}>
                <Link href={`/admin/tickets/${t.ticket_number}`}>
                  <b>{t.title || t.service_name} · {t.ticket_number}</b>
                  {t.urgent_note && <p>{t.urgent_note}</p>}
                  <small>{t.customer_name} · {t.status_label}{t.assignee && user.role === "admin" ? ` · ${t.assignee.name}` : ""} · flagged {t.flagged_by ? `by ${t.flagged_by} ` : ""}{timeAgo(t.flagged_at)}</small>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="admin-stats">
        {cards.map((card) => (
          <button key={card.label} className={`admin-stat${card.active ? " active" : ""}`} onClick={card.apply}>
            <span>{card.label}</span>
            <b>{card.value ?? "–"}</b>
            {card.hint && <small>{card.hint}</small>}
          </button>
        ))}
      </section>

      <section className="admin-card">
        <div className="admin-filters">
          <input type="search" placeholder="Search ticket, customer, phone or area" aria-label="Search tickets" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select aria-label="Status" value={filters.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="open">Open</option>
            <option value="">All statuses</option>
            <option value="closed">Closed</option>
            {meta?.statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select aria-label="Service" value={filters.service} onChange={(e) => set({ service: e.target.value })}>
            <option value="">All services</option>
            {services.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
          </select>
          {user.role === "admin" && (
            <select aria-label="Assignee" value={filters.assignee} onChange={(e) => set({ assignee: e.target.value })}>
              <option value="">Anyone</option>
              <option value="me">Me</option>
              <option value="unassigned">Unassigned</option>
              {staff.filter((s) => s.id !== user.id).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
        </div>

        {error && <p className="admin-error" role="alert">{error}</p>}

        <div className="admin-table" role="table" aria-label="Tickets">
          <div className="admin-row admin-row-head" role="row">
            <span role="columnheader">Ticket</span><span role="columnheader">Customer</span><span role="columnheader">Service</span>
            <span role="columnheader">Status</span><span role="columnheader">Assignee</span><span role="columnheader">Updated</span>
          </div>
          {data?.items.map((t) => (
            <Link key={t.ticket_number} href={`/admin/tickets/${t.ticket_number}`} className="admin-row" role="row">
              <span role="cell" className="cell-ticket">
                <b>{t.ticket_number}</b>
                <small>{t.source}{t.priority !== "normal" && <em className={`priority priority-${t.priority}`}>{t.priority}</em>}</small>
              </span>
              <span role="cell"><b>{t.customer_name}</b><small>{t.location}</small></span>
              <span role="cell"><b>{t.service_name}</b><small>{t.package ?? "No package"}</small></span>
              <span role="cell"><span className={`admin-pill pill-${t.status}`}>{t.status_label}</span>{t.needs_reply && <small className="needs-reply">● Customer replied</small>}</span>
              <span role="cell">{t.assignee ? t.assignee.name : <small className="muted">Unassigned</small>}</span>
              <span role="cell"><small>{timeAgo(t.updated_at)}</small></span>
            </Link>
          ))}
          {data && data.items.length === 0 && <p className="admin-empty">No tickets match these filters.</p>}
          {!data && !error && <p className="admin-empty">Loading tickets…</p>}
        </div>

        {data && data.total > PAGE_SIZE && (
          <div className="admin-pager">
            <button className="btn small light" disabled={filters.page <= 1} onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}>← Previous</button>
            <span>Page {filters.page} of {pages} · {data.total} tickets</span>
            <button className="btn small light" disabled={filters.page >= pages} onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}>Next →</button>
          </div>
        )}
      </section>
    </>
  );
}
