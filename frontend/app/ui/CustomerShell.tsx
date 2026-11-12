"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError, type AccountOverview } from "@homexo/shared";
import { api } from "../api";
import { signOut, readSession, type Session } from "../account/session";
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
  const [supportReplies, setSupportReplies] = useState(0);
  const [signOutError,setSignOutError]=useState("");
  const ending=useRef(false);
  async function endCurrentSession(){
    if(ending.current)return;ending.current=true;setSignOutError("");const token=session.token;
    try{await api.revokeCurrentCustomerSession(token);if(readSession()?.token===token)signOut();}
    catch(error){if(readSession()?.token===token)setSignOutError(error instanceof Error?error.message:"Could not confirm sign-out. Please try again.");}
    finally{ending.current=false;}
  }
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
  useEffect(() => {
    let active = true, generation = 0;
    setSupportReplies(0);
    const load = () => {
      const current = ++generation;
      api.supportUnread().then(value => { if (active && current === generation && Number.isSafeInteger(value.unread_replies) && value.unread_replies >= 0) setSupportReplies(value.unread_replies); }).catch(() => {});
    };
    load();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 30000);
    window.addEventListener("hx-support-updated", load);
    window.addEventListener("focus", load);
    return () => { active = false; clearInterval(timer); window.removeEventListener("hx-support-updated", load); window.removeEventListener("focus", load); };
  }, [session.token, pathname]);
  const todo = requests.filter((r) => r.needs_you);
  const nav = [
    {
      label: "Overview",
      items: [
        { href: "/account", label: "Home", icon: "home" as const },
        { href: "/request", label: "Start / resume request", icon: "plus" as const },
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
        { href: "/account/reviews", label: "My reviews", icon: "pen" as const },
        { href: "/account/notifications", label: "Notifications", icon: "bell" as const },
        { href: "/account#payments", label: "Payments", icon: "card" as const },
        { href: "/account/privacy", label: "Privacy requests", icon: "shield" as const },
        { href: "/account/data", label: "Download my summary", icon: "file" as const },
        { href: "/account/security", label: "Signed-in sessions", icon: "shield" as const },
        { href: "/account/support", label: "Support & complaints", icon: "inbox" as const, count: supportReplies },
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
        onSignOut={endCurrentSession}
        searchPlaceholder="Search requests by service or ticket number"
        onSearch={(q) => {
          setQuery(q);
          if (pathname !== "/account") router.push("/account#requests");
        }}
        bell={{
          count: todo.length + supportReplies,
          items: [...todo.map((r) => ({
            label: `${r.ticket_number} · ${r.needs_you}`,
            href: "/documents",
            onClick: () =>
              openDocuments({
                ticket_number: r.ticket_number,
                contact: session.profile.contact,
              }),
          })), ...(supportReplies ? [{ label: `${supportReplies} unread support ${supportReplies === 1 ? "reply" : "replies"}`, href: "/account/support" }] : [])],
        }}
        mobileTabs={[
          { href: "/account", label: "Home", icon: "home" },
          { href: "/account#requests", label: "Requests", icon: "case" },
          { href: "/assistant", label: "Ask", icon: "spark" },
          { href: "/documents", label: "Docs", icon: "file" },
          { href: "/account#profile", label: "Account", icon: "users" },
        ]}
      >
        {signOutError&&<p className="form-error" role="alert">Could not confirm sign-out. {signOutError}</p>}
        {children}
      </AppShell>
    </SearchContext.Provider>
  );
}
