"use client";
import MainContent from "../ui/MainContent";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type IntakeDraft, type IntakeNotice, type IntakeQuestion, type TicketCreated } from "@homexo/shared";
import { api } from "../api";
import { useSession, type Session } from "../account/session";
import { openDocuments } from "../documents/ref";

const when = (value: string) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
function label(q: IntakeQuestion, value?: string) { return q.options.find(o => o.value === value)?.label || value || "Skipped"; }

export default function GuidedIntake() {
  const session = useSession();
  return session ? <IntakeContent key={session.token} session={session} /> : null;
}

function IntakeContent({ session }: { session: Session }) {
  const router = useRouter(), params = useSearchParams();
  const id = params.get("draft"), service = params.get("service") || undefined;
  const [drafts, setDrafts] = useState<IntakeDraft[]>([]), [draft, setDraft] = useState<IntakeDraft | null>(null);
  const [notice, setNotice] = useState<IntakeNotice | null>(null);
  const [savingConsent, setSavingConsent] = useState(false), [submitConsent, setSubmitConsent] = useState(false);
  const [editing, setEditing] = useState<string | null>(null), [created, setCreated] = useState<TicketCreated | null>(null);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const apply = useCallback((next: IntakeDraft) => {
    setDraft(previous => previous?.id === next.id && previous.revision > next.revision ? previous : next);
    setNotice(next.notice); setCreated(next.ticket);
  }, []);

  useEffect(() => {
    let active = true; setLoading(true); setDraft(null); setError(""); setConflict(false); setEditing(null); setSavingConsent(false); setSubmitConsent(false); setCreated(null);
    const load = async () => {
      try {
        if (id) { const next = await api.getIntake(id); if (active) apply(next); }
        else { const list = await api.intakeDrafts(); if (active) { setDraft(null); setDrafts(list.items); setNotice(list.notice); } }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Could not load your saved request."); }
      finally { if (active) setLoading(false); }
    };
    load(); return () => { active = false; };
  }, [id, apply]);

  function fail(e: unknown) {
    setError(e instanceof Error ? e.message : "We couldn't save that answer. Please try again.");
    if (e instanceof ApiError && e.status === 409) setConflict(true);
  }
  async function start() {
    if (!notice) return;
    setBusy(true); setError("");
    try { const next = await api.startIntake(notice.version, savingConsent, service); apply(next); router.push(`/request?draft=${next.id}`); }
    catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function answer(question: IntakeQuestion, value: string, pause: boolean) {
    if (!draft) return;
    setBusy(true); setError("");
    try {
      const next = await api.answerIntake(draft.id, draft.revision, question.key, value);
      apply(next); setEditing(null); setSubmitConsent(false);
      if (pause) router.push("/request");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function reload() {
    setBusy(true); setError("");
    try {
      if (id) apply(await api.getIntake(id));
      else { const list = await api.intakeDrafts(); setDrafts(list.items); setNotice(list.notice); setSavingConsent(false); }
      setConflict(false); setEditing(null); setSubmitConsent(false);
    }
    catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function discard(value: IntakeDraft) {
    if (!window.confirm("Discard this draft and remove its saved answers?")) return;
    setBusy(true); setError("");
    try { await api.discardIntake(value.id); setDrafts(previous => previous.filter(d => d.id !== value.id)); }
    catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (!draft || !notice) return;
    setBusy(true); setError("");
    try {
      const result = await api.submitIntake(draft.id, draft.revision, notice.version, submitConsent);
      setCreated(result); setSubmitConsent(false); window.dispatchEvent(new Event("hx-account-refresh"));
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  const question = draft?.questions.find(q => q.key === (editing || draft.next_question));
  const answered = draft?.questions.filter(q => q.key in draft.answers) ?? [];
  const earlier = question && draft ? answered.filter(q => draft.questions.indexOf(q) < draft.questions.indexOf(question)) : [];
  return <MainContent className="guided-intake">
    <header className="intake-header"><div className="eyebrow">A request, one step at a time</div><h1>{created ? "Your request is with the team" : "Tell us what you need"}</h1><p>Share the essentials. An advocate will confirm what applies to your property.</p></header>
    {error && <div className="intake-error" role="alert"><p>{error}</p>{conflict && <button className="btn small light" disabled={busy} onClick={reload}>{id ? "Reload saved answers" : "Reload privacy notice"}</button>}</div>}
    {loading ? <p role="status">Loading your saved answers…</p> : created ? <section className="intake-card intake-success"><span className="eyebrow">Request received</span><h2>{created.ticket_number}</h2><p>{created.message}</p><p>Your request is linked to your verified phone: {session.profile.phone}.</p><div className="intake-actions"><Link className="btn" href="/documents" onClick={() => openDocuments({ ticket_number: created.ticket_number, contact: session.profile.contact })}>Open documents</Link><Link className="btn light" href="/account">Track in my account</Link><Link className="text-link" href="/request">Start another request</Link></div></section> : !id ? <>
      <section className="intake-card"><h2>Start a guided request</h2><p>Sign-in verified {session.profile.phone}. Your phone number stays attached to your request.</p><p>Answer only the questions relevant to your service and property. You can skip optional details and share them with the team later.</p>
        {notice && <><label className="intake-consent"><input type="checkbox" checked={savingConsent} onChange={e => setSavingConsent(e.target.checked)} />{notice.saving}</label><Link href="/request/privacy" target="_blank" rel="noopener noreferrer">Read the guided request privacy notice</Link><button className="btn" disabled={busy || !savingConsent} onClick={start}>{busy ? "Starting…" : "Start guided request"}</button></>}
        {service && <Link href="/request" className="text-link">Choose a different service</Link>}<Link href="/#callback" className="text-link">Prefer a quick callback?</Link>
      </section>
      <section className="intake-card"><h2>Saved drafts {drafts.length > 0 && `(${drafts.length})`}</h2>{!drafts.length ? <p>No unfinished requests. Completed answers will appear here when you start.</p> : <ul className="intake-drafts">{drafts.map(d => <li key={d.id}><div><b>{label(d.questions[0], d.answers.service_slug) === "Skipped" ? "New service request" : label(d.questions[0], d.answers.service_slug)}</b><p>{d.completed} of {d.total} answers saved · expires {when(d.expires_at)}</p></div><div className="intake-actions"><Link className="btn small light" href={`/request?draft=${d.id}`}>Resume</Link><button className="text-link" disabled={busy} onClick={() => discard(d)}>Discard</button></div></li>)}</ul>}</section>
    </> : draft && <>
      <div className="intake-progress"><span>{draft.completed} of {draft.total} answers saved</span><span>Saved until {when(draft.expires_at)}</span><progress aria-label="Completed intake answers" max={draft.total} value={draft.completed} /></div>
      {question ? <>
        {earlier.length > 0 && <details className="intake-card intake-history"><summary>Earlier answers ({earlier.length})</summary><dl>{earlier.map(q => <div key={q.key}><dt>{q.prompt}</dt><dd>{label(q, draft.answers[q.key])}</dd></div>)}</dl></details>}
        <Question key={`${draft.id}:${question.key}:${draft.revision}`} question={question} initial={draft.answers[question.key] ?? ""} busy={busy || conflict} onAnswer={(value, pause) => answer(question, value, pause)} />
        <div className="intake-actions">{earlier.length > 0 && <button className="text-link" disabled={busy} onClick={() => setEditing(earlier[earlier.length - 1].key)}>Back to previous answer</button>}<Link href="/request" className="text-link">Back to saved drafts</Link></div>
        <p className="intake-hint">Continue saves this answer. Save and exit saves it before returning to your drafts. Text you leave without saving is not retained.</p>
      </> : <section className="intake-card"><div className="eyebrow">Review before sending</div><h2>Does everything look right?</h2><p>The team will follow up using your verified phone, {session.profile.phone}, or the preference below. You can edit any answer.</p><dl className="intake-review">{draft.questions.map(q => <div key={q.key}><div><dt>{q.prompt}</dt><dd>{label(q, draft.answers[q.key])}</dd></div><button className="text-link" disabled={busy} aria-label={`Edit: ${q.prompt}`} onClick={() => { setEditing(q.key); setSubmitConsent(false); }}>Edit</button></div>)}</dl>
        <form onSubmit={submit}><label className="intake-consent"><input type="checkbox" required checked={submitConsent} onChange={e => setSubmitConsent(e.target.checked)} />{draft.notice.submission}</label><p className="intake-hint">This is a request for assistance. No fee, government outcome or legal conclusion is promised. Documents can be uploaded securely after submission.</p><Link href="/request/privacy" target="_blank" rel="noopener noreferrer">Privacy notice · {draft.notice.version}</Link><div className="intake-actions"><button className="btn" disabled={busy || conflict || !submitConsent}>{busy ? "Creating request…" : "Create my request"}</button><Link href="/request" className="text-link">Finish later</Link></div></form>
      </section>}
    </>}
    {!loading && id && !draft && !created && <Link className="btn light" href="/request">Open saved drafts</Link>}
  </MainContent>;
}

function Question({ question: q, initial, busy, onAnswer }: { question: IntakeQuestion; initial: string; busy: boolean; onAnswer: (value: string, pause: boolean) => void }) {
  const [value, setValue] = useState(initial);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => { form.current?.querySelector<HTMLElement>("#intake-answer")?.focus(); }, []);
  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); const button = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    onAnswer(value, button?.value === "pause");
  }
  const common = { id: "intake-answer", required: q.required, disabled: busy, value, onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setValue(e.target.value), "aria-describedby": "intake-help" };
  return <form ref={form} className="intake-card intake-question" onSubmit={submit}><span className="eyebrow">Homexo asks</span><h2><label htmlFor="intake-answer">{q.prompt}</label></h2><p id="intake-help">{q.help || "Choose the answer that best describes your request."}{!q.required && " Leave blank to skip."}</p>
    {q.kind === "select" ? <select {...common}><option value="">Choose an answer</option>{q.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select> : q.kind === "textarea" ? <textarea {...common} rows={4} minLength={q.min_length} maxLength={q.max_length} /> : <input {...common} type={q.kind === "email" ? "email" : "text"} minLength={q.min_length} maxLength={q.max_length} autoComplete={q.key === "customer_name" ? "name" : q.kind === "email" ? "email" : "off"} />}
    <div className="intake-actions"><button className="btn" value="next" disabled={busy}>{busy ? "Saving…" : "Continue"}</button><button className="btn light" value="pause" disabled={busy}>Save and exit</button></div>
  </form>;
}
