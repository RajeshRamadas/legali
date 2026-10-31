"use client";

import { useEffect, useState } from "react";
import { adminFetch, formatDate, type TicketDetail } from "./api";
import "./verification.css";

type Evidence = { document_id: string; page: number; quote: string };
type Law = { id: string; act: string; sections: string; principle: string; url: string };
type Run = {
  id: string; created_at: string; state: string; stale: boolean;
  verdict: "high_risk" | "insufficient_evidence" | "conditional_review"; reason: string;
  llm_status: string; provider: string | null; model: string | null; law_version: string;
  documents: { id: string; filename: string; sha256: string; warnings: string[]; pages: { page: number; text: string; method: string }[] }[];
  facts: { field: string; value: string; evidence: Evidence }[];
  findings: { title: string; severity: string; reason: string; action: string; law_ids: string[]; evidence: Evidence[] }[];
  open_checks: { title: string; action: string; law_ids: string[] }[];
  trace: { step: string; detail: string }[];
  laws: Law[]; limitations: string[];
};
type AgentConfig = { configured: boolean; provider: string; model: string; max_documents: number; max_pages_per_document: number };
const VERDICTS = { high_risk: "High risk · resolve before proceeding", insufficient_evidence: "Insufficient evidence for a title decision", conditional_review: "Conditional · advocate review required" };

export default function VerificationPanel({ ticket }: { ticket: TicketDetail }) {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState("");
  const [state, setState] = useState("Karnataka");
  const [useLLM, setUseLLM] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const base = `/admin/tickets/${encodeURIComponent(ticket.ticket_number)}/verification`;
  // Changes to documents, property or checklist refresh server-calculated staleness.
  const inputs = JSON.stringify([ticket.documents.map(d => [d.id, d.tag, d.checksum_sha256]), ticket.property, ticket.report?.items]);
  useEffect(() => {
    let active = true;
    setError("");
    Promise.all([adminFetch<AgentConfig>("/admin/verification/config"), adminFetch<{ items: Run[] }>(base)])
      .then(([cfg, history]) => { if (active) { setConfig(cfg); setRuns(history.items); setSelected(""); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [base, inputs]);
  const run = runs.find(r => r.id === selected) ?? runs[0];
  const lawText = (ids: string[]) => ids.map(id => run?.laws.find(l => l.id === id)).filter((l): l is Law => !!l);
  function citation(e: Evidence, key: string | number) {
    const doc = run?.documents.find(d => d.id === e.document_id);
    return <blockquote key={key}><p>“{e.quote}”</p><small>{doc?.filename ?? e.document_id} · page / part {e.page}</small></blockquote>;
  }
  async function analyse() {
    setBusy(true); setError("");
    try {
      const result = await adminFetch<Run>(base, { method: "POST", body: JSON.stringify({ state, use_llm: useLLM, consent_to_external_processing: consent }) });
      setRuns(previous => [result, ...previous].slice(0, 10)); setSelected(result.id);
    } catch (e) { setError(e instanceof Error ? e.message : "Analysis failed. Please retry."); }
    finally { setBusy(false); }
  }
  function download() {
    if (!run) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${ticket.ticket_number}-verification-${run.id}.json`; link.click(); URL.revokeObjectURL(url);
  }
  return <section className="admin-card verification-panel" aria-label="Property verification agent">
    <div className="verification-heading"><div><span className="eyebrow">Evidence → comparison → legal screening</span><h2>Property verification agent</h2></div><span className="admin-tag">Indian property law</span></div>
    <p>Read the case documents, compare evidence and prepare a reasoned screening verdict. The case lawyer retains the final signed opinion.</p>
    <div className="verification-controls">
      <label>Property state / union territory<input value={state} maxLength={80} onChange={e => setState(e.target.value)} required /></label>
      <label className="verification-check"><input type="checkbox" checked={useLLM} disabled={!config?.configured || busy} onChange={e => { setUseLLM(e.target.checked); setConsent(false); }} />Use LLM evidence analysis {config?.configured ? `(${config.provider} · ${config.model})` : "(not configured)"}</label>
      {useLLM && <label className="verification-check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />I am authorised to send the extracted case document text to this LLM provider for analysis.</label>}
      {!config?.configured && <p className="verification-help">LLM analysis is configured by the server administrator. You can still run local extraction and identify open verification checks.</p>}
      <small>PDF, DOCX, JPG, PNG and WEBP extraction · up to {config?.max_documents ?? 10} files, {config?.max_pages_per_document ?? 15} pages per PDF. Scanned pages use OCR; unsupported, unreadable and omitted content is flagged.</small>
      <button type="button" className="btn btn-primary" onClick={analyse} disabled={busy || !ticket.documents.length || !state.trim() || (useLLM && !consent)}>{busy ? "Reading and analysing documents…" : "Run verification"}</button>
      {!ticket.documents.length && <p>Upload the property documents in the case file below to begin.</p>}
    </div>
    <div role="status" aria-live="polite">{busy && <p>Extraction and model analysis can take several minutes. Keep this case open.</p>}</div>
    {error && <p className="admin-error" role="alert">{error}</p>}
    {run && <div className="verification-results">
      <div className="verification-history"><label>Saved analysis<select value={run.id} onChange={e => setSelected(e.target.value)}>{runs.map(r => <option key={r.id} value={r.id}>{formatDate(r.created_at)} · {r.state} · {r.llm_status}</option>)}</select></label><button type="button" className="btn btn-secondary" onClick={download}>Export evidence report</button></div>
      {run.stale && <p className="admin-error" role="alert">Case evidence, property details or checklist changed after this run. This verdict is out of date; run verification again.</p>}
      <div className={`verification-verdict verdict-${run.verdict}`}><span className="eyebrow">Automated screening verdict</span><h3>{VERDICTS[run.verdict]}</h3><p>{run.reason}</p><small>{run.state} · LLM analysis: {run.llm_status.replaceAll("_", " ")} · {formatDate(run.created_at)}</small></div>
      <h3>Agent activity</h3><ol className="verification-trace">{run.trace.map(t => <li key={t.step}><strong>{t.step}</strong><p>{t.detail}</p></li>)}</ol>
      <h3>Findings and reasons</h3>
      {!run.findings.length && <p>{run.llm_status === "completed" ? "No evidence-backed adverse findings were returned. This does not establish clear title; complete the open checks below." : "Semantic analysis is incomplete. No LLM findings are available."}</p>}
      {run.findings.map((f, i) => <article className={`verification-finding severity-${f.severity}`} key={i}><span className="admin-tag">{f.severity}</span><h4>{f.title}</h4><p>{f.reason}</p>{f.evidence.map((e, n) => citation(e, n))}<p><strong>Next action:</strong> {f.action}</p>{lawText(f.law_ids).map(l => <p key={l.id}><a href={l.url} target="_blank" rel="noreferrer">{l.act} · {l.sections}</a></p>)}</article>)}
      <h3>Independent checks still required</h3>{run.open_checks.map((c, i) => <article className="verification-finding" key={i}><h4>{c.title}</h4><p>{c.action}</p><small>{lawText(c.law_ids).map(l => `${l.act} (${l.sections})`).join("; ")}</small></article>)}
      <details><summary>Extracted facts ({run.facts.length})</summary>{run.facts.map((f, i) => <div key={i}><h4>{f.field.replaceAll("_", " ")}: {f.value}</h4>{citation(f.evidence, i)}</div>)}</details>
      <details><summary>Document evidence and extraction coverage ({run.documents.length})</summary>{run.documents.map(d => <article key={d.id}><h4>{d.filename}</h4><small className="verification-hash">SHA-256: {d.sha256}</small>{d.warnings.map((w, i) => <p className="admin-error" key={i}>{w}</p>)}{d.pages.map(p => <details key={p.page}><summary>Page / part {p.page} · {p.method}</summary><pre>{p.text || "No readable text"}</pre></details>)}</article>)}</details>
      <details><summary>Indian law reference pack · {run.law_version}</summary><p>Curated screening principles. Links open the official India Code search for the Act. Confirm the current text, state amendments, exceptions and case law before relying on them.</p>{run.laws.map(l => <article key={l.id}><h4><a href={l.url} target="_blank" rel="noreferrer">{l.act}</a></h4><strong>{l.sections}</strong><p>{l.principle}</p></article>)}</details>
      <div className="verification-limitations">{run.limitations.map((text, i) => <p key={i}>{text}</p>)}</div>
    </div>}
  </section>;
}
