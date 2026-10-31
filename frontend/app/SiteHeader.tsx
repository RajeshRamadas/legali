"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AccountLink from "./account/AccountLink";

const NAV = [
  ["/rera", "RERA check"], ["/lawyers", "Find a lawyer"], ["/#packages", "Verify a property"], ["/services#documents", "Documents"],
  ["/developers", "For developers"], ["/blog", "Insights"],
];

export default function SiteHeader() {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <div className="topline"><div className="wrap"><span><strong>Property &amp; legal help · Bangalore</strong> &nbsp; For home buyers, families and developers.</span><span>Questions? Ask our assistant, or <Link href="/#callback"><strong>request a free callback</strong></Link></span></div></div>
      <header className="header">
        <div className="wrap navrow">
          <Link className="brand" href="/" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></Link>
          <nav className={`navlinks${menuOpen ? " is-open" : ""}`} id="navlinks" aria-label="Main navigation">
            {NAV.map(([href, label]) => <Link key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</Link>)}
            <Link className="nav-only-menu" href="/#track" onClick={() => setMenuOpen(false)}>Track request</Link>
            <AccountLink className="nav-only-menu" onClick={() => setMenuOpen(false)} />
          </nav>
          <div className="navright">
            <AccountLink className="nav-account" />
            <Link className="btn small light hide-md" href="/#track">Track request</Link>
            <Link className="btn small" href="/#callback">Get free callback ↗</Link>
            <button className="menu" aria-expanded={menuOpen} aria-controls="navlinks" aria-label={menuOpen ? "Close navigation" : "Open navigation"} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? "×" : "☰"}</button>
          </div>
        </div>
      </header>
    </>
  );
}
