import type { CaseProgress as Progress } from "@homexo/shared";
import "./case-progress.css";

const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const rupees = (n: number) => `₹${n.toLocaleString("en-IN")}`;

// The case's steps for the customer (customer_progress in backend/app/case_management.py).
// `compact` shows only the step bar and the current step, for lists.
export default function CaseProgress({ progress, compact = false }: { progress: Progress; compact?: boolean }) {
  const done = progress.milestones.filter((m) => m.done).length;
  const current = progress.milestones.find((m) => m.current);
  return (
    <div className={`case-progress${compact ? " compact" : ""}`}>
      <ol className="cp-steps" aria-label={`${done} of ${progress.milestones.length} steps done`}>
        {progress.milestones.map((m) => (
          <li key={m.key} className={m.done ? "done" : m.current ? "current" : undefined} aria-current={m.current ? "step" : undefined}>
            <span className="cp-dot" aria-hidden>{m.done ? "✓" : ""}</span>
            <span className="cp-label">{m.label}</span>
          </li>
        ))}
      </ol>
      {compact ? (
        current && <small className="cp-now">Now: {current.label}</small>
      ) : (
        <>
          {progress.next_step && <p className="cp-next"><b>Next for you:</b> {progress.next_step}</p>}
          <div className="cp-facts">
            {progress.due_at && <span>Target date {dateFormat.format(new Date(progress.due_at))}</span>}
            {progress.fee && (
              <span className={`cp-fee fee-${progress.fee.status}`}>
                {progress.fee.status === "paid" ? `Fee paid ${rupees(progress.fee.paid ?? progress.fee.quote ?? 0)}` : progress.fee.status === "waived" ? "Fee waived" : `Fee ${rupees(progress.fee.quote ?? 0)} due`}
              </span>
            )}
            {progress.closed?.outcome_label && <span>Closed · {progress.closed.outcome_label}</span>}
          </div>
        </>
      )}
    </div>
  );
}
