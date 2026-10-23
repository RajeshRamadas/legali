"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, paymentLabel, type AccountOverview, type AccountRequest } from "@homexo/shared";
import { api } from "../api";
import { openDocuments } from "../documents/ref";
import "../documents/documents.css";
import { saveBooking } from "../lawyers/store";
import "./account.css";
import CustomerNav from "./CustomerNav";
import { signOut, updateProfile, useSession, type Session } from "./session";
import SignInForm from "./SignInForm";

const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function AccountPage() {
  const session = useSession();
  return (
    <>
      <CustomerNav />
      <main>
        <section className="dc-band">
          <div className="wrap">
            <div className="eyebrow">Your account</div>
            <h1>{session?.profile.name ? `Hello, ${session.profile.name.split(" ")[0]}` : "Everything in one place"}</h1>
            <p>Your property requests, lawyer consultations, payments and case documents, for every request made with your phone number.</p>
          </div>
        </section>
        <div className="wrap dc-body">
          {session === null && <SignInForm />}
          {session && <Overview session={session} />}
        </div>
      </main>
      <footer className="footer">
        <div className="wrap" style={{ fontSize: 11, color: "#a4bcb2", lineHeight: 1.7 }}>
          You stay signed in on this browser until you sign out. On a shared computer, sign out when you are done.
        </div>
      </footer>
    </>
  );
}

function Overview({ session }: { session: Session }) {
  const router = useRouter();
  const [data, setData] = useState<AccountOverview | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const overview = await api.getAccount(session.token);
      setData(overview);
      updateProfile(overview.profile);
      // My bookings lists what this browser remembers, so add the account's consultations there too.
      [...overview.bookings].reverse().forEach((b) => saveBooking({ ticket_number: b.ticket_number, contact: overview.profile.contact }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) signOut();
      else setError(e instanceof Error ? e.message : "We couldn't load your account.");
    }
    // Only the token matters; the profile changes as it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.token]);
  useEffect(() => { load(); }, [load]);

  if (error) return <p className="dc-error" role="alert">{error} <button className="dc-link ac-plain" onClick={load}>Try again</button></p>;
  if (!data) return <p className="dc-muted">Loading your account…</p>;

  const openRequest = (r: AccountRequest) => {
    openDocuments({ ticket_number: r.ticket_number, contact: data.profile.contact });
    router.push("/documents");
  };
  const todo = data.requests.filter((r) => r.needs_you);

  return (
    <div className="ac-layout">
      <section className="dc-card">
        <div className="dc-card-head">
          <div><h2>Your requests</h2><small>{data.requests.length ? `${data.requests.length} on ${data.profile.phone}` : `None yet on ${data.profile.phone}`}</small></div>
          <Link className="btn small light" href="/#callback">New request</Link>
        </div>
        {todo.length > 0 && (
          <ul className="ac-todo" aria-label="Waiting on you">
            {todo.map((r) => (
              <li key={r.ticket_number}><span><b>{r.ticket_number}</b> · {r.needs_you}</span><button className="btn small gold" onClick={() => openRequest(r)}>Open</button></li>
            ))}
          </ul>
        )}
        {data.requests.length === 0 ? (
          <p className="dc-muted">When you ask for a callback, verification or consultation with this number, it shows here. <Link href="/lawyers" style={{ color: "var(--forest2)", fontWeight: 800 }}>Find a lawyer</Link> or <Link href="/#packages" style={{ color: "var(--forest2)", fontWeight: 800 }}>verify a property</Link>.</p>
        ) : (
          <ul className="ac-requests">
            {data.requests.map((r) => (
              <li key={r.ticket_number} className="ac-request">
                <div className="ac-request-top">
                  <div><b>{r.kind === "consultation" ? r.title : r.service_name}</b><small>{r.ticket_number}{r.package ? ` · ${r.package}` : ""} · {dateFormat.format(new Date(r.created_at))}</small></div>
                  <span className={`status-pill status-${r.status}`}>{r.status_label}</span>
                </div>
                <div className="ac-facts">
                  {r.next_meeting && <span>Meeting {r.next_meeting.when}</span>}
                  {r.report && <span>{r.report.status_label}{r.report.signed ? "" : ` (${r.report.progress.done} of ${r.report.progress.total})`}</span>}
                  {r.documents > 0 && <span>{r.documents} document{r.documents === 1 ? "" : "s"}</span>}
                </div>
                {r.needs_you && <span className="ac-needs">{r.needs_you}</span>}
                <div className="ac-actions">
                  {r.kind === "consultation"
                    ? <Link className="btn small light" href="/bookings">Manage booking</Link>
                    : <button className="btn small light" onClick={() => openRequest(r)}>{r.report?.signed ? "Report & documents" : "Documents & status"}</button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="ac-side">
        <Profile session={session} />
        <section className="dc-card">
          <h2>Payments</h2>
          {data.payments.length === 0 ? <p className="dc-muted" style={{ margin: 0 }}>Consultation fees you pay online show here.</p> : (
            <ul className="ac-payments">
              {data.payments.map((p) => (
                <li key={p.ticket_number}>
                  <div><b>{p.description}</b><small>{p.when}{p.reference ? ` · Ref ${p.reference}` : ""}</small></div>
                  <div className="ac-amount"><b>{paymentLabel(p)}</b>{p.can_pay && <small><Link href="/bookings" style={{ color: "var(--forest2)", fontWeight: 800 }}>Pay now</Link></small>}{p.paid_at && <small>{dateFormat.format(new Date(p.paid_at))}</small>}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function Profile({ session }: { session: Session }) {
  const { profile } = session;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ full_name: profile.name ?? "", email: profile.email ?? "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      updateProfile(await api.updateAccount(session.token, { full_name: form.full_name.trim() || undefined, email: form.email.trim() }));
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't save that.");
    } finally {
      setBusy(false);
    }
  }

  async function signOutEverywhere() {
    try {
      await api.signOutEverywhere(session.token);
    } finally {
      signOut();
    }
  }

  return (
    <section className="dc-card">
      <div className="dc-card-head"><h2>Your details</h2>{!editing && <button className="dc-link ac-plain" onClick={() => { setForm({ full_name: profile.name ?? "", email: profile.email ?? "" }); setEditing(true); }}>Edit</button>}</div>
      {editing ? (
        <form className="ac-edit" onSubmit={save}>
          <label>Name<input className="dc-input" minLength={2} maxLength={120} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
          <label>Email<input className="dc-input" type="email" maxLength={254} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="ac-actions"><button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button><button type="button" className="btn small light" onClick={() => setEditing(false)}>Cancel</button></div>
        </form>
      ) : (
        <dl className="ac-dl">
          <dt>Name</dt><dd>{profile.name || "Not added"}</dd>
          <dt>Phone</dt><dd>{profile.phone}</dd>
          <dt>Email</dt><dd>{profile.email || "Not added"}</dd>
        </dl>
      )}
      <div className="ac-row" style={{ marginTop: 16 }}>
        <button className="dc-link ac-plain" onClick={signOut}>Sign out</button>
        <button className="dc-link" onClick={signOutEverywhere}>Sign out on all devices</button>
      </div>
    </section>
  );
}
