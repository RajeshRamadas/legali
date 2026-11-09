"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import BrandMark from "./BrandMark";
import SiteFooter from "../SiteFooter";
import { useSession } from "../account/session";
import Icon from "./Icon";
import useMediaQuery from "./useMediaQuery";
const defaultNav = [
  ["/rera", "RERA check"],
  ["/lawyers", "Find a lawyer"],
  ["/#packages", "Verify a property"],
  ["/services#documents", "Documents"],
  ["/developers", "For developers"],
];
export default function PublicShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const modernHome = pathname === "/";
  const nav = modernHome
    ? [
        ["/#packages", "Property verification"],
        ["/rera", "RERA check"],
        ["/lawyers", "Find an advocate"],
        ["/services", "All services"],
      ]
    : defaultNav;
  const [open, setOpen] = useState(false);
  const mobile = useMediaQuery(modernHome ? "(max-width: 900px)" : "(max-width: 1000px)");
  const header = useRef<HTMLElement>(null);
  const navigation = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const session = useSession();
  useEffect(() => { setOpen(false); }, [pathname, mobile]);
  useEffect(() => {
    if (!open) return;
    navigation.current?.querySelector<HTMLElement>("a")?.focus();
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented && !document.querySelector("dialog[open]")) {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !header.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("keydown", close);
    document.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("keydown", close); document.removeEventListener("pointerdown", outside); };
  }, [open]);
  return (
    <div className={`hx-public${modernHome ? " hx-home-public" : ""}`}>
      <header className="hx-public-header" ref={header}>
        <div className="hx-public-nav">
          <Link className="hx-brand" href="/" aria-label="Homexo Legal home">
            <BrandMark />
            <span className="hp-wordmark">homexo{" "}<small>LEGAL</small></span>
          </Link>
          <nav
            ref={navigation}
            id="public-navigation"
            className={`hx-public-links ${open ? "open" : ""}`}
            aria-label="Main navigation"
            onBlur={(event) => {
              if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== menuButton.current) setOpen(false);
            }}
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
              ref={menuButton}
              type="button"
              className="hx-icon-button hx-mobile-menu"
              aria-controls="public-navigation"
              aria-expanded={open}
              aria-label={open ? "Close navigation" : "Open navigation"}
              disabled={session === undefined}
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
