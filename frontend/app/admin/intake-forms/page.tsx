"use client";
import { useEffect, useRef, useState } from "react";
import MainContent from "../../ui/MainContent";
import { useStaff } from "../AdminShell";
import { adminFetch } from "../api";
import "../services/services.css";
import "./forms.css";

type Question = { id: string; prompt: string; help: string; kind: "text" | "textarea" | "select"; required: boolean; max_length: number; options: string[] };
type ServiceForm = { slug: string; name: string; active: boolean; revision: number; questions: Question[] };
type History = { items: { id: string; actor: string; at: string; revision: number; reason: string; questions: Question[]; previous_questions: Question[] }[]; total: number; page: number; page_size: number };
const date = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

export default function IntakeFormsPage() {
  const { user, onError } = useStaff();
  const [forms, setForms] = useState<ServiceForm[]>([]), [selected, setSelected] = useState(""), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (user.role !== "admin") return;
    let active = true; setLoading(true); setError("");
    adminFetch<{ items: ServiceForm[] }>("/admin/intake-forms").then(result => {
      if (active) { setForms(result.items); setSelected(current => current || result.items.find(item => item.active)?.slug || ""); }
    }).catch(error => { if (active) setError(onError(error)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user.role, onError, refresh]);
  if (user.role !== "admin") return <MainContent><h1>Administrator access required</h1><p>Only administrators can publish guided intake questions.</p></MainContent>;
  const current = forms.find(item => item.slug === selected);
  return <MainContent className="service-availability intake-form-page"><header><div className="eyebrow">Better service requests</div><h1>Intake forms</h1><p>Add up to five service-specific questions to the guided request. Existing core questions, consent and case admission remain in place.</p></header>
    <section className="service-availability-card"><label>Service form<select value={selected} disabled={busy || loading} onChange={event => setSelected(event.target.value)}>{forms.map(item => <option key={item.slug} value={item.slug}>{item.name}{!item.active ? " · Retired" : ""}</option>)}</select></label>
      <button className="btn light" disabled={busy || loading} onClick={() => setRefresh(value => value+1)}>Reload published form (replaces draft)</button>
      {loading && <p role="status">Loading intake forms…</p>}{error && <p role="alert">{error}</p>}
    </section>
    {current && !loading && <FormEditor key={`${current.slug}:${refresh}`} current={current} onBusy={setBusy} onError={onError} onSaved={result => setForms(items => items.map(item => item.slug === result.slug ? result : item))} />}
  </MainContent>;
}

function FormEditor({ current, onBusy, onError, onSaved }: { current: ServiceForm; onBusy: (busy: boolean) => void; onError: (error: unknown) => string; onSaved: (form: ServiceForm) => void }) {
  const [questions, setQuestions] = useState<Question[]>(() => current.questions.map(question => ({ ...question, options: [...question.options] })));
  const [reason, setReason] = useState(""), [reviewing, setReviewing] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false), [history, setHistory] = useState<History | null>(null), [historyError, setHistoryError] = useState(""), [page, setPage] = useState(1), [historyRefresh, setHistoryRefresh] = useState(0);
  const guard = useRef(false), feedback = useRef<HTMLParagraphElement>(null), preview = useRef<HTMLDivElement>(null);
  useEffect(() => { if (notice) feedback.current?.focus(); }, [notice]);
  useEffect(() => { if (reviewing) preview.current?.focus(); }, [reviewing]);
  useEffect(() => {
    if (!historyOpen) return;
    let active = true; setHistory(null); setHistoryError("");
    adminFetch<History>(`/admin/intake-forms/${encodeURIComponent(current.slug)}/history?page=${page}`)
      .then(result => { if (active) setHistory(result); }).catch(error => { if (active) setHistoryError(onError(error)); });
    return () => { active = false; };
  }, [historyOpen, current.slug, page, historyRefresh, onError]);
  const update = (index: number, patch: Partial<Question>) => { setQuestions(rows => rows.map((row, number) => number === index ? { ...row, ...patch } : row)); setNotice(""); };
  const changed = JSON.stringify(questions) !== JSON.stringify(current.questions);
  const normalized = questions.map(question => ({ ...question, prompt: question.prompt.trim(), help: question.help.trim(), options: question.options.map(value => value.trim()) }));
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (guard.current || !changed) return;
    if (!reviewing) { setReviewing(true); setError(""); setNotice(""); return; }
    guard.current = true; setBusy(true); onBusy(true); setError(""); setNotice("");
    try {
      const result = await adminFetch<ServiceForm>(`/admin/intake-forms/${encodeURIComponent(current.slug)}`, { method: "PATCH", body: JSON.stringify({ revision: current.revision, questions: normalized, reason: reason.trim(), confirmed: true }) });
      onSaved(result); setQuestions(result.questions); setReason(""); setReviewing(false); setPage(1); setHistoryRefresh(value => value+1); setNotice("Intake form published. New service selections use this version; saved drafts keep their questions.");
    } catch (error) { setError(`${onError(error)} Your form draft and private reason are kept.`); }
    finally { guard.current = false; setBusy(false); onBusy(false); }
  }
  return <section className="service-availability-card" aria-label="Service intake form editor"><h2>{current.name}</h2><p>Published version {current.revision} · {current.questions.length} additional questions. These apply to guided requests only. Other intake channels continue through their existing workflows.</p><p>Ask only for details needed to scope this service. Do not request passwords, sign-in codes, payment information, identity numbers or document contents. Files belong in the secure case document area.</p>
    {!current.active ? <p>Retired service forms are read-only.</p> : <form onSubmit={submit}><fieldset disabled={busy}>
      {reviewing ? <>
        <div ref={preview} tabIndex={-1} role="region" aria-label="Question preview" className="intake-form-preview"><h3>Questions customers will see</h3><QuestionList questions={normalized} /></div>
        <p>Publishing applies this version when a service is newly selected. Removing questions does not erase saved answers or change submitted cases.</p>
        <button type="button" className="btn light" onClick={() => setReviewing(false)}>Back to editing</button>{" "}<button className="btn">{busy ? "Publishing…" : "Publish reviewed form"}</button>
      </> : <>
        {!questions.length && <p>No additional service questions. The standard guided questions still apply.</p>}
        {questions.map((question, index) => <fieldset className="intake-form-question" key={question.id}><legend>Question {index+1}</legend>
          <label>Question text<input required minLength={5} maxLength={160} value={question.prompt} onChange={event => update(index, { prompt: event.target.value })} /></label>
          <label>Help text (optional)<textarea rows={2} maxLength={400} value={question.help} onChange={event => update(index, { help: event.target.value })} /></label>
          <label>Answer type<select value={question.kind} onChange={event => { const kind = event.target.value as Question["kind"]; update(index, { kind, options: kind === "select" ? ["", ""] : [] }); }}><option value="text">Short answer</option><option value="textarea">Paragraph</option><option value="select">Choose one</option></select></label>
          <label className="service-availability-confirm"><input type="checkbox" checked={question.required} onChange={event => update(index, { required: event.target.checked })} /><span>Answer required</span></label>
          {question.kind !== "select" ? <label>Maximum answer length<input type="number" required min={1} max={1000} value={question.max_length} onChange={event => update(index, { max_length: Number(event.target.value) })} /></label> : <>
            {question.options.map((option, optionIndex) => <div className="intake-form-choice" key={optionIndex}><label>Choice {optionIndex+1}<input required maxLength={80} value={option} onChange={event => update(index, { options: question.options.map((value, number) => number === optionIndex ? event.target.value : value) })} /></label><button type="button" className="btn light" disabled={question.options.length <= 2} onClick={() => update(index, { options: question.options.filter((_, number) => number !== optionIndex) })}>Remove choice {optionIndex+1}</button></div>)}
            <button type="button" className="btn light" disabled={question.options.length >= 8} onClick={() => update(index, { options: [...question.options, ""] })}>Add choice</button>
          </>}
          <div className="intake-form-actions"><button type="button" className="btn light" disabled={index === 0} onClick={() => setQuestions(rows => { const next = [...rows]; [next[index-1], next[index]] = [next[index], next[index-1]]; return next; })}>Move question {index+1} up</button><button type="button" className="btn light" onClick={() => setQuestions(rows => rows.filter((_, number) => number !== index))}>Remove question {index+1}</button></div>
        </fieldset>)}
        <button type="button" className="btn light" disabled={questions.length >= 5} onClick={() => { setQuestions(rows => [...rows, { id: crypto.randomUUID(), prompt: "", help: "", kind: "text", required: false, max_length: 200, options: [] }]); setNotice(""); }}>Add question</button>
        <label>Private publication reason<textarea required minLength={10} maxLength={1000} rows={3} value={reason} onChange={event => setReason(event.target.value)} /></label>
        <button className="btn" disabled={!changed || reason.trim().length < 10}>Review intake form</button>
      </>}
    </fieldset></form>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status" ref={feedback} tabIndex={-1}>{notice}</p>}
    <details className="service-description-history" onToggle={event => setHistoryOpen(event.currentTarget.open)}><summary>Private form publication history</summary>
      {historyError ? <p role="alert">{historyError} <button type="button" className="text-link" onClick={() => setHistoryRefresh(value => value+1)}>Retry form history</button></p> : !history ? <p role="status">Loading form history…</p> : <>
        {!history.items.length ? <p>No form publications recorded.</p> : <ol className="service-availability-history">{history.items.map(item => <li key={item.id}><h3>Version {item.revision}</h3><p>{item.actor} · {date(item.at)}</p><p>Private reason: {item.reason}</p><h4>Published questions</h4><QuestionList questions={item.questions} /><details><summary>Previous questions</summary><QuestionList questions={item.previous_questions} /></details></li>)}</ol>}
        {(history.total > history.page_size || page > 1) && <nav aria-label="Form history pages"><button type="button" className="btn light" disabled={page <= 1} onClick={() => setPage(value => value-1)}>Previous publications</button><span>Page {page}</span><button type="button" className="btn light" disabled={page*history.page_size >= history.total} onClick={() => setPage(value => value+1)}>Next publications</button></nav>}
      </>}
    </details>
  </section>;
}

function QuestionList({ questions }: { questions: Question[] }) {
  return !questions.length ? <p>No additional questions. Standard guided questions still apply.</p> : <ol>{questions.map(question => <li key={question.id}><strong>{question.prompt}</strong><p>{question.required ? "Required" : "Optional"} · {question.kind === "select" ? "Choose one" : `${question.kind === "textarea" ? "Paragraph" : "Short answer"}, up to ${question.max_length} characters`}</p>{question.help && <p>{question.help}</p>}{question.options.length > 0 && <ul>{question.options.map((option, index) => <li key={index}>{option}</li>)}</ul>}</li>)}</ol>;
}
