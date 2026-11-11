"use client";
import { useState } from "react";
import type { SubmittedIntake } from "./api";
import "./submitted-intake.css";

const date = (value: string | null) => value ? new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) : "Not retained";

export default function SubmittedIntakeReview({ review, hasHistory }: { review: SubmittedIntake | null | undefined; hasHistory: boolean }) {
  const [search, setSearch] = useState(""), [group, setGroup] = useState("all");
  if (!review) return null;
  const term = search.trim().toLowerCase();
  const answers = review.answers.filter(row => (group === "all" || row.section === group) && `${row.question} ${row.skipped ? "Skipped" : row.answer}`.toLowerCase().includes(term));
  return <section className="admin-card submitted-intake" aria-label="Submitted request review">
    <div className="card-head"><h2>Submitted request</h2><span className="admin-tag">{review.answers.length} recorded answers</span></div>
    <p>Customer-provided details saved at submission. Confirm scope and applicability through the case workflow.</p>
    <p className="muted">Submitted {date(review.submitted_at)}{review.service_form_revision ? ` · Service questions version ${review.service_form_revision}` : ""}</p>
    {review.format === "legacy" && <p className="submitted-intake-note">This older request shows general fields as saved values. Service answers use their retained question definitions. {hasHistory ? "Original wording is available in the submitted question history below." : "Original general-question wording was not retained."}</p>}
    {review.incomplete && <p className="submitted-intake-note">Some recorded answers could not be displayed. Review the retained question history and case records before relying on this summary.</p>}
    <div className="submitted-intake-controls"><label>Answer group<select value={group} onChange={event => setGroup(event.target.value)}><option value="all">All answers</option><option value="general">General request</option><option value="service">Service-specific questions</option></select></label>
      <label>Find in submitted answers<input type="search" maxLength={120} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search questions or answers" /></label></div>
    <p role="status">{answers.length} of {review.answers.length} answers shown.</p>
    {!answers.length ? <p>{review.answers.length ? "No recorded answers match these filters." : "No readable answer snapshot was retained. Review the retained case records."}</p> : <dl className="submitted-intake-answers">{answers.map(row => <div key={row.key}><dt>{row.question}<span className="muted">{row.section === "service" ? "Service-specific question" : "General request"}</span></dt><dd>{row.skipped ? <span className="muted">Skipped by customer</span> : row.answer}</dd></div>)}</dl>}
    <details className="submitted-intake-notices"><summary>Recorded notices</summary><dl><div><dt>Saving notice</dt><dd>{review.saving_notice || "Not retained"}</dd></div><div><dt>Saving consent recorded</dt><dd>{date(review.saving_consented_at)}</dd></div><div><dt>Submission notice</dt><dd>{review.submission_notice || "Not retained"}</dd></div><div><dt>Submission consent recorded</dt><dd>{date(review.submitted_at)}</dd></div></dl></details>
  </section>;
}
