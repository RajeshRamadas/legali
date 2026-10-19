"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { askAssistant, requestService } from "./homeEvents";

type Action = { go: string } | { service: string; message: string } | { ask: true };
type Chip = { label: string; action: Action };
type Task = { id: string; label: string; placeholder: string; cta: string; run: (q: string) => Action; chips: Chip[] };

const enc = encodeURIComponent;
const service = (slug: string, message: string): Action => ({ service: slug, message });

const TASKS: Task[] = [
  {
    id: "rera", label: "RERA check", cta: "Check project",
    placeholder: "Project name, RERA number, developer, locality or PIN code",
    run: (q) => ({ go: q ? `/rera?q=${enc(q)}#results` : "/rera" }),
    chips: [
      { label: "High-risk projects", action: { go: "/rera?risk=red#results" } },
      { label: "Due to complete soonest", action: { go: "/rera?status=ongoing&sort=deadline#results" } },
      { label: "Completed projects", action: { go: "/rera?status=completed#results" } },
    ],
  },
  {
    id: "lawyer", label: "Talk to a lawyer", cta: "Find lawyers",
    placeholder: "Describe your problem, e.g. property dispute, cheque bounce, RERA delay",
    run: (q) => ({ go: q ? `/lawyers?q=${enc(q)}` : "/lawyers" }),
    chips: ["Property", "Cheque bounce", "Divorce", "Consumer"].map((label) => ({ label, action: { go: `/lawyers?q=${enc(label)}` } })),
  },
  {
    id: "verify", label: "Verify a property", cta: "Get started",
    placeholder: "Which property? e.g. resale 2BHK in Whitefield",
    run: () => service("title-verification", "Property verification selected. Share a few details and a specialist will confirm the scope."),
    chips: [
      { label: "Title check", action: service("title-verification", "Title verification selected. Share a few details and we'll call you back.") },
      { label: "Full due diligence", action: service("legal-due-diligence", "Full legal due diligence selected. Share a few details and we'll call you back.") },
      { label: "Khata transfer", action: service("khata-tax-bescom-transfer", "Khata transfer selected. Share a few details and we'll call you back.") },
    ],
  },
  {
    id: "docs", label: "Get a document", cta: "Request document",
    placeholder: "Which document? e.g. affidavit, Encumbrance Certificate, certified sale deed",
    run: () => service("document-retrieval-courier", "Document request selected. Tell us which document you need and where the property is."),
    chips: [
      { label: "Affidavit", action: service("affidavit-drafting", "Affidavit drafting selected. Tell us what the affidavit is for and we'll call you back.") },
      { label: "Encumbrance Certificate", action: service("certified-copy-ec", "Encumbrance Certificate selected. Share the property details and we'll confirm fees and timing.") },
      { label: "RTC / Pahani", action: service("rtc-mutation-survey-records", "Land records selected. Share the survey number and location and we'll confirm availability.") },
      { label: "Deeds & POA", action: service("deed-drafting-registration", "Deed drafting selected. Tell us which deed you need and we'll call you back.") },
    ],
  },
  {
    id: "ask", label: "Ask a question", cta: "Ask",
    placeholder: "Ask anything, e.g. what is an A Khata?",
    run: () => ({ ask: true }),
    chips: ["What is an EC?", "A Khata vs B Khata", "Which package do I need?"].map((label) => ({ label, action: { ask: true } as Action })),
  },
];

// The hero's "What do you need?" box: each tab sends the visitor straight to the place that gets that job done.
export default function HomeHero() {
  const router = useRouter();
  const [taskId, setTaskId] = useState(TASKS[0].id);
  const [query, setQuery] = useState("");
  const task = TASKS.find((t) => t.id === taskId) ?? TASKS[0];

  function run(action: Action, text: string) {
    if ("go" in action) router.push(action.go);
    else if ("service" in action) requestService({ slug: action.service, message: action.message, description: query.trim() || undefined });
    else askAssistant(text);
  }

  return (
    <div className="hx-launcher">
      <div className="hx-tabs" role="tablist" aria-label="What do you need?">
        {TASKS.map((t) => (
          <button key={t.id} id={`tab-${t.id}`} role="tab" type="button" aria-selected={t.id === task.id} aria-controls="hx-task" className={`hx-tab${t.id === task.id ? " on" : ""}`} onClick={() => setTaskId(t.id)}>{t.label}</button>
        ))}
      </div>
      <div id="hx-task" role="tabpanel" aria-labelledby={`tab-${task.id}`}>
        <form className="hx-ask" onSubmit={(e) => { e.preventDefault(); run(task.run(query.trim()), query.trim()); }}>
          <label htmlFor="hx-query" className="sr-only">{task.label}</label>
          <input id="hx-query" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={task.placeholder} required={task.id === "ask"} />
          <button className="btn" type="submit">{task.cta} <span aria-hidden>→</span></button>
        </form>
        <div className="hx-chips">
          <span>Popular:</span>
          {task.chips.map((chip) => <button key={chip.label} type="button" onClick={() => run(chip.action, chip.label)}>{chip.label}</button>)}
        </div>
      </div>
    </div>
  );
}
