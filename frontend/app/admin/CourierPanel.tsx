"use client";

import { useState, type FormEvent } from "react";
import { COURIER_STATUS_LABELS, type CourierStatus } from "@homexo/shared";
import { adminFetch, formatDate, type StaffShipment, type TicketDetail } from "./api";

type Draft = Pick<StaffShipment, "carrier" | "tracking_number" | "status" | "revision">;

export default function CourierPanel({ ticket, onTicket, onError }: {
  ticket: TicketDetail;
  onTicket: (ticket: TicketDetail) => void;
  onError: (error: unknown) => string;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const shipment = ticket.courier;
  if (shipment === undefined) return null;

  const current: Draft = {
    carrier: shipment?.carrier ?? "",
    tracking_number: shipment?.tracking_number ?? "",
    status: shipment?.status ?? "dispatched",
    revision: shipment?.revision ?? 0,
  };
  const form = draft ?? current;
  const statuses = shipment ? [shipment.status, ...shipment.next_statuses] : [current.status];
  const stale = form.revision !== current.revision;
  const path = "/admin/tickets/" + encodeURIComponent(ticket.ticket_number);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || stale) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      onTicket(await adminFetch<TicketDetail>(path + "/courier", {
        method: "PUT",
        body: JSON.stringify(form),
      }));
      setDraft(null);
      setNotice("Courier tracking saved.");
    } catch (err) {
      setError(onError(err));
    } finally {
      setBusy(false);
    }
  }

  async function reload() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      onTicket(await adminFetch<TicketDetail>(path));
      setDraft(null);
    } catch (err) {
      setError(onError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-card" aria-label="Courier tracking">
      <h2>Courier tracking</h2>
      <p className="muted">
        {shipment ? COURIER_STATUS_LABELS[shipment.status] + " · updated " + formatDate(shipment.updated_at) : "Record dispatch after handing the documents to the courier."}
      </p>
      <form className="admin-form" onSubmit={save}>
        <label>Courier company
          <input required disabled={busy} maxLength={80} value={form.carrier} onChange={(e) => setDraft({ ...form, carrier: e.target.value })} />
        </label>
        <label>Tracking number
          <input required disabled={busy} maxLength={80} value={form.tracking_number} onChange={(e) => setDraft({ ...form, tracking_number: e.target.value })} />
        </label>
        <label>Delivery status
          <select disabled={busy} value={form.status} onChange={(e) => setDraft({ ...form, status: e.target.value as CourierStatus })}>
            {stale && !statuses.includes(form.status) && <option value={form.status}>{COURIER_STATUS_LABELS[form.status]}</option>}
            {statuses.map((status) => <option key={status} value={status}>{COURIER_STATUS_LABELS[status]}</option>)}
          </select>
        </label>
        {error && <p className="admin-error" role="alert">{error}</p>}
        {stale && <p className="admin-error" role="alert">This shipment changed. Reload it before saving.</p>}
        {notice && <p className="admin-notice" role="status">{notice}</p>}
        <button className="btn small" disabled={busy || stale || !form.carrier.trim() || !form.tracking_number.trim()}>
          {busy ? "Please wait…" : shipment ? "Save courier update" : "Record dispatch"}
        </button>
        {(error || stale) && (
          <button className="btn small light" type="button" disabled={busy} onClick={reload}>Reload and discard edits</button>
        )}
      </form>
    </section>
  );
}
