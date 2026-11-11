"use client";

import { useEffect, useRef, useState } from "react";
import { PROPERTY_TYPES, type PropertyType, type Service } from "@homexo/shared";
import { api } from "./api";
import TrackRequest from "./TrackRequest";
import { SERVICE_OPTIONS, serviceLabel } from "./content";
import { SERVICE_EVENT, type ServiceRequest } from "./homeEvents";
import PropertyIntakeFields, { EMPTY_INTAKE } from "./PropertyIntakeFields";
import Link from "next/link";
import { openDocuments } from "./documents/ref";
import useRetryDelay from "./ui/useRetryDelay";
import FormTrap from "./ui/FormTrap";
import Dialog from "./ui/Dialog";
import { preferredScrollBehavior } from "./ui/utils";

const emptyForm = { name: "", phone: "", email: "", propertyType: "apartment" as PropertyType, location: "", description: "" };

// The callback form, the ticket confirmation and request tracking. Other parts of the site pick a service for it
// with requestService() on this page, or with a link like /?service=affidavit-drafting#callback.
export default function CallbackSection() {
  const [service, setService] = useState("general-guidance");
  const [available, setAvailable] = useState<Service[] | null>(null), [availabilityError, setAvailabilityError] = useState(false);
  const serviceUnavailable = available !== null && !available.some(item => item.slug === service);
  async function refreshAvailability() {
    try { setAvailable(await api.listServices()); setAvailabilityError(false); }
    catch { setAvailabilityError(true); }
  }
  useEffect(() => { refreshAvailability(); }, []);
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [intake, setIntake] = useState(EMPTY_INTAKE);
  const [sending, setSending] = useState(false);
  const [website, setWebsite] = useState("");
  const retry = useRetryDelay();
  const [formError, setFormError] = useState("");
  const [created, setCreated] = useState<{ ticket: string; contact: string; name: string; message: string } | null>(null);
  const [trackPrefill, setTrackPrefill] = useState({ ticket: "", contact: "", key: 0 });
  const [toast, setToast] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const submitButton = useRef<HTMLButtonElement>(null);

  function notify(text: string) {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 3600);
  }

  useEffect(() => {
    function choose({ slug, message, pkg = null, description }: ServiceRequest) {
      setService(slug);
      setSelectedPackage(pkg);
      if (description) setForm((prev) => ({ ...prev, description }));
      document.getElementById("callback")?.scrollIntoView({ behavior: preferredScrollBehavior(), block: "center" });
      setTimeout(() => document.getElementById("fullName")?.focus({ preventScroll: true }), 500);
      notify(message);
    }
    const onService = (event: Event) => choose((event as CustomEvent<ServiceRequest>).detail);
    window.addEventListener(SERVICE_EVENT, onService);

    const slug = new URLSearchParams(window.location.search).get("service");
    if (slug && SERVICE_OPTIONS.some((option) => option.slug === slug)) {
      choose({ slug, message: `${serviceLabel(slug)} selected. Share a few details and we'll call you back.` });
    }

    return () => {
      window.removeEventListener(SERVICE_EVENT, onService);
    };
  }, []);

  async function submitCallback(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending || retry.seconds > 0 || serviceUnavailable) return;
    setFormError("");
    setSending(true);
    try {
      const data = await api.createTicket({
        website_url: website,
        property_intake: intake,
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
      setWebsite("");
      setSelectedPackage(null);
    } catch (error) {
      retry.record(error);
      setFormError(error instanceof Error ? error.message : "We couldn't send your request. Please try again.");
    } finally {
      setSending(false);
    }
  }

  function trackCreated() {
    if (!created) return;
    setTrackPrefill((prev) => ({ ticket: created.ticket, contact: created.contact, key: prev.key + 1 }));
    setCreated(null);
    setTimeout(() => document.getElementById("track")?.scrollIntoView({ behavior: preferredScrollBehavior(), block: "center" }), 50);
  }

  return (
    <>
      <section className="callback-band" id="callback">
        <div className="wrap callback-grid">
          <div>
            <div className="eyebrow">Free expert callback</div>
            <h2>Not sure where to start?</h2>
            <p>Share a few details. A legal specialist will discuss what you need, the scope and the next step with you. You&apos;ll get a request number to track everything.</p>
            <p><Link className="text-link" href={`/request?service=${encodeURIComponent(service)}`}>Prefer one question at a time? Start a guided request you can save and resume.</Link></p>
            {selectedPackage && <p className="selected-package">Package: <b>{selectedPackage}</b> <button type="button" className="text-link" onClick={() => setSelectedPackage(null)}>Remove</button></p>}
          </div>
          <form className="callback-form" onSubmit={submitCallback}>
            <FormTrap value={website} onChange={setWebsite} />
            <div className="field"><label htmlFor="fullName">Full name</label><input id="fullName" placeholder="Your name" autoComplete="name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div className="field"><label htmlFor="phone">Phone number</label><input id="phone" type="tel" placeholder="10-digit mobile number" autoComplete="tel" pattern="[0-9+\(\) \-]{8,18}" required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
            <div className="field"><label htmlFor="email">Email address</label><input id="email" type="email" placeholder="you@email.com" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            <div className="field"><label htmlFor="service">Service needed</label>
              <select id="service" value={service} onChange={(e) => { setService(e.target.value); setSelectedPackage(null); }}>
                {serviceUnavailable && <option value={service} disabled>{serviceLabel(service)} — unavailable</option>}
                {(available ? available.map(item => ({ slug: item.slug, label: item.name })) : SERVICE_OPTIONS).map((option) => <option key={option.slug} value={option.slug}>{option.label}</option>)}
              </select>
              {!availabilityError && available?.find(item => item.slug === service)?.description && <p className="form-note" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{available.find(item => item.slug === service)?.description}</p>}
              {serviceUnavailable && <p role="status">{available?.length ? "This service is not accepting new requests. Choose another service." : "No services are currently accepting new requests. Please try again later."} <button className="text-link" type="button" onClick={refreshAvailability}>Refresh availability</button></p>}
              {availabilityError && <p>Current availability will be checked when you submit. <button className="text-link" type="button" onClick={refreshAvailability}>Refresh availability</button></p>}
            </div>
            <div className="field"><label htmlFor="propertyType">Property type</label>
              <select id="propertyType" value={form.propertyType} onChange={(e) => setForm({ ...form, propertyType: e.target.value as PropertyType })}>
                {PROPERTY_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
              </select>
            </div>
            <div className="field"><label htmlFor="location">Property location</label><input id="location" placeholder="Area, city" required minLength={2} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></div>
            <div className="field wide"><label htmlFor="description">Anything we should know? (optional)</label><textarea id="description" rows={2} placeholder="e.g. Resale 2BHK, registration planned next month" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
            <details className="wide"><summary>Tailor the document checklist to your property</summary><p>These answers help us request the right documents automatically. Choose unknown whenever you are unsure.</p><PropertyIntakeFields value={intake} onChange={setIntake} /></details>
            <button ref={submitButton} className="btn" type="submit" disabled={sending || retry.seconds > 0 || serviceUnavailable}>{sending ? "Sending…" : retry.seconds > 0 ? `Try again in ${retry.seconds}s` : "Request free callback ↗"}</button>
            {formError ? <div className="form-note form-error" role="alert">{formError}</div> : <div className="form-note">Your details are used only to respond to this request.</div>}
          </form>
        </div>
      </section>

      <TrackRequest key={trackPrefill.key} initialTicket={trackPrefill.ticket} initialContact={trackPrefill.contact} />

      <div className={`toast${toast ? " show" : ""}`} role="status" aria-live="polite">{toast}</div>

      <Dialog open={!!created} labelledBy="modalTitle" returnFocusRef={submitButton} className="hx-callback-dialog" onClose={() => setCreated(null)}>
        {created && (
          <div className="modal-box">
            <button className="modal-close" aria-label="Close dialog" onClick={() => setCreated(null)}>×</button>
            <div className="eyebrow">Request received</div>
            <h2 id="modalTitle">Thanks, {created.name.split(" ")[0]}.</h2>
            <div className="ticket-chip"><span>Your ticket number</span><b>{created.ticket}</b></div>
            <p>{created.message} Save this number to track your request.</p>
            <p><Link className="btn light" href="/documents" onClick={() => openDocuments({ ticket_number: created.ticket, contact: created.contact })}>See requested documents and upload</Link></p>
            <div className="modal-actions"><button className="btn" onClick={trackCreated} autoFocus>Track this request</button><button className="btn light" onClick={() => setCreated(null)}>Continue browsing</button></div>
          </div>
        )}
      </Dialog>
    </>
  );
}
