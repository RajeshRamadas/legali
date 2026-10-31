"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import AccountLink from "../account/AccountLink";
import "./lawyers.css";

// Header and footer for Find a lawyer, lawyer profiles and My bookings.
export default function LawyerShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <>
      <header className="header">
        <div className="wrap navrow">
          <Link className="brand" href="/" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></Link>
          <nav className="lw-nav" aria-label="Lawyers">
            <Link href="/lawyers" className={pathname.startsWith("/lawyers") ? "active" : undefined}>Find a lawyer</Link>
            <Link href="/bookings" className={pathname.startsWith("/bookings") ? "active" : undefined}>My bookings</Link>
            <Link href="/" className="hide-sm">Property services</Link>
            <AccountLink className={pathname.startsWith("/account") ? "active" : undefined} />
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <footer className="footer">
        <div className="wrap" style={{ fontSize: 11, color: "#a4bcb2", lineHeight: 1.7 }}>
          Consultations are with independent advocates enrolled with the Bar Council. Booking a consultation does not create a lawyer–client
          relationship for any matter beyond that consultation. Fees are shown up front; a booking cancelled in time is refunded in full.
        </div>
      </footer>
    </>
  );
}
