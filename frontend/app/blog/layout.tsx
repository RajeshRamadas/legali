import Link from "next/link";
import "./blog.css";

export default function BlogLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="header">
        <div className="wrap navrow">
          <Link className="brand" href="/" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></Link>
          <nav className="blog-nav" aria-label="Main navigation">
            <Link href="/#packages">Packages</Link>
            <Link href="/#developers">For developers</Link>
            <Link href="/blog" className="active">Insights</Link>
            <Link href="/#track">Track request</Link>
          </nav>
          <Link className="btn small" href="/#callback">Get free callback ↗</Link>
        </div>
      </header>
      <main className="blog">{children}</main>
      <footer className="footer">
        <div className="wrap">
          <div className="copyright">© 2026 Homexo Legal. Articles and case studies are general information, not legal advice for your property. Legal opinions must be provided by a qualified advocate. Client details in case studies are shared with consent or anonymised.</div>
        </div>
      </footer>
    </>
  );
}
