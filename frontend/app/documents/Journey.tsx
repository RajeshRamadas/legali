"use client";

// Shared by the customer Documents page and the staff ticket page: where the case stands (stepper), how the requested
// documents relate (map) and the plain-language verification checklist. Data comes from document_request.journey.
import { useRef, useState, type ReactNode } from "react";
import type { CheckStatus, DocumentJourney, JourneyCheck, ReportItem } from "@homexo/shared";
import "./journey.css";

export const CHECK_TEXT: Record<CheckStatus, { icon: string; label: string }> = {
  passed: { icon: "✓", label: "Verified" },
  in_review: { icon: "◔", label: "Being checked" },
  waiting: { icon: "○", label: "Waiting for documents" },
  problem: { icon: "!", label: "Needs attention" },
};

export function Stepper({ journey }: { journey: DocumentJourney }) {
  if (!journey.stages.length) return null;
  return (
    <ol className="jn-steps" aria-label="Where your case is">
      {journey.stages.map((s, n) => (
        <li key={s.key} className={`jn-step ${s.status}`} aria-current={s.status === "current" ? "step" : undefined}>
          <span className="jn-dot" aria-hidden>{s.status === "done" ? "✓" : n + 1}</span>
          <b>{s.label}</b>
          <small>{s.detail}</small>
        </li>
      ))}
    </ol>
  );
}

// Who is selling → how they came to own it → is it clean, recorded and approved → the advocate's opinion.
const LEFT = ["identity"];
const MIDDLE = ["title"];
export function DocumentMap({ journey, onPick }: { journey: DocumentJourney; onPick?: (key: string) => void }) {
  const groups = new Map(journey.groups.map((g) => [g.key, g]));
  const opinion = journey.checks.find((c) => c.key === "opinion");
  if (!journey.groups.length) return null;
  const node = (key: string) => {
    const g = groups.get(key);
    if (!g) return null;
    const check = journey.checks.find((c) => c.key === key);
    return (
      <button key={key} type="button" className={`jn-node ${g.status}${g.flagged ? " flagged" : ""}`} onClick={() => onPick?.(key)}
        title={g.explains} aria-label={`${g.label}: ${CHECK_TEXT[g.status].label}${g.flagged ? ", automatic check noticed something" : ""}`}>
        <span className="jn-node-icon" aria-hidden>{CHECK_TEXT[g.status].icon}</span>
        <span className="jn-node-text"><b>{g.label}</b><small>{check ? `${check.accepted} of ${check.total} accepted` : ""}{g.flagged ? " · check flagged" : ""}</small></span>
      </button>
    );
  };
  const right = journey.groups.map((g) => g.key).filter((k) => !LEFT.includes(k) && !MIDDLE.includes(k));
  const columns = [LEFT.filter((k) => groups.has(k)), MIDDLE.filter((k) => groups.has(k)), right].filter((c) => c.length);
  return (
    <div className="jn-map" role="group" aria-label="How your documents fit together">
      {columns.map((col, i) => (
        <div className="jn-col" key={i}>{col.map(node)}</div>
      ))}
      {opinion && (
        <div className="jn-col">
          <div className={`jn-node final ${opinion.status}`}>
            <span className="jn-node-icon" aria-hidden>{CHECK_TEXT[opinion.status].icon}</span>
            <span className="jn-node-text"><b>Advocate&apos;s opinion</b><small>{opinion.status === "passed" ? "Signed" : "Weighs every check"}</small></span>
          </div>
        </div>
      )}
    </div>
  );
}

export function MapLegend() {
  return (
    <ul className="jn-legend" aria-label="Colour key">
      {(Object.keys(CHECK_TEXT) as CheckStatus[]).map((s) => <li key={s} className={s}><span aria-hidden>{CHECK_TEXT[s].icon}</span>{CHECK_TEXT[s].label}</li>)}
    </ul>
  );
}

export function CheckList({ journey, items, renderItem, open: initiallyOpen }: {
  journey: DocumentJourney;
  items: ReportItem[];
  renderItem: (item: ReportItem) => ReactNode;
  open?: string[];
}) {
  return (
    <ol className="jn-checks">
      {journey.checks.map((c) => (
        <CheckRow key={c.key} check={c} items={items.filter((i) => c.tags.includes(i.tag))} renderItem={renderItem}
          defaultOpen={initiallyOpen?.includes(c.key) ?? (c.status === "problem" || c.status === "waiting")} />
      ))}
    </ol>
  );
}

function CheckRow({ check, items, renderItem, defaultOpen }: { check: JourneyCheck; items: ReportItem[]; renderItem: (i: ReportItem) => ReactNode; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLLIElement>(null);
  const text = CHECK_TEXT[check.status];
  return (
    <li ref={ref} id={`check-${check.key}`} className={`jn-check ${check.status}${open ? " open" : ""}`}>
      <button type="button" className="jn-check-head" aria-expanded={open} onClick={() => setOpen(!open)} disabled={!items.length && !check.flags.length}>
        <span className="jn-check-icon" aria-hidden>{text.icon}</span>
        <span className="jn-check-title">
          <b>{check.question}</b>
          <small>{check.label}{check.total && check.key !== "opinion" ? ` · ${check.accepted} of ${check.total} accepted` : ""}</small>
        </span>
        <span className={`jn-badge ${check.status}`}>{text.label}</span>
      </button>
      <div className="jn-check-body" hidden={!open && !!items.length}>
        <p className="jn-detail">{check.detail}</p>
        {check.flags.length > 0 && (
          <ul className="jn-flags" aria-label="Noticed by the automatic check">
            {check.flags.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        )}
        {open && items.length > 0 && <ul className="jn-items">{items.map((i) => <li key={i.id}>{renderItem(i)}</li>)}</ul>}
      </div>
    </li>
  );
}

// Opens a check and scrolls to it, e.g. when a node in the map is clicked.
export function revealCheck(key: string) {
  const el = document.getElementById(`check-${key}`);
  if (!el) return;
  if (!el.classList.contains("open")) el.querySelector<HTMLButtonElement>(".jn-check-head")?.click();
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}
