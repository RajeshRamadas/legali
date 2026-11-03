"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import StaffSignIn from "./StaffSignIn";
import AppShell from "../ui/AppShell";
import { initials } from "../ui/utils";
import type { NavGroup } from "../ui/AppShell";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  adminFetch,
  getToken,
  setToken,
  UnauthorizedError,
  type StaffUser,
} from "./api";

type Session = {
  user: StaffUser;
  setUser: (user: StaffUser) => void;
  signOut: () => void;
  onError: (error: unknown) => string;
};
const SessionContext = createContext<Session | null>(null);

export function useStaff(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useStaff must be used inside AdminShell");
  return session;
}

export default function AdminShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [user, setUser] = useState<StaffUser | null>(null);
  const [checking, setChecking] = useState(true);
  const pathname = usePathname();
  const router = useRouter();
  const [urgentCount, setUrgentCount] = useState(0);
  useEffect(() => {
    if (user)
      adminFetch<{ items: unknown[] }>("/admin/urgent")
        .then((r) => setUrgentCount(r.items.length))
        .catch(() => {});
  }, [user?.id, pathname]);

  useEffect(() => {
    let active = true;
    if (!getToken()) {
      setUser(null);
      setChecking(false);
      return;
    }
    adminFetch<StaffUser>("/auth/me")
      .then(next => { if (active) setUser(next); })
      .catch(() => { if (active) { setToken(null); setUser(null); } })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [pathname]);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  // An expired session sends staff back to sign-in; other errors become a message for the page.
  const onError = useCallback(
    (error: unknown) => {
      if (error instanceof UnauthorizedError) signOut();
      return error instanceof Error ? error.message : "Something went wrong.";
    },
    [signOut],
  );

  if (pathname === "/admin/reset-password") return <>{children}</>;
  if (checking) return <div className="admin-loading">Loading…</div>;
  if (!user) return <StaffSignIn onSignedIn={setUser} />;

  const nav: NavGroup[] = [
    {
      label: "Workspace",
      items: [
        { href: "/admin", label: "Dashboard", icon: "home" },
        { href: "/admin?view=queue", label: "Ticket queue", icon: "case" },
        { href: "/admin/cases", label: "Case board", icon: "inbox" },
        { href: "/admin/calendar", label: "Calendar", icon: "cal" },
        {
          href: "/admin/fetches",
          label: "Government fetches",
          icon: "download",
        },
      ],
    },
    {
      label: "Clients & team",
      items: [
        { href: "/admin/team", label: "Team calls", icon: "users" },
        { href: "/admin/profile", label: "Lawyer profile", icon: "law" },
        { href: "/admin/security", label: "Security", icon: "lock" },
      ],
    },
    ...(user.role === "admin"
      ? [
          {
            label: "Content",
            items: [
              { href: "/admin/blog", label: "Blog", icon: "pen" as const },
              { href: "/admin/staff", label: "Staff", icon: "users" as const },
            ],
          },
        ]
      : []),
  ];

  return (
    <SessionContext.Provider value={{ user, setUser, signOut, onError }}>
      <AppShell
        nav={nav}
        user={{
          name: user.name,
          sub: user.role === "admin" ? "Administrator" : "Agent",
          initials: initials(user.name),
        }}
        area="Staff workspace"
        onSignOut={signOut}
        searchPlaceholder="Search tickets, customers or area"
        onSearch={(q) => {
          window.dispatchEvent(
            new CustomEvent("hx-staff-search", { detail: q }),
          );
          if (pathname !== "/admin")
            router.push(`/admin?q=${encodeURIComponent(q)}`);
        }}
        bell={{
          count: urgentCount,
          items: urgentCount
            ? [
                {
                  label: `${urgentCount} urgent cases need attention`,
                  href: "/admin",
                },
              ]
            : [],
        }}
        footer={
          <AvailabilityToggle
            user={user}
            onChange={setUser}
            onError={onError}
          />
        }
      >
        {children}
      </AppShell>
    </SessionContext.Provider>
  );
}

// One tap to say whether the team can call you now. The note and number are set on the Team calls page.
function AvailabilityToggle({
  user,
  onChange,
  onError,
}: {
  user: StaffUser;
  onChange: (u: StaffUser) => void;
  onError: (e: unknown) => string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function toggle() {
    setBusy(true);
    setError("");
    try {
      onChange(
        await adminFetch<StaffUser>("/admin/me/availability", {
          method: "PUT",
          body: JSON.stringify({
            available: !user.available_for_calls,
            note: user.availability_note,
          }),
        }),
      );
    } catch (e) {
      setError(onError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        className={`admin-availability${user.available_for_calls ? " on" : ""}`}
        role="switch"
        aria-checked={user.available_for_calls}
        disabled={busy}
        onClick={toggle}
      >
        <span aria-hidden />
        {user.available_for_calls ? "Taking team calls" : "Not taking calls"}
      </button>
      {error && (
        <small className="admin-availability-error">
          {error.replace(/^phone: /, "")} <Link href="/admin/team">Add it</Link>
        </small>
      )}
    </>
  );
}
