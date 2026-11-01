"use client";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useSession } from "../account/session";
import PublicShell from "./PublicShell";
import CustomerShell from "./CustomerShell";
import ChatWidget from "../ChatWidget";
import { Skeleton } from "./primitives";
export default function SiteFrame({ children }: { children: ReactNode }) {
  const path = usePathname(),
    session = useSession();
  if (
    path.startsWith("/admin") ||
    path.startsWith("/design-demo") ||
    path === "/ui"
  )
    return <>{children}</>;
  const customer = ["/account", "/documents", "/bookings", "/assistant"].some(
    (p) => path.startsWith(p),
  );
  if (customer && session === undefined)
    return (
      <div className="hx-loading-page">
        <Skeleton height={300} />
      </div>
    );
  if (customer && session)
    return <CustomerShell session={session}>{children}</CustomerShell>;
  return (
    <PublicShell>
      {children}
      {path !== "/assistant" && <ChatWidget />}
    </PublicShell>
  );
}
