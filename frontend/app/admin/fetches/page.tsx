"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, adminUpload, type FetchTask } from "../api";
import type { GovSource } from "@homexo/shared";

// Public records the case team gets from government portals so the buyer doesn't have to, across open reports.
export default function FetchesPage() {
  const { onError } = useStaff();
  const [items, setItems] = useState<FetchTask[] | null>(null);
  const [sources, setSources] = useState<GovSource[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    adminFetch<{ items: FetchTask[]; sources: GovSource[] }>("/admin/fetch-queue")
      .then((r) => { setItems(r.items); setSources(r.sources); })
      .catch((e) => setError(onError(e)));
  }, [onError]);
  useEffect(load, [load]);

  async function upload(task: FetchTask, file: File) {
    setError("");
    setNotice("");
    const form = new FormData();
    form.append("tag", task.item.tag);
    form.append("note", task.source ? `Fetched from ${task.source.name}` : "");
    form.append("file", file);
    try {
      await adminUpload(`/admin/tickets/${encodeURIComponent(task.ticket_number)}/documents`, form);
      setNotice(`${file.name} filed under #${task.item.tag} on ${task.ticket_number}. Verify it on the ticket.`);
      load();
    } catch (e) {
      setError(onError(e));
    }
  }

  const bySource = new Map<string, FetchTask[]>();
  for (const task of items ?? []) {
    const key = task.source?.key ?? "";
    bySource.set(key, [...(bySource.get(key) ?? []), task]);
  }

  return (
    <>
      <header className="admin-head">
        <div>
          <div className="eyebrow">Less for the buyer to chase</div>
          <h1>Government fetches</h1>
          <p className="muted" style={{ maxWidth: 680, fontSize: 13 }}>
            Public records that preliminary reports mark for Homexo to get: ECs and certified copies from Kaveri, RTC and mutation from Bhoomi,
            khata and tax from BBMP, survey sketches and RERA. Open the portal, search with the details shown, download the copy and upload it here; it is filed under the checklist tag.
          </p>
        </div>
      </header>
      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}
      {items === null ? <p className="admin-empty">Loading…</p> : items.length === 0 ? (
        <p className="admin-empty">Nothing to fetch. Items appear here when a preliminary report marks a document for Homexo to get.</p>
      ) : (
        [...bySource.entries()].map(([key, tasks]) => {
          const source = sources.find((s) => s.key === key);
          return (
            <section key={key || "none"} className="admin-card fetch-group">
              <div className="casefile-head">
                <div>
                  <h2>{source?.name ?? "No portal set"} <small className="muted">· {tasks.length}</small></h2>
                  {source && <small className="muted">Search by: {source.search_by}</small>}
                </div>
                {source && <a className="btn small light" href={source.url} target="_blank" rel="noreferrer">Open portal ↗</a>}
              </div>
              <ul className="fetch-list">
                {tasks.map((task) => <FetchRow key={task.item.id} task={task} onUpload={(f) => upload(task, f)} />)}
              </ul>
            </section>
          );
        })
      )}
    </>
  );
}

function FetchRow({ task, onUpload }: { task: FetchTask; onUpload: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const p = task.property;
  const details = p ? [
    p.survey_number && `Sy. no. ${p.survey_number}${p.subdivision_or_surnoc ? `/${p.subdivision_or_surnoc}` : ""}`,
    p.property_id_or_pid && `PID ${p.property_id_or_pid}`, p.village, p.hobli && `${p.hobli} hobli`, p.taluk && `${p.taluk} taluk`, p.district,
  ].filter(Boolean).join(" · ") : "";
  return (
    <li>
      <div>
        <b>{task.item.label}</b> <span className="dc-tag">#{task.item.tag}</span>
        {task.item.status === "rejected" && <span className="casefile-pill rejected">Asked again</span>}
        <small><Link href={`/admin/tickets/${task.ticket_number}`}>{task.ticket_number}</Link> · {task.customer_name} · {p?.location ?? "No location"}</small>
        <small className={details ? undefined : "fetch-missing"}>{details || "Survey number / PID not on file yet. Add it on the ticket under Property identifiers."}</small>
        {task.item.note && <small>Note: {task.item.note}</small>}
      </div>
      <input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
      <button className="btn small" onClick={() => input.current?.click()}>Upload copy</button>
    </li>
  );
}
