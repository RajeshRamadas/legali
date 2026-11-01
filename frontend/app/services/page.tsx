import type { Metadata } from "next";
import Link from "next/link";
import { DOC_SERVICES, PROCESS, VERIFY_SERVICES } from "../content";

export const metadata: Metadata = {
  title: "Property services, documents and affidavits · Homexo Legal",
  description: "What Homexo Legal verifies and handles: title and EC, approvals, SRO checks, drafting, Khata and tax, government documents with courier delivery, and affidavits.",
};

const request = (slug: string) => `/?service=${slug}#callback`;

export default function ServicesPage() {
  return (
    <>

      <main>
        <section className="section services" id="verify">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">What we verify &amp; handle</div><h1 className="heading hx-tone-b0e08465" style={{ fontSize: "clamp(36px,4.4vw,52px)", lineHeight: 1.06, margin: "9px 0 0" }}>Every angle of your<br />property’s legal health.</h1></div><p>From historical title and compliance to drafting, registration coordination and post-purchase paperwork. <Link className="hx-tone-b2722ad7" href="/#packages" style={{ fontWeight: 700 }}>Compare packages →</Link></p></div>
            <div className="service-grid">
              {VERIFY_SERVICES.map((item) => (
                <article className="service-card" key={item.title}><div className="service-icon">{item.icon}</div><h3>{item.title}</h3><p>{item.text}</p><div className="tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></article>
              ))}
            </div>
          </div>
        </section>

        <section className="section document-desk" id="documents">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Stay home. We handle the paperwork.</div><h2 className="heading">Documents and affidavits,<br />delivered to your door.</h2></div><p>Request property documents, deeds or an affidavit from home. Our team confirms the requirements, coordinates the process, and arranges secure courier delivery when physical delivery is available.</p></div>
            <div className="doc-desk-grid">
              <div className="doc-desk-copy">
                <div className="doc-desk-badge">⌂ &nbsp; Home-to-home service</div>
                <h3>One request. A team to take it forward.</h3>
                <p>Tell us which document you need and where the property is located. We’ll confirm the issuing authority, eligibility, required authorisation, expected timeline and government charges before proceeding.</p>
                <div className="doc-benefits"><span>✓ Document checklist and guidance</span><span>✓ Agent coordination where required</span><span>✓ Request status and follow-up</span><span>✓ Courier tracking for physical documents</span></div>
                <Link className="btn gold" href={request("document-retrieval-courier")}>Request a document ↗</Link>
                <small className="doc-disclaimer">Availability depends on the issuing authority, document type, applicant eligibility and authorisation. Government fees, stamp paper, notary, agent visits and courier charges are quoted separately where applicable.</small>
              </div>
              <div className="doc-service-list">
                {DOC_SERVICES.map((doc) => (
                  <article key={doc.title}>
                    <span className="doc-icon">{doc.icon}</span>
                    <div><h4>{doc.title}</h4><p>{doc.text}</p><Link className="text-link" href={request(doc.slug)}>Request this service <span>↗</span></Link></div>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="section process" id="process">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">How a verification runs</div><h2 className="heading">Real transparency<br />from day one.</h2></div><p>Follow your order from document intake to lawyer-reviewed findings. Updates reflect the actual case status, never a simulated live government lookup.</p></div>
            <div className="process-grid">
              {PROCESS.map((step, i) => (
                <article className="process-card" key={step.title}><div className="process-num">{String(i + 1).padStart(2, "0")}</div><div><h3>{step.title}</h3><p>{step.text}</p><div className="message-example">{step.message}</div></div></article>
              ))}
            </div>
          </div>
        </section>

        <section className="final-cta">
          <div className="wrap">
            <div><div className="eyebrow hx-tone-63647bec" >Not sure which service fits?</div><h2>Ask us. We&apos;ll point you to the right one.</h2><p>A specialist will discuss the property, the scope and the next step with you.</p></div>
            <Link className="btn gold" href={request("general-guidance")}>Get a free callback ↗</Link>
          </div>
        </section>
      </main>


    </>
  );
}
