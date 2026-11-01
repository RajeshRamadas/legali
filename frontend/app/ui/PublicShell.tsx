"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import ThemeToggle from "./ThemeToggle";
import SiteFooter from "../SiteFooter";
import { useSession } from "../account/session";
import Icon from "./Icon";
const nav = [
  ["/rera", "RERA check"],
  ["/lawyers", "Find a lawyer"],
  ["/#packages", "Verify a property"],
  ["/services#documents", "Documents"],
  ["/developers", "For developers"],
];
export default function PublicShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const session = useSession();
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, []);
  return (
    <div className="hx-public">
      <header className="hx-public-header">
        <div className="hx-public-nav">
          <Link className="hx-brand" href="/">
            <span className="hx-mark">H</span>
            <span>homexo legal</span>
          </Link>
          <nav
            className={`hx-public-links ${open ? "open" : ""}`}
            aria-label="Main navigation"
          >
            {nav.map(([href, label]) => (
              <Link key={href} href={href} onClick={() => setOpen(false)}>
                {label}
              </Link>
            ))}
            {open && (
              <>
                <Link href="/#track" onClick={() => setOpen(false)}>
                  Track request
                </Link>
                <Link href="/account" onClick={() => setOpen(false)}>
                  Sign in
                </Link>
              </>
            )}
          </nav>
          <div className="hx-public-actions">
            <ThemeToggle />
            <Link className="hx-button pill" href="/account">
              {session ? "My account" : "Sign in"}
            </Link>
            <Link
              className="hx-button dark pill hx-get-started"
              href="/#callback"
            >
              Get started
            </Link>
            <button
              type="button"
              className="hx-icon-button hx-mobile-menu"
              aria-expanded={open}
              aria-label={open ? "Close navigation" : "Open navigation"}
              onClick={() => setOpen(!open)}
            >
              <Icon name={open ? "check" : "menu"} />
            </button>
          </div>
        </div>
      </header>
      {children}
      <SiteFooter />
    </div>
  );
}
