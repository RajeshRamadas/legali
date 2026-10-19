"use client";

import { useEffect, useRef, useState } from "react";
import { PROPERTY_TYPES, type PropertyType } from "@homexo/shared";
import { api } from "./api";
import ChatWidget from "./ChatWidget";
import TrackRequest from "./TrackRequest";
import {
  BUNDLES, DOC_SERVICES, FAQS, LIFECYCLE, PACKAGES, PROCESS, SERVICE_OPTIONS, TESTIMONIALS, VERIFY_SERVICES, WHY, serviceLabel,
} from "./content";

const NAV = [
  ["/lawyers", "Find a lawyer"], ["/rera", "RERA check"], ["#packages", "Packages"], ["#developers", "For developers"], ["#how-it-works", "How it works"], ["#services", "What we verify"],
  ["#document-desk", "Document delivery"], ["#track", "Track request"], ["#faq", "FAQs"], ["/blog", "Insights"],
];

const emptyForm = { name: "", phone: "", email: "", propertyType: "apartment" as PropertyType, location: "", description: "" };

export default function HomePage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [faqOpen, setFaqOpen] = useState<number | null>(null);
  const [service, setService] = useState("title-verification");
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [sending, setSending] = useState(false);
  const [formError, setFormError] = useState("");
  const [created, setCreated] = useState<{ ticket: string; contact: string; name: string; message: string } | null>(null);
  const [trackPrefill, setTrackPrefill] = useState({ ticket: "", contact: "", key: 0 });
  const [toast, setToast] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout>>();

  function notify(text: string) {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 3600);
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setCreated(null);
        setMenuOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Preselect a service in the callback form and take the visitor there.
  function chooseService(slug: string, message: string, pkg: string | null = null) {
    setService(slug);
    setSelectedPackage(pkg);
    document.getElementById("callback")?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => document.getElementById("fullName")?.focus({ preventScroll: true }), 500);
    notify(message);
  }

  async function submitCallback(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setSending(true);
    try {
      const data = await api.createTicket({
        customer_name: form.name.trim(),
        contact: form.phone.trim(),
        email: form.email.trim() || undefined,
        property_type: form.propertyType,
        service_slug: service,
        package: selectedPackage ?? undefined,
        location: form.location.trim(),
        description: form.description.trim(),
        source: "website",
      });
      setCreated({ ticket: data.ticket_number, contact: form.phone.trim(), name: form.name.trim(), message: data.message });
      setForm(emptyForm);
      setSelectedPackage(null);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "We couldn't send your request. Please try again.");
    } finally {
      setSending(false);
    }
  }

  function trackCreated() {
    if (!created) return;
    setTrackPrefill((prev) => ({ ticket: created.ticket, contact: created.contact, key: prev.key + 1 }));
    setCreated(null);
    setTimeout(() => document.getElementById("track")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  }

  return (
    <>
      <div className="topline"><div className="wrap"><span><strong>Property legal services · Bangalore</strong> &nbsp; For buyers and real estate developers.</span><span>Speak to a specialist: <a href="#callback"><strong>Request a free callback</strong></a></span></div></div>
      <header className="header">
        <div className="wrap navrow">
          <a className="brand" href="#home" aria-label="Homexo Legal home"><span className="brandmark">H</span><span>homexo legal<small>Property clarity, end to end</small></span></a>
          <nav className={`navlinks${menuOpen ? " is-open" : ""}`} id="navlinks" aria-label="Main navigation">
            {NAV.map(([href, label]) => <a key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</a>)}
          </nav>
          <div className="navright">
            <a className="btn small" href="#callback">Get free callback ↗</a>
            <button className="menu" aria-expanded={menuOpen} aria-controls="navlinks" aria-label={menuOpen ? "Close navigation" : "Open navigation"} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? "×" : "☰"}</button>
          </div>
        </div>
      </header>

      <main id="home">
        <section className="hero">
          <div className="wrap hero-grid">
            <div>
              <div className="eyebrow">Property legal verification · Bangalore</div>
              <h1 className="serif">Buy your home<br />with complete <em>confidence.</em></h1>
              <p className="hero-copy">Property verification, registration support and post-purchase assistance—with fixed-fee packages, clear status updates and a plain-English Go / Investigate / Do Not Proceed verdict.</p>
              <div className="hero-actions"><a className="btn" href="#packages">View packages <span>↗</span></a><a className="btn light" href="/lawyers">Book a lawyer consultation ↗</a><a className="btn light" href="#how-it-works">See how it works ↓</a></div>
              <div className="trustline"><span>Transparent package pricing</span><span>Advocate-led review</span><span>Case status updates</span></div>
            </div>
            <div className="hero-visual">
              <div className="visual-frame">
                <div className="verdict">
                  <div className="verdict-top"><div className="verdict-brand">homexo legal<br /><span className="tiny-label">Property review summary</span></div><span className="tiny-label">Illustrative preview</span></div>
                  <h3>Property Legal Verdict</h3>
                  <div className="verdict-sub">A clear summary of checks, open issues and next steps.</div>
                  <div className="verdict-badge"><i /> REVIEW IN PROGRESS</div>
                  <div className="checks">
                    {[["✓", "Title chain"], ["✓", "EC review"], ["✓", "RERA / approvals"], ["…", "Litigation search"], ["…", "SRO records"], ["→", "Lawyer review"]].map(([mark, label]) => (
                      <div className="check" key={label}><b>{mark}</b> {label}</div>
                    ))}
                  </div>
                  <div className="verdict-foot"><span>Case status: evidence review</span><span>Updated by case team</span></div>
                </div>
              </div>
              <div className="floating-note"><strong>One clear next step</strong>Know what is verified—and what still needs attention.</div>
            </div>
          </div>
        </section>

        <section className="stats">
          <div className="wrap stats-grid">
            <div className="stat"><b>₹4,999</b><span>Starting package price</span></div>
            <div className="stat"><b>5–7 days</b><span>Typical Pro package turnaround</span></div>
            <div className="stat"><b>Fixed fee</b><span>Scope explained upfront</span></div>
            <div className="stat"><b>End to end</b><span>Verification to post-purchase support</span></div>
          </div>
        </section>

        <section className="developer-intro" id="developers">
          <div className="wrap">
            <div className="developer-hero">
              <div className="developer-copy">
                <div className="eyebrow">For real estate developers</div>
                <h2 className="serif">From land acquisition to registered ownership.</h2>
                <p>Coordinate legal due diligence, high-volume registrations and post-registration records through one managed workflow—built for development teams and their buyers.</p>
                <div className="hero-actions">
                  <a className="btn gold" href="#developer-bundles">Explore developer services ↗</a>
                  <button className="btn light" onClick={() => chooseService("bulk-registration-operations", "Developer services selected. Tell us about your project in the callback form.")}>Talk to our team</button>
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
                <p className="dash-note">Illustrative interface only—not live portfolio data or a claim of completed registrations.</p>
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
            <div className="section-head"><div><div className="eyebrow">Developer product bundles</div><h2 className="serif">Deploy the whole lifecycle,<br />or start with one part.</h2></div><p>Modular services for acquisition, legal, sales and post-sale operations. Scope and capacity are confirmed for each engagement.</p></div>
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
                  <button className={`btn${bundle.featured ? "" : " light"}`} onClick={() => chooseService(bundle.slug, `${bundle.name} selected. Share your project location, parcel or unit volume and timeline.`)}>{bundle.cta} →</button>
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

        <section className="section pricing" id="packages">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Service packages</div><h2 className="serif">One flat fee.<br />Clear scope. No surprises.</h2></div><p>Choose the level of support that matches your property and transaction. Stamp duty, registration fees and government charges are billed at actuals.</p></div>
            <div className="price-grid">
              {PACKAGES.map((pkg) => (
                <article className={`price-card${pkg.popular ? " popular" : ""}`} key={pkg.name}>
                  {pkg.popular && <div className="popular-tag">Most popular</div>}
                  <div className="tier">{pkg.tier}</div>
                  <h3>{pkg.name}</h3>
                  <div className="price">{pkg.price}</div>
                  <div className="delivery">◷ {pkg.delivery}</div>
                  <ul className="features">{pkg.features.map((f) => <li key={f.text} className={f.off ? "off" : undefined}>{f.text}</li>)}</ul>
                  <button className={`btn${pkg.popular ? "" : " light"}`} onClick={() => chooseService(pkg.slug, `${pkg.name} selected. Request a callback so we can confirm scope, documents and payment.`, pkg.name)}>{pkg.cta} →</button>
                </article>
              ))}
            </div>
            <p className="fineprint">Turnaround times depend on document completeness, record availability and case complexity. Stamp duty, registration fees and government charges are separate. Final legal opinions and statutory decisions are made by the qualified advocate or relevant authority.</p>
          </div>
        </section>

        <section className="callback-band" id="callback">
          <div className="wrap callback-grid">
            <div>
              <div className="eyebrow">Free expert callback</div>
              <h2>Not sure what your property needs?</h2>
              <p>Share a few details. A legal specialist can discuss the property, the service scope and the next step with you. You&apos;ll get a ticket number to track your request.</p>
              {selectedPackage && <p className="selected-package">Package: <b>{selectedPackage}</b> <button type="button" className="text-link" onClick={() => setSelectedPackage(null)}>Remove</button></p>}
            </div>
            <form className="callback-form" onSubmit={submitCallback}>
              <div className="field"><label htmlFor="fullName">Full name</label><input id="fullName" placeholder="Your name" autoComplete="name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div className="field"><label htmlFor="phone">Phone number</label><input id="phone" type="tel" placeholder="10-digit mobile number" autoComplete="tel" pattern="[0-9+\(\) \-]{8,18}" required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
              <div className="field"><label htmlFor="email">Email address</label><input id="email" type="email" placeholder="you@email.com" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
              <div className="field"><label htmlFor="service">Service needed</label>
                <select id="service" value={service} onChange={(e) => { setService(e.target.value); setSelectedPackage(null); }}>
                  {SERVICE_OPTIONS.map((option) => <option key={option.slug} value={option.slug}>{option.label}</option>)}
                </select>
              </div>
              <div className="field"><label htmlFor="propertyType">Property type</label>
                <select id="propertyType" value={form.propertyType} onChange={(e) => setForm({ ...form, propertyType: e.target.value as PropertyType })}>
                  {PROPERTY_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                </select>
              </div>
              <div className="field"><label htmlFor="location">Property location</label><input id="location" placeholder="Area, city" required minLength={2} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></div>
              <div className="field wide"><label htmlFor="description">Anything we should know? (optional)</label><textarea id="description" rows={2} placeholder="e.g. Resale 2BHK, registration planned next month" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
              <button className="btn" type="submit" disabled={sending}>{sending ? "Sending…" : "Request free callback ↗"}</button>
              {formError ? <div className="form-note form-error" role="alert">{formError}</div> : <div className="form-note">Your details are used only to respond to this request.</div>}
            </form>
          </div>
        </section>

        <TrackRequest key={trackPrefill.key} initialTicket={trackPrefill.ticket} initialContact={trackPrefill.contact} />

        <section className="section consult" id="consultation">
          <div className="wrap consult-grid">
            <div>
              <div className="eyebrow">Add-on service</div>
              <h2 className="serif">Start with a conversation. Make the next move with clarity.</h2>
              <p>Book a 30-minute consultation with a senior property advocate before choosing a package—or as a standalone service. Discuss your property, documents, concerns and the verification scope that makes sense.</p>
              <div className="trustline"><span style={{ color: "#d5e7df" }}>Property-specific questions</span><span style={{ color: "#d5e7df" }}>Risk discussion</span><span style={{ color: "#d5e7df" }}>Written summary</span></div>
            </div>
            <div className="consult-card">
              <div className="consult-card-top"><div><div className="eyebrow">Video consultation</div><h3>Talk to an advocate</h3><div className="tiny-label">30 minutes · 1-on-1</div></div><div className="consult-price">₹999</div></div>
              <ul>
                <li>Discuss your property, documents or concerns</li><li>Understand the headline risk profile and next steps</li><li>Get a customized document checklist</li><li>Receive a written summary by email</li><li>₹999 credited toward a Shield package ordered within 7 days</li>
              </ul>
              <button className="btn" onClick={() => chooseService("advocate-consultation", "Consultation selected. We'll confirm advocate availability when we call.")}>Enquire about a consultation →</button>
            </div>
          </div>
        </section>

        <section className="section process" id="how-it-works">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">How it works</div><h2 className="serif">Real transparency<br />from day one.</h2></div><p>Follow your order from document intake to lawyer-reviewed findings. Updates should reflect the actual case status—never a simulated live government lookup.</p></div>
            <div className="process-grid">
              {PROCESS.map((step, i) => (
                <article className="process-card" key={step.title}><div className="process-num">{String(i + 1).padStart(2, "0")}</div><div><h3>{step.title}</h3><p>{step.text}</p><div className="message-example">{step.message}</div></div></article>
              ))}
            </div>
          </div>
        </section>

        <section className="section services" id="services">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">What we verify &amp; handle</div><h2 className="serif">Every angle of your<br />property’s legal health.</h2></div><p>From historical title and compliance to drafting, registration coordination and post-purchase paperwork—see the scope in one place.</p></div>
            <div className="service-grid">
              {VERIFY_SERVICES.map((item) => (
                <article className="service-card" key={item.title}><div className="service-icon">{item.icon}</div><h3>{item.title}</h3><p>{item.text}</p><div className="tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></article>
              ))}
            </div>
          </div>
        </section>

        <section className="section why">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Why Homexo Legal</div><h2 className="serif">A legal product.<br />Built around the buyer.</h2></div><p>Make a high-stakes decision with a clearer process, a defined scope and a place to track what happens next.</p></div>
            <div className="why-grid">
              {WHY.map((item) => <article className="why-card" key={item.title}><div className="why-icon">{item.icon}</div><h3>{item.title}</h3><p>{item.text}</p></article>)}
            </div>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Customer stories</div><h2 className="serif">Clarity for the<br />biggest purchase.</h2></div><p>Illustrative testimonials from the supplied content. Publish only after obtaining customer consent and verifying each statement.</p></div>
            <div className="testimonial-grid">
              {TESTIMONIALS.map((t) => <article className="quote" key={t.name}><div className="quote-mark">“</div><p>{t.quote}</p><strong>{t.name}</strong><small>{t.role}</small></article>)}
            </div>
          </div>
        </section>

        <section className="section faq" id="faq">
          <div className="wrap faq-grid">
            <div>
              <div className="eyebrow">FAQs</div>
              <h2 className="serif" style={{ fontSize: 42, color: "var(--forest)", margin: "10px 0 14px" }}>Questions before you begin?</h2>
              <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7 }}>Start with a callback or a consultation if you are unsure which service fits your property.</p>
              <a className="btn" href="#callback">Ask a specialist →</a>
            </div>
            <div className="faq-list">
              {FAQS.map((item, i) => (
                <div className={`faq-item${faqOpen === i ? " open" : ""}`} key={item.q}>
                  <button className="faq-q" aria-expanded={faqOpen === i} onClick={() => setFaqOpen(faqOpen === i ? null : i)}>{item.q}<span>+</span></button>
                  <div className="faq-a">{item.a}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="section document-desk" id="document-desk">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Stay home. We handle the paperwork.</div><h2 className="serif">Property documents,<br />delivered to your door.</h2></div><p>Request eligible property-related documents or document services from home. Our team helps clarify the requirements, coordinates the process, and arranges secure courier delivery when physical delivery is available.</p></div>
            <div className="doc-desk-grid">
              <div className="doc-desk-copy">
                <div className="doc-desk-badge">⌂ &nbsp; Home-to-home service</div>
                <h3>One request. A team to take it forward.</h3>
                <p>Tell us which document you need and where the property is located. We’ll confirm the issuing authority, eligibility, required authorisation, expected timeline and government charges before proceeding.</p>
                <div className="doc-benefits"><span>✓ Document checklist and guidance</span><span>✓ Agent coordination where required</span><span>✓ Request status and follow-up</span><span>✓ Courier tracking for physical documents</span></div>
                <button className="btn gold" onClick={() => chooseService("document-retrieval-courier", "Document retrieval and courier selected. Describe the document you need in the form.")}>Request a document ↗</button>
                <small className="doc-disclaimer">Availability depends on the issuing authority, document type, applicant eligibility and authorisation. Government fees, agent visits and courier charges are quoted separately where applicable.</small>
              </div>
              <div className="doc-service-list">
                {DOC_SERVICES.map((doc) => (
                  <article key={doc.title}>
                    <span className="doc-icon">{doc.icon}</span>
                    <div><h4>{doc.title}</h4><p>{doc.text}</p><button type="button" className="text-link" onClick={() => chooseService(doc.slug, `${serviceLabel(doc.slug)} selected. Complete the form and we'll confirm availability, fees and delivery.`)}>Request this service <span>↗</span></button></div>
                  </article>
                ))}
                <div className="courier-flow">
                  {["Request", "We coordinate", "Verify & dispatch", "Delivered"].map((step, i) => (
                    <span key={step} style={{ display: "contents" }}>
                      {i > 0 && <i>→</i>}
                      <div className="courier-step"><b>{String(i + 1).padStart(2, "0")}</b><span>{step}</span></div>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="final-cta">
          <div className="wrap">
            <div><div className="eyebrow" style={{ color: "#cce4d7" }}>Property due diligence</div><h2>Verify first. Register with confidence.</h2><p>From document review to registration coordination and post-purchase follow-up.</p></div>
            <a className="btn gold" href="#callback">Get a free callback ↗</a>
          </div>
        </section>
      </main>

      <footer className="footer">
        <div className="wrap">
          <div className="footer-grid">
            <div><a className="brand" href="#home"><span className="brandmark">H</span><span>homexo legal<small style={{ color: "#a4bcb2" }}>Property clarity, end to end</small></span></a><p>Property legal verification, acquisition due diligence, registration coordination and post-registration support for buyers and developers in Bangalore.</p></div>
            <div><h4>Explore</h4><a href="/lawyers">Find a lawyer</a><a href="/rera">RERA project check</a><a href="/bookings">My bookings</a><a href="#packages">Buyer packages</a><a href="#developers">Developer services</a><a href="#developer-bundles">Developer bundles</a><a href="#how-it-works">How it works</a><a href="#services">What we verify</a><a href="#consultation">Advocate consultation</a></div>
            <div><h4>Property services</h4><a href="#services">Title &amp; EC</a><a href="#services">Sale deed / agreement</a><a href="#services">Registration</a><a href="#services">Khata &amp; tax</a><a href="#document-desk">Document retrieval &amp; courier</a></div>
            <div><h4>Important</h4><a href="/blog">Insights &amp; case studies</a><a href="#track">Track a request</a><a href="#faq">FAQs</a><a href="#callback">Contact</a><a href="#faq">Scope &amp; limitations</a></div>
          </div>
          <div className="copyright">© 2026 Homexo Legal. Service scope, delivery estimates and availability depend on the selected package and property records. Legal opinions must be provided by a qualified advocate; government fees and statutory decisions remain with the relevant authority. Homexo does not connect to live government systems.</div>
        </div>
      </footer>

      <div className={`toast${toast ? " show" : ""}`} role="status" aria-live="polite">{toast}</div>

      <div className={`modal${created ? " show" : ""}`} role="dialog" aria-modal="true" aria-labelledby="modalTitle" onClick={(e) => e.target === e.currentTarget && setCreated(null)}>
        {created && (
          <div className="modal-box">
            <button className="modal-close" aria-label="Close dialog" onClick={() => setCreated(null)}>×</button>
            <div className="eyebrow">Request received</div>
            <h2 id="modalTitle">Thanks, {created.name.split(" ")[0]}.</h2>
            <div className="ticket-chip"><span>Your ticket number</span><b>{created.ticket}</b></div>
            <p>{created.message} Save this number to track your request.</p>
            <div className="modal-actions"><button className="btn" onClick={trackCreated} autoFocus>Track this request</button><button className="btn light" onClick={() => setCreated(null)}>Continue browsing</button></div>
          </div>
        )}
      </div>

      <ChatWidget />
    </>
  );
}
