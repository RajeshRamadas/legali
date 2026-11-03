"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import BrandMark from "./BrandMark";
import SiteFooter from "../SiteFooter";
import { useSession } from "../account/session";
import Icon from "./Icon";
const defaultNav = [
  ["/rera", "RERA check"],
  ["/lawyers", "Find a lawyer"],
  ["/#packages", "Verify a property"],
  ["/services#documents", "Documents"],
  ["/developers", "For developers"],
];
export default function PublicShell({ children }: { children: ReactNode }) {
  const modernHome = usePathname() === "/";
  const nav = modernHome
    ? [
        ["/#packages", "Property verification"],
        ["/rera", "RERA check"],
        ["/lawyers", "Find an advocate"],
        ["/services", "All services"],
      ]
    : defaultNav;
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
    <div className={`hx-public${modernHome ? " hx-home-public" : ""}`}>
      <header className="hx-public-header">
        <div className="hx-public-nav">
          <Link className="hx-brand" href="/" aria-label="Homexo Legal home">
            <BrandMark />
            <span className="hp-wordmark">homexo<small>LEGAL</small></span>
          </Link>
          <nav
            id="public-navigation"
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
            <Link className="hx-button pill" href="/account">
              {session ? "My account" : "Sign in"}
            </Link>
            {!modernHome && (
              <Link
                className="hx-button dark pill hx-get-started"
                href="/#callback"
              >
                Get started
              </Link>
            )}
            <button
              type="button"
              className="hx-icon-button hx-mobile-menu"
              aria-controls="public-navigation"
              aria-expanded={open}
              aria-label={open ? "Close navigation" : "Open navigation"}
              onClick={() => setOpen(!open)}
            >
              {open ? (
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M6 6l12 12M6 18L18 6" />
                </svg>
              ) : (
                <Icon name="menu" />
              )}
            </button>
          </div>
        </div>
      </header>
      {children}
      <SiteFooter />
    </div>
  );
}
