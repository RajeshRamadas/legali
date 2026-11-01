import Link from "next/link";

export default function SiteFooter() {
  return (
    <footer className="footer">
      <div className="wrap">
        <div className="footer-grid">
          <div><Link className="brand" href="/"><span className="brandmark">H</span><span>homexo legal<small className="hx-tone-78cc9b2f" >Property clarity, end to end</small></span></Link><p>Property legal verification, lawyer consultations, documents, registration coordination and post-registration support for buyers and developers in Bangalore.</p></div>
          <div><h4>Get it done</h4><Link href="/rera">RERA project check</Link><Link href="/lawyers">Find a lawyer</Link><Link href="/bookings">My bookings</Link><Link href="/documents">My documents</Link><Link href="/#packages">Buyer packages</Link><Link href="/#track">Track a request</Link></div>
          <div><h4>Services</h4><Link href="/services">What we verify</Link><Link href="/services#documents">Documents &amp; courier</Link><Link href="/services#documents">Affidavits &amp; deeds</Link><Link href="/developers">Developer services</Link></div>
          <div><h4>Important</h4><Link href="/blog">Insights &amp; case studies</Link><Link href="/#faq">FAQs</Link><Link href="/#callback">Contact</Link><Link href="/services#process">How a verification runs</Link></div>
        </div>
        <div className="copyright">© 2026 Homexo Legal. Service scope, delivery estimates and availability depend on the selected package and property records. Legal opinions must be provided by a qualified advocate; government fees and statutory decisions remain with the relevant authority. Homexo does not connect to live government systems.</div>
      </div>
    </footer>
  );
}
