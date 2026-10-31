"use client";

// At-a-glance view of a case for staff: the same stepper, document map and checklist the customer sees, with each
// requested document's files and upload-check notes. Reviewing and fetching still happen in the case file below.
import { describeUploadCheck, type ReportItem } from "@homexo/shared";
import { CheckList, DocumentMap, MapLegend, Stepper, revealCheck } from "../documents/Journey";
import { fileHref, type TicketDetail } from "./api";

export default function VerificationOverview({ ticket }: { ticket: TicketDetail }) {
  const journey = ticket.document_request?.journey;
  if (!journey || !journey.checks.length) return null;
  const docs = new Map(ticket.documents.map((d) => [d.id, d]));
  const items = ticket.document_request?.items ?? [];
  const flagged = journey.checks.reduce((n, c) => n + c.flags.length, 0);
  const problems = journey.checks.filter((c) => c.status === "problem").length;
  const renderItem = (item: ReportItem) => (
    <div className={`jn-item ${item.status}`}>
      <span className="jn-item-status" aria-hidden>{item.status === "verified" || item.status === "waived" ? "✓" : item.status === "rejected" ? "!" : item.status === "received" ? "…" : ""}</span>
      <div className="jn-item-top">
        <b>{item.label}</b>
        <span className="admin-tag">#{item.tag}</span>
        <span className={`dc-pill ${item.fetch_by === "homexo" && item.status === "pending" ? "fetching" : item.status}`}>{item.status_label}</span>
      </div>
      <div className="jn-item-body">
        {item.note && <small>{item.note}</small>}
        {item.documents.length ? (
          <ul className="jn-files">
            {item.documents.map((id) => docs.get(id)).filter((d) => !!d).map((d) => {
              const check = describeUploadCheck(d!.check);
              return <li key={d!.id}><a href={fileHref(d!.download_url)} target="_blank" rel="noreferrer">{d!.filename}</a>{check && <small className={check.warn ? "warn" : ""}>{check.text}</small>}</li>;
            })}
          </ul>
        ) : <small>{item.fetch_by === "homexo" ? `Official-record task${item.source ? ` · ${item.source.name}` : ""}` : "Not uploaded yet"}</small>}
      </div>
    </div>
  );
  return (
    <section className="admin-card jn-admin" aria-label="Verification overview">
      <div className="jn-admin-head">
        <div>
          <h2>Verification overview</h2>
          <small>{journey.checks.filter((c) => c.status === "passed").length} of {journey.checks.length} checks verified{problems ? ` · ${problems} need attention` : ""}{flagged ? ` · ${flagged} upload-check note${flagged === 1 ? "" : "s"}` : ""}. What the customer sees, in the same words.</small>
        </div>
      </div>
      <Stepper journey={journey} />
      <div className="jn-admin-grid">
        <div>
          <h3>Checklist</h3>
          <CheckList journey={journey} items={items} renderItem={renderItem} open={journey.checks.filter((c) => c.status === "problem" || c.flags.length).map((c) => c.key)} />
        </div>
        <div>
          <h3>How the documents relate</h3>
          <DocumentMap journey={journey} onPick={revealCheck} />
          <MapLegend />
        </div>
      </div>
    </section>
  );
}
