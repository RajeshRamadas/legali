"use client";

import { useCallback, useEffect, useState } from "react";
import { useStaff } from "../AdminShell";
import { adminFetch, type StaffUser } from "../api";

const emptyForm = { display_name: "", email: "", password: "", role: "agent" as "agent" | "admin" };

export default function StaffPage() {
  const { user, onError } = useStaff();
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    adminFetch<{ items: StaffUser[] }>("/admin/staff").then((r) => setStaff(r.items)).catch((e) => setError(onError(e)));
  }, [onError]);
  useEffect(load, [load]);

  if (user.role !== "admin") return <p className="admin-empty">Only admins can manage staff.</p>;

  async function run(action: () => Promise<unknown>, done: string) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await action();
      setNotice(done);
      load();
      return true;
    } catch (e) {
      setError(onError(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (await run(() => adminFetch("/admin/staff", { method: "POST", body: JSON.stringify(form) }), `${form.display_name} can now sign in.`)) setForm(emptyForm);
  }

  const update = (member: StaffUser, body: object, done: string) =>
    run(() => adminFetch(`/admin/staff/${member.id}`, { method: "PATCH", body: JSON.stringify(body) }), done);

  return (
    <>
      <header className="admin-head"><div><div className="eyebrow">Team</div><h1>Staff</h1></div></header>
      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}
      <div className="staff-layout">
        <section className="admin-card">
          <h2>Team members</h2>
          <ul className="staff-list">
            {staff.map((member) => (
              <li key={member.id} className={member.account_status !== "active" ? "suspended" : undefined}>
                <div>
                  <b>{member.name}{member.id === user.id && " (you)"}</b>
                  <small>{member.email} · {member.role === "admin" ? "Admin" : "Agent"}{member.account_status !== "active" && " · suspended"}</small>
                </div>
                {member.id !== user.id && (
                  <div className="staff-actions">
                    <button className="admin-link" disabled={busy} onClick={() => update(member, { role: member.role === "admin" ? "agent" : "admin" }, `${member.name} is now ${member.role === "admin" ? "an agent" : "an admin"}.`)}>
                      Make {member.role === "admin" ? "agent" : "admin"}
                    </button>
                    <button className="admin-link" disabled={busy} onClick={() => update(member, { account_status: member.account_status === "active" ? "suspended" : "active" }, member.account_status === "active" ? `${member.name} can no longer sign in.` : `${member.name} can sign in again.`)}>
                      {member.account_status === "active" ? "Suspend" : "Reactivate"}
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>

        <form className="admin-card admin-form" onSubmit={create}>
          <h2>Add a team member</h2>
          <label>Name<input required minLength={2} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
          <label>Email<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Temporary password<input type="password" required minLength={10} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          <label>Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as "agent" | "admin" })}>
              <option value="agent">Agent: works tickets assigned to them</option>
              <option value="admin">Admin: sees every ticket, assigns work, manages staff</option>
            </select>
          </label>
          <button className="btn small" disabled={busy}>Add member</button>
          <small className="admin-footnote">Share the password privately. At least 10 characters.</small>
        </form>
      </div>
    </>
  );
}
