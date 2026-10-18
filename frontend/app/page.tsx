"use client";

import { useState } from "react";

const services = [
  { icon: "⌂", title: "Home & Apartment", desc: "Support for home ownership, apartment records, rentals and property-related requests.", tags: "Homes · Apartments", slug: "home-apartment-assistance" },
  { icon: "▦", title: "Plot & Land Records", desc: "Get help organizing RTC/Pahani, mutation, survey and land-record requests.", tags: "Plots · Land", slug: "rtc-mutation-assistance" },
  { icon: "§", title: "Legal & Documents", desc: "Coordinate EC, khata and property-document assistance with clear next steps.", tags: "EC · Khata · Records", slug: "ec-assistance" },
  { icon: "✳", title: "Inspection & Reports", desc: "Request a property visit and condition report with photo or video evidence.", tags: "Inspection · Reports", slug: "property-inspection" },
  { icon: "♧", title: "Plot Maintenance", desc: "Ask about plot cleaning, fencing and recurring upkeep in supported areas.", tags: "Cleaning · Upkeep", slug: "plot-maintenance" },
  { icon: "↗", title: "Agent Assistance", desc: "Request a callback, document coordination or delivery where available.", tags: "Follow-up · Delivery", slug: "home-apartment-assistance" },
];

const faqs = [
  { q: "Can I request help for an apartment and a plot?", a: "Yes. Homexo is designed for apartments, independent houses, residential plots and land-related requests. Available services depend on location and scope." },
  { q: "Will Homexo guarantee a government document or legal clearance?", a: "No. Homexo can help coordinate requests and professional review, but government decisions, document availability and legal conclusions cannot be guaranteed." },
  { q: "How do I track my request?", a: "After you submit a request, you receive a ticket number. Customer sign-in and verified ticket tracking will be enabled as the platform's account features are implemented." },
  { q: "Do I need to upload documents immediately?", a: "Not always. Start with the details you have. The operations team can tell you which documents are actually needed for your selected service." },
];

export default function HomePage() {
  const [chatOpen, setChatOpen] = useState(false);
  const [faqOpen, setFaqOpen] = useState<number | null>(0);
  const [selectedService, setSelectedService] = useState(services[0].slug);
  const [form, setForm] = useState({ name: "", contact: "", propertyType: "apartment", location: "", description: "" });
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);

  async function submitRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    setSending(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      const response = await fetch(`${base}/api/v1/tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: form.name,
          contact: form.contact,
          property_type: form.propertyType,
          service_slug: selectedService,
          location: form.location,
          description: form.description,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not submit the request.");
      setNotice(`Request received. Your demo ticket number is ${data.ticket_number}. Save it for reference.`);
      setForm({ name: "", contact: "", propertyType: "apartment", location: "", description: "" });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not connect to Homexo. Please try again.");
    } finally {
      setSending(false);
    }
  }

  function startRequest(slug?: string) {
    if (slug) setSelectedService(slug);
    setChatOpen(true);
    setTimeout(() => document.getElementById("request-panel")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  }

  return (
    <main>
      <div className="topline"><div className="container top-line-inner"><span>Property help, with a clearer next step.</span><span className="top-right">Serving Bengaluru first · Availability varies by service</span></div></div>
      <header className="header">
        <div className="container nav">
          <a className="brand" href="#" aria-label="Homexo homepage"><span className="brand-mark">h<span>•</span></span><span className="brand-word">homexo<span className="brand-dot">.</span><small>PROPERTY SERVICES</small></span></a>
          <nav className="desktop-nav" aria-label="Main navigation">
            <a href="#services">Services</a><a href="#how-it-works">How it works</a><a href="#homes-plots">Homes & plots</a><a href="#faqs">FAQs</a>
          </nav>
          <div className="nav-actions"><a className="track-link" href="#request">Track a request <span>↗</span></a><button className="button button-small" onClick={() => startRequest()}>Start a request <span>→</span></button></div>
        </div>
      </header>

      <section className="hero">
        <div className="hero-shape shape-one" /><div className="hero-shape shape-two" />
        <div className="container hero-grid">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-dot" /> PROPERTY SERVICES, ONE PLACE</div>
            <h1>Property services,<br /><em>made simpler.</em></h1>
            <p className="hero-description">From your apartment’s documents to your plot’s upkeep, get the right next step—with guided requests and clear progress updates.</p>
            <div className="hero-actions"><button className="button" onClick={() => startRequest()}>Tell us what you need <span>→</span></button><a className="text-link" href="#services">Explore services <span>↓</span></a></div>
            <div className="hero-points"><span><b>✓</b> Guided requests</span><span><b>✓</b> Trackable tickets</span><span><b>✓</b> Human follow-up</span></div>
          </div>
          <div className="hero-visual" aria-label="Illustration of a home and apartment buildings">
            <div className="visual-sun" />
            <div className="visual-cloud cloud-a" /><div className="visual-cloud cloud-b" />
            <div className="building building-back"><div className="windows">{Array.from({ length: 12 }, (_, i) => <i key={i} />)}</div></div>
            <div className="building building-mid"><div className="windows">{Array.from({ length: 10 }, (_, i) => <i key={i} />)}</div></div>
            <div className="house"><div className="roof" /><div className="house-body"><div className="house-window" /><div className="door" /><div className="house-window second" /></div></div>
            <div className="visual-ground" />
            <div className="floating-card card-doc"><span className="mini-icon">✓</span><span><b>Request received</b><small>Your next step is clear</small></span></div>
            <div className="floating-card card-status"><span className="status-dot" /><span><b>Progress you can follow</b><small>Every request has a ticket</small></span></div>
          </div>
        </div>
      </section>

      <section className="trust-strip"><div className="container trust-grid"><div><span className="trust-icon">⌂</span><span><b>Homes & apartments</b><small>Ownership to everyday needs</small></span></div><div><span className="trust-icon">▦</span><span><b>Plots & land</b><small>Records to maintenance</small></span></div><div><span className="trust-icon">◎</span><span><b>Clear request tracking</b><small>Know what happens next</small></span></div><div><span className="trust-icon">♧</span><span><b>People to help</b><small>Human review when needed</small></span></div></div></section>

      <section className="section services-section" id="services">
        <div className="container">
          <div className="section-heading"><div><div className="eyebrow">HOW CAN WE HELP?</div><h2>One property. <em>Many needs.</em></h2></div><p>Choose a service to get started. We’ll guide you through the details needed for your request.</p></div>
          <div className="service-grid">{services.map((service, index) => <article className="service-card" key={service.title}><div className={`service-icon icon-${index}`}>{service.icon}</div><div className="service-tags">{service.tags}</div><h3>{service.title}</h3><p>{service.desc}</p><button className="card-link" onClick={() => startRequest(service.slug)}>Request this service <span>↗</span></button></article>)}</div>
        </div>
      </section>

      <section className="split-section" id="homes-plots"><div className="container split-grid">
        <div className="split-panel home-panel"><div className="panel-number">01 / HOMES</div><div className="panel-illustration home-illustration"><div className="illustration-building" /><div className="illustration-house"><span /></div><div className="illustration-tree" /></div><h2>For the place<br />you <em>call home.</em></h2><p>Get help coordinating apartment and independent-home requests, property records, inspections and related services.</p><button className="panel-link" onClick={() => startRequest("home-apartment-assistance")}>Explore home services <span>→</span></button></div>
        <div className="split-panel plot-panel"><div className="panel-number">02 / PLOTS & LAND</div><div className="panel-illustration plot-illustration"><div className="plot-sun" /><div className="plot-boundary"><i /><i /><i /><i /></div><div className="plot-house" /><div className="plot-path" /></div><h2>For the land<br />you <em>look after.</em></h2><p>Organize land-record requests, survey details, plot inspections and maintenance in one place.</p><button className="panel-link" onClick={() => startRequest("rtc-mutation-assistance")}>Explore plot services <span>→</span></button></div>
      </div></section>

      <section className="section steps-section" id="how-it-works"><div className="container"><div className="section-heading centered"><div><div className="eyebrow">A CLEARER WAY FORWARD</div><h2>From question to <em>next step.</em></h2></div><p>No need to figure out every detail before you begin.</p></div>
        <div className="steps-grid"><article className="step"><span className="step-num">01</span><div className="step-icon">☏</div><h3>Tell us what you need</h3><p>Choose a service and answer a few simple, relevant questions.</p></article><article className="step"><span className="step-num">02</span><div className="step-icon">▤</div><h3>Share the details</h3><p>Provide property information and documents when they’re needed.</p></article><article className="step"><span className="step-num">03</span><div className="step-icon">◎</div><h3>We review the request</h3><p>Our team confirms the scope, availability and any estimate.</p></article><article className="step"><span className="step-num">04</span><div className="step-icon">↗</div><h3>Follow the progress</h3><p>Use your ticket to follow updates and the next action.</p></article></div>
      </div></section>

      <section className="cta-section"><div className="container cta-box"><div><div className="eyebrow light-eyebrow">LET’S GET STARTED</div><h2>Every property need<br />starts with a <em>conversation.</em></h2><p>Tell us what you’re trying to get done. We’ll help identify the next step.</p></div><button className="button button-light" onClick={() => startRequest()}>Start your request <span>→</span></button><div className="cta-decoration">h<span>•</span></div></div></section>

      <section className="section faq-section" id="faqs"><div className="container faq-grid"><div><div className="eyebrow">GOOD TO KNOW</div><h2>Questions, <em>answered.</em></h2><p className="faq-intro">A little clarity before you begin.</p><a className="text-link" href="#request">Still need help? Start a request <span>→</span></a></div><div className="faq-list">{faqs.map((faq, i) => <article className={`faq-item ${faqOpen === i ? "open" : ""}`} key={faq.q}><button onClick={() => setFaqOpen(faqOpen === i ? null : i)} aria-expanded={faqOpen === i}><span>{faq.q}</span><b>{faqOpen === i ? "−" : "+"}</b></button>{faqOpen === i && <p>{faq.a}</p>}</article>)}</div></div></section>

      <footer className="footer"><div className="container"><div className="footer-top"><a className="brand footer-brand" href="#"><span className="brand-mark">h<span>•</span></span><span className="brand-word">homexo<span className="brand-dot">.</span><small>PROPERTY SERVICES</small></span></a><p>Property management and service coordination, made simpler.</p><button className="footer-cta" onClick={() => startRequest()}>Start a request ↗</button></div><div className="footer-bottom"><span>© {new Date().getFullYear()} Homexo. All rights reserved.</span><div><a href="#services">Services</a><a href="#how-it-works">How it works</a><a href="#faqs">FAQs</a><a href="mailto:hello@homexo.in">Contact</a></div><span className="footer-note">Service availability and outcomes vary.</span></div></div></footer>

      <button className="chat-fab" aria-label="Open request assistant" onClick={() => startRequest()}><span className="chat-fab-icon">✳</span><span>Need help?</span></button>

      {chatOpen && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) setChatOpen(false); }}>
        <section className="request-modal" id="request-panel" role="dialog" aria-modal="true" aria-labelledby="request-title">
          <div className="modal-head"><div><div className="eyebrow">HOMEXO REQUEST ASSISTANT</div><h2 id="request-title">Let’s get you <em>started.</em></h2><p>Share a few details. The operations team can confirm scope and availability.</p></div><button className="close-modal" onClick={() => setChatOpen(false)} aria-label="Close request form">×</button></div>
          <form onSubmit={submitRequest} className="request-form">
            <label>What service do you need?<select value={selectedService} onChange={(e) => setSelectedService(e.target.value)}>{services.map((s) => <option value={s.slug} key={s.title}>{s.title}</option>)}</select></label>
            <div className="form-row"><label>Your name<input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Full name" /></label><label>Email or phone<input required minLength={5} value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} placeholder="How can we reach you?" /></label></div>
            <div className="form-row"><label>Property type<select value={form.propertyType} onChange={(e) => setForm({ ...form, propertyType: e.target.value })}><option value="apartment">Apartment</option><option value="independent_house">Independent house</option><option value="residential_plot">Residential plot</option><option value="agricultural_land">Agricultural land</option><option value="commercial">Commercial property</option><option value="other">Other</option></select></label><label>Property location<input required minLength={2} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="City / locality" /></label></div>
            <label>Briefly describe what you need<textarea required minLength={5} rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="For example, I need help with an EC for my apartment..." /></label>
            <p className="form-privacy">Please don’t submit Aadhaar numbers, passwords, bank details or sensitive documents in this form. We’ll explain any required documents during follow-up.</p>
            {notice && <div className="form-notice" role="status">{notice}</div>}
            <button className="button submit-button" disabled={sending}>{sending ? "Submitting…" : "Submit request"} <span>→</span></button>
            <p className="form-footnote">Submitting a request does not guarantee service acceptance, a government outcome or a legal conclusion.</p>
          </form>
        </section>
      </div>}
    </main>
  );
}
