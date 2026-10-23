"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "./session";

// Header for the customer's own pages: documents and account.
export default function CustomerNav() {
  const pathname = usePathname();
  const session = useSession();
  const active = (href: string) => (pathname.startsWith(href) ? "active" : undefined);
  return (
    <header className="header">
      <div className="wrap navrow">
        <Link className="brand" href="/" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></Link>
        <nav className="dc-nav" aria-label="Customer">
          {!session && <Link href="/#track" className="hide-sm">Track a request</Link>}
          <Link href="/documents" className={active("/documents")}>My documents</Link>
          <Link href="/bookings" className="hide-sm">My bookings</Link>
          <Link href="/account" className={active("/account")}>{session ? "My account" : "Sign in"}</Link>
        </nav>
      </div>
    </header>
  );
}
