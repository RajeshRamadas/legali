"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, dueIn, formatDate, type Board, type BoardCard, type CaseTask } from "../api";

// Open cases by the milestone they are working towards, with what is late (GET /admin/cases/board),
// and the signed-in person's open tasks across cases (GET /admin/tasks).
export default function CaseBoard() {
  const { user, onError } = useStaff();
  const [scope, setScope] = useState(user.role === "admin" ? "" : "me");
  const [board, setBoard] = useState<Board | null>(null);
  const [tasks, setTasks] = useState<CaseTask[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    adminFetch<Board>(`/admin/cases/board${scope ? `?assignee=${scope}` : ""}`).then(setBoard).catch((e) => setError(onError(e)));
  }, [scope, onError]);

  const loadTasks = () => adminFetch<{ items: CaseTask[] }>("/admin/tasks").then((r) => setTasks(r.items)).catch((e) => setError(onError(e)));
  useEffect(() => { loadTasks(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function finish(task: CaseTask) {
    try {
      await adminFetch(`/admin/tickets/${task.case!.ticket_number}/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: "done" }) });
      loadTasks();
    } catch (e) {
      setError(onError(e));
    }
  }

  const counts = board?.counts;
  const stats = [
    { label: "Open cases", value: counts?.open },
    { label: "Overdue", value: counts?.overdue, alert: !!counts?.overdue },
    { label: "Due this week", value: counts?.due_this_week },
    { label: "Late first reply", value: counts?.first_response_missed, alert: !!counts?.first_response_missed, hint: "No reply yet, past target" },
    { label: "Overdue tasks", value: counts?.overdue_tasks, alert: !!counts?.overdue_tasks },
    { label: "Closed, 30 days", value: counts?.closed_30_days },
  ];

  return (
    <>
      <header className="admin-head">
        <div>
          <div className="eyebrow">{scope === "me" ? "Cases you own" : scope === "unassigned" ? "Waiting for an owner" : user.role === "admin" ? "Every open case" : "Your cases"}</div>
          <h1>Case board</h1>
        </div>
        <div className="admin-toggle" role="radiogroup" aria-label="Whose cases">
          {(user.role === "admin" ? [["", "Everyone"], ["me", "Mine"], ["unassigned", "Unassigned"]] : [["me", "I own"], ["", "I'm on"]]).map(([value, label]) => (
            <button key={value} type="button" role="radio" aria-checked={scope === value} className={scope === value ? "on" : undefined} onClick={() => setScope(value)}>{label}</button>
          ))}
        </div>
      </header>

      {error && <p className="admin-error" role="alert">{error}</p>}

      <section className="admin-stats board-stats">
        {stats.map((s) => (
          <div key={s.label} className={`admin-stat${s.alert ? " alert" : ""}`}>
            <span>{s.label}</span>
            <b>{s.value ?? "–"}</b>
            {s.hint && <small>{s.hint}</small>}
          </div>
        ))}
      </section>

      <div className="board-layout">
        <aside className="admin-card board-tasks" aria-label="My tasks">
          <h2>My tasks{tasks?.length ? ` (${tasks.length})` : ""}</h2>
          {tasks?.length === 0 && <p className="muted">No open tasks for you.</p>}
          <ul className="task-list">
            {tasks?.map((t) => (
              <li key={t.id} className={t.overdue ? "late" : undefined}>
                <button className="task-check" aria-label={`Mark "${t.title}" done`} onClick={() => finish(t)} />
                <div>
                  <b>{t.title}</b>
                  <small>
                    <Link href={`/admin/tickets/${t.case!.ticket_number}`}>{t.case!.ticket_number}</Link> · {t.case!.customer_name}
                    {t.due_at ? ` · ${t.overdue ? dueIn(t.due_at) : `due ${formatDate(t.due_at)}`}` : ""}
                  </small>
                </div>
              </li>
            ))}
          </ul>
        </aside>
        <div className="board-columns" aria-label="Open cases by milestone">
          {board?.columns.map((col) => (
            <section key={col.key} className="board-column" aria-label={col.label}>
              <h2>{col.label}<span>{col.cards.length}</span></h2>
              {col.cards.length === 0 && <p className="board-empty">Nothing here.</p>}
              {col.cards.map((c) => <Card key={c.ticket_number} card={c} showOwner={scope !== "me"} />)}
            </section>
          ))}
          {!board && !error && <p className="admin-empty">Loading cases…</p>}
        </div>

      </div>
    </>
  );
}

function Card({ card, showOwner }: { card: BoardCard; showOwner: boolean }) {
  const d = card.deadlines;
  return (
    <Link href={`/admin/tickets/${card.ticket_number}`} className={`board-card${d.overdue ? " late" : ""}${card.priority === "urgent" ? " urgent" : ""}`}>
      <div className="board-card-top">
        <b>{card.customer_name}</b>
        {card.priority !== "normal" && <em className={`priority priority-${card.priority}`}>{card.priority}</em>}
      </div>
      <small>{card.service_name}{card.location ? ` · ${card.location}` : ""}</small>
      <div className="board-meta">
        <span className={`admin-pill pill-${card.status}`}>{card.status_label}</span>
        {d.due_at && <span className={d.overdue ? "flag late" : "flag"}>{d.overdue ? dueIn(d.due_at) : `Due ${dueIn(d.due_at)}`}</span>}
        {d.first_response_missed && !d.first_response_at && <span className="flag late">No reply yet</span>}
        {card.open_tasks > 0 && <span className={card.overdue_tasks ? "flag late" : "flag"}>{card.open_tasks} task{card.open_tasks > 1 ? "s" : ""}{card.overdue_tasks ? `, ${card.overdue_tasks} late` : ""}</span>}
        {card.fee_status === "quoted" && <span className="flag warn">Fee due</span>}
        {card.needs_reply && <span className="flag late">Customer replied</span>}
      </div>
      <small className="board-owner">{card.ticket_number}{showOwner ? ` · ${card.assignee?.name ?? "Unassigned"}` : ""}{card.team.length ? ` + ${card.team.length}` : ""}</small>
    </Link>
  );
}
