"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { adminFetch, getToken, setToken, UnauthorizedError, type StaffUser } from "./api";

type Session = { user: StaffUser; signOut: () => void; onError: (error: unknown) => string };
const SessionContext = createContext<Session | null>(null);

export function useStaff(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useStaff must be used inside AdminShell");
  return session;
}

export default function AdminShell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<StaffUser | null>(null);
  const [checking, setChecking] = useState(true);
  const pathname = usePathname();

  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    adminFetch<StaffUser>("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  // An expired session sends staff back to sign-in; other errors become a message for the page.
  const onError = useCallback((error: unknown) => {
    if (error instanceof UnauthorizedError) signOut();
    return error instanceof Error ? error.message : "Something went wrong.";
  }, [signOut]);

  if (checking) return <div className="admin-loading">Loading…</div>;
  if (!user) return <SignIn onSignedIn={setUser} />;

  const nav = [
    { href: "/admin", label: "Ticket queue", icon: "▤" },
    { href: "/admin/calendar", label: "Calendar", icon: "◷" },
    { href: "/admin/fetches", label: "Government fetches", icon: "⇩" },
    { href: "/admin/profile", label: "Lawyer profile", icon: "⚖" },
    ...(user.role === "admin" ? [{ href: "/admin/blog", label: "Blog", icon: "✎" }, { href: "/admin/staff", label: "Staff", icon: "☺" }] : []),
  ];

  return (
    <SessionContext.Provider value={{ user, signOut, onError }}>
      <div className="admin-app">
        <aside className="admin-side">
          <Link className="admin-brand" href="/admin"><span className="brandmark">H</span><span>homexo legal<small>Staff workspace</small></span></Link>
          <nav>
            {nav.map((item) => (
              <Link key={item.href} href={item.href} className={(item.href === "/admin" ? pathname === "/admin" || pathname.startsWith("/admin/tickets") : pathname.startsWith(item.href)) ? "active" : undefined}>
                <span aria-hidden>{item.icon}</span>{item.label}
              </Link>
            ))}
          </nav>
          <div className="admin-me">
            <b>{user.name}</b>
            <small>{user.role === "admin" ? "Admin" : "Agent"} · {user.email}</small>
            <button className="admin-link" onClick={signOut}>Sign out</button>
          </div>
        </aside>
        <main className="admin-main">{children}</main>
      </div>
    </SessionContext.Provider>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: (user: StaffUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await adminFetch<{ access_token: string; user: StaffUser }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setToken(data.access_token);
      onSignedIn(data.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-signin">
      <form className="admin-card signin-card" onSubmit={submit}>
        <div className="admin-brand dark"><span className="brandmark">H</span><span>homexo legal<small>Staff workspace</small></span></div>
        <h1>Sign in</h1>
        <p>For Homexo case team members. Customers can track requests on the <Link href="/#track">home page</Link>.</p>
        <label>Email<input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <p className="admin-error" role="alert">{error}</p>}
        <button className="btn" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
