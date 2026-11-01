"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError, type AccountOverview } from "@homexo/shared";
import { api } from "../api";
import { signOut, type Session } from "../account/session";
import { openDocuments } from "../documents/ref";
import AppShell from "./AppShell";
import { initials, maskedPhone } from "./utils";
const SearchContext = createContext("");
export const useRequestSearch = () => useContext(SearchContext);
export default function CustomerShell({
  session,
  children,
}: {
  session: Session;
  children: ReactNode;
}) {
  const [data, setData] = useState<AccountOverview | null>(null),
    [query, setQuery] = useState("");
  const pathname = usePathname(),
    router = useRouter();
  useEffect(() => {
    let active = true;
    const load = () =>
      api
        .getAccount(session.token)
        .then((r) => {
          if (active) setData(r);
        })
        .catch((e) => {
          if (e instanceof ApiError && e.status === 401) signOut();
        });
    load();
    window.addEventListener("hx-account-refresh", load);
    return () => {
      active = false;
      window.removeEventListener("hx-account-refresh", load);
    };
  }, [session.token, pathname]);
  const requests = data?.requests ?? [];
  const todo = requests.filter((r) => r.needs_you);
  const nav = [
    {
      label: "Overview",
      items: [
        { href: "/account", label: "Home", icon: "home" as const },
        {
          href: "/account#requests",
          label: "My requests",
          icon: "case" as const,
          count: requests.filter(
            (r) => !["completed", "cancelled", "rejected"].includes(r.status),
          ).length,
        },
        { href: "/documents", label: "Documents", icon: "file" as const },
        { href: "/bookings", label: "Consultations", icon: "video" as const },
        { href: "/account#payments", label: "Payments", icon: "card" as const },
      ],
    },
    {
      label: "Get help",
      items: [
        { href: "/assistant", label: "AI assistant", icon: "spark" as const },
        { href: "/lawyers", label: "Find a lawyer", icon: "law" as const },
        { href: "/rera", label: "RERA check", icon: "rera" as const },
      ],
    },
  ];
  return (
    <SearchContext.Provider value={query}>
      <AppShell
        nav={nav}
        user={{
          name: session.profile.name || "Your account",
          sub: maskedPhone(session.profile.phone),
          initials: initials(session.profile.name || "Your account"),
        }}
        onSignOut={signOut}
        searchPlaceholder="Search requests by service or ticket number"
        onSearch={(q) => {
          setQuery(q);
          if (pathname !== "/account") router.push("/account#requests");
        }}
        bell={{
          count: todo.length,
          items: todo.map((r) => ({
            label: `${r.ticket_number} · ${r.needs_you}`,
            href: "/documents",
            onClick: () =>
              openDocuments({
                ticket_number: r.ticket_number,
                contact: session.profile.contact,
              }),
          })),
        }}
        mobileTabs={[
          { href: "/account", label: "Home", icon: "home" },
          { href: "/account#requests", label: "Requests", icon: "case" },
          { href: "/assistant", label: "Ask", icon: "spark" },
          { href: "/documents", label: "Docs", icon: "file" },
          { href: "/account#profile", label: "Account", icon: "users" },
        ]}
      >
        {children}
      </AppShell>
    </SearchContext.Provider>
  );
}
