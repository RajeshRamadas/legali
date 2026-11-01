import type { Metadata } from "next";
import Link from "next/link";
import { BUNDLES, LIFECYCLE } from "../content";

export const metadata: Metadata = {
  title: "Developer services · Homexo Legal",
  description: "Land screening, acquisition due diligence, bulk registration operations and mutation follow-up for real estate developers in Bangalore.",
};

const enquire = (slug: string) => `/?service=${slug}#callback`;

export default function DevelopersPage() {
  return (
    <>

      <main>
        <section className="developer-intro" id="developers">
          <div className="wrap">
            <div className="developer-hero">
              <div className="developer-copy">
                <div className="eyebrow">For real estate developers</div>
                <h1 className="heading" style={{ fontSize: "clamp(36px,4.6vw,56px)", lineHeight: 1.05, margin: "10px 0 16px" }}>From land acquisition to registered ownership.</h1>
                <p>Coordinate legal due diligence, high-volume registrations and post-registration records through one managed workflow, built for development teams and their buyers.</p>
                <div className="hero-actions">
                  <a className="btn gold" href="#developer-bundles">Explore developer services ↗</a>
                  <Link className="btn light" href={enquire("bulk-registration-operations")}>Talk to our team</Link>
                </div>
                <div className="developer-proof"><span><b>01</b> Screen land before commitment</span><span><b>02</b> Track each registration</span><span><b>03</b> Follow through to mutation</span></div>
              </div>
              <div className="developer-dashboard">
                <div className="dash-top"><div><span className="tiny-label">Illustrative portfolio view</span><h3>Project operations</h3></div><span className="dash-pill">WORKFLOW OVERVIEW</span></div>
                <div className="dash-stats">
                  <div><span>Land parcels</span><b>12</b><small>Due diligence pipeline</small></div>
                  <div><span>Unit registrations</span><b>84</b><small>Across active projects</small></div>
                  <div><span>Post-sale actions</span><b>26</b><small>Mutation / Khata follow-up</small></div>
                </div>
                <div className="dash-list">
                  {[["done", "Land screening", "Evidence collection and title review"], ["active", "Registration execution", "Document readiness and SRO coordination"], ["pending", "Mutation & records", "Post-registration follow-up"]].map(([state, title, sub]) => (
                    <div key={title}><span className={`dash-dot ${state}`} /><span><b>{title}</b><small>{sub}</small></span><em>Workflow stage</em></div>
                  ))}
                </div>
                <p className="dash-note">Illustrative interface only, not live portfolio data or a claim of completed registrations.</p>
              </div>
            </div>
            <div className="lifecycle">
              <div className="lifecycle-heading"><div className="eyebrow">The full lifecycle</div><h3>From raw land to handed-over keys.</h3></div>
              <div className="lifecycle-grid">
                {LIFECYCLE.map((step, i) => (
                  <article key={step.title}><span>{String(i + 1).padStart(2, "0")}</span><div><h4>{step.title}</h4><p>{step.text}</p></div></article>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="section developer-bundles" id="developer-bundles">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Developer product bundles</div><h2 className="heading">Deploy the whole lifecycle,<br />or start with one part.</h2></div><p>Modular services for acquisition, legal, sales and post-sale operations. Scope and capacity are confirmed for each engagement.</p></div>
            <div className="bundle-grid">
              {BUNDLES.map((bundle, i) => (
                <article className={`bundle-card${bundle.featured ? " featured" : ""}`} key={bundle.name}>
                  <span className="bundle-num">{String(i + 1).padStart(2, "0")}</span>
                  <div className="bundle-icon">{bundle.icon}</div>
                  <h3>{bundle.name}</h3>
                  <p className="bundle-audience">{bundle.audience}</p>
                  <div className="bundle-rule" />
                  <span className="tiny-label">Includes</span>
                  <ul>{bundle.items.map((item) => <li key={item}>{item}</li>)}</ul>
                  <Link className={`btn${bundle.featured ? "" : " light"}`} href={enquire(bundle.slug)}>{bundle.cta} →</Link>
                </article>
              ))}
            </div>
            <div className="developer-ops">
              <div><div className="eyebrow">One operations view</div><h3>Know where every parcel and unit stands.</h3><p>Organise case owners, documents, blockers, upcoming appointments and post-registration tasks in one workflow. Portfolio counts and case statuses become live only when connected to your operational backend.</p></div>
              <div className="ops-checks">
                {["Parcel and project records", "Unit-level registration cases", "Document checklist and audit trail", "Pending mutation / Khata tasks", "Buyer-facing progress updates", "Role-based team assignments"].map((item) => <span key={item}>{item}</span>)}
              </div>
            </div>
            <p className="fineprint">Service availability depends on location, records and local execution partners. Stamp duty, registration fees and government charges are separate at actuals. Registration and mutation outcomes are determined by the relevant authorities; legal opinions require qualified advocate review.</p>
          </div>
        </section>

        <section className="final-cta">
          <div className="wrap">
            <div><div className="eyebrow hx-tone-63647bec" >For development teams</div><h2>Tell us about your project.</h2><p>Share the location, parcel or unit volume and timeline, and we&apos;ll scope the engagement with you.</p></div>
            <Link className="btn gold" href={enquire("bulk-registration-operations")}>Talk to our team ↗</Link>
          </div>
        </section>
      </main>


    </>
  );
}
