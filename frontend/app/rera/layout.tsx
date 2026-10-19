import Link from "next/link";
import "./rera.css";

export default function ReraLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="header">
        <div className="wrap navrow">
          <Link className="brand" href="/" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></Link>
          <nav className="rr-nav" aria-label="Main navigation">
            <Link href="/rera" className="active">RERA project check</Link>
            <Link href="/lawyers" className="hide-sm">Find a lawyer</Link>
            <Link href="/#packages" className="hide-sm">Packages</Link>
            <Link href="/blog" className="hide-sm">Insights</Link>
          </nav>
          <Link className="btn small hide-sm" href="/#callback">Get free callback ↗</Link>
        </div>
      </header>
      <main className="rr">{children}</main>
      <footer className="footer">
        <div className="wrap">
          <div className="copyright">
            © 2026 Homexo Legal. Project details are compiled from Karnataka RERA (K-RERA) registrations and may lag the RERA portal; check the
            latest record at rera.karnataka.gov.in. Warning signs are worked out automatically from that record and are not a legal opinion on any
            project, developer or unit. Homexo Legal is not affiliated with K-RERA.
          </div>
        </div>
      </footer>
    </>
  );
}
