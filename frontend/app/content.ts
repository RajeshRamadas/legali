// Static copy for the home page. Service slugs mirror SERVICES in backend/app/catalogue.py.

export const SERVICE_OPTIONS = [
  { slug: "title-verification", label: "Title Verification" },
  { slug: "legal-due-diligence", label: "Full Legal Due Diligence" },
  { slug: "sale-agreement-deed", label: "Sale Agreement / Sale Deed" },
  { slug: "property-registration", label: "Property Registration" },
  { slug: "khata-tax-bescom-transfer", label: "Khata / Tax / BESCOM Transfer" },
  { slug: "developer-land-screening", label: "Developer Land Screening" },
  { slug: "acquisition-due-diligence", label: "Acquisition Due Diligence" },
  { slug: "bulk-registration-operations", label: "Bulk Registration Operations" },
  { slug: "mutation-records-management", label: "Mutation & Records Management" },
  { slug: "document-retrieval-courier", label: "Government Document Retrieval & Courier" },
  { slug: "certified-copy-ec", label: "Certified Copy / Encumbrance Certificate" },
  { slug: "rtc-mutation-survey-records", label: "RTC / Mutation / Survey Records" },
  { slug: "khata-property-tax-documents", label: "Khata / Property Tax Documents" },
  { slug: "deed-drafting-registration", label: "Deed Drafting / Registration Support" },
  { slug: "affidavit-drafting", label: "Affidavit Drafting & Notarisation" },
  { slug: "advocate-consultation", label: "Advocate Consultation" },
  { slug: "general-guidance", label: "Not sure — need guidance" },
];

export function serviceLabel(slug: string) {
  return SERVICE_OPTIONS.find((option) => option.slug === slug)?.label ?? "Selected service";
}

type Feature = { text: string; off?: boolean };
const on = (...items: string[]): Feature[] => items.map((text) => ({ text }));
const off = (...items: string[]): Feature[] => items.map((text) => ({ text, off: true }));

export const PACKAGES = [
  {
    tier: "Tier 01", name: "Shield Starter", price: "₹4,999", delivery: "Delivery in 48–72 hours", slug: "title-verification", cta: "Choose Starter", summary: "Title, EC, RERA and litigation checks with a Go / No-Go verdict",
    features: [...on("Title deed verification", "Encumbrance Certificate check", "RERA registration check", "Basic litigation check", "1-page Go / No-Go verdict PDF", "WhatsApp status updates"), ...off("SRO field verification", "Sale Agreement drafting", "Khata Transfer support"), ...on("1 video consultation session")],
  },
  {
    tier: "Tier 02", name: "Shield Pro", price: "₹9,999", delivery: "Delivery in 5–7 working days", slug: "legal-due-diligence", cta: "Choose Pro", popular: true, summary: "30-year title history, SRO field check and a buyer-protective sale agreement",
    features: [...on("Everything in Starter", "30-year title history check", "Mother Deed chain verification", "BBMP / BDA / BMRDA audit", "Land acquisition notice check", "SRO physical field verification", "Buyer-protective Sale Agreement", "Khata & property tax records"), ...off("Khata Transfer execution"), ...on("2 video consultation sessions")],
  },
  {
    tier: "Tier 03", name: "Shield Complete", price: "₹18,999", delivery: "7–10 days + post-purchase support", slug: "property-registration", cta: "Choose Complete", summary: "Sale deed, registration, Khata transfer and 12 months of help after purchase",
    features: on("Everything in Pro", "Sale Deed drafting & registration support", "Khata Transfer (BBMP / BDA)", "Property tax name change", "BESCOM name change support", "Aadhaar eSign support for documents", "Secure document vault", "12-month post-purchase helpline", "Dedicated advocate assigned", "3 video consultation sessions"),
  },
];

export const BUNDLES = [
  { icon: "⌕", name: "Land Screening", audience: "For BD and land acquisition teams", slug: "developer-land-screening", cta: "Enquire about screening", items: ["Initial title and ownership checks", "Encumbrance and land-classification review", "Survey identity and document-gap flags", "Preliminary risk summary"] },
  { icon: "▤", name: "Acquisition Due Diligence", audience: "For legal and acquisition leaders", slug: "acquisition-due-diligence", cta: "Enquire about diligence", items: ["Historical title-chain reconstruction", "Revenue, survey and EC reconciliation", "Litigation and restriction checks", "Development-rights review and lawyer report"] },
  { icon: "▣", name: "Registration Operations", audience: "For projects with multiple unit sales", slug: "bulk-registration-operations", cta: "Enquire about registration", featured: true, items: ["Unit-level readiness checklist", "Buyer / seller document coordination", "Deed and SRO appointment coordination", "Registration progress and deed collection tracking"] },
  { icon: "↻", name: "Mutation & Records Hygiene", audience: "For portfolio and post-sale teams", slug: "mutation-records-management", cta: "Enquire about records", items: ["Mutation application follow-up", "Khata and property-tax updates", "Utility transfer coordination where applicable", "Pending-task dashboard and document archive"] },
];

export const LIFECYCLE = [
  { title: "Land & acquisition", text: "Screen parcels, reconstruct title and identify material gaps before you commit." },
  { title: "Registration execution", text: "Coordinate documents, deed readiness, SRO appointments and registration-day tasks." },
  { title: "Mutation & records", text: "Track mutation, Khata, tax and utility-name-change follow-up after registration." },
  { title: "Buyer handover", text: "Give buyers a clearer checklist, visible progress and organised ownership documents." },
];

export const PROCESS = [
  { title: "Order placed", text: "Choose a package, share property details and upload the documents available to you.", message: "“Your order is confirmed. Your secure document checklist is ready.”" },
  { title: "Title review", text: "Review title chain, EC, RERA, approvals and available litigation/acquisition records.", message: "“Initial checks are underway. EC and title-chain review are in progress.”" },
  { title: "Record verification", text: "Where included and feasible, coordinate physical SRO checks and communicate progress.", message: "“SRO verification is scheduled. We’ll share the confirmed update.”" },
  { title: "Verdict prepared", text: "Evidence, conflicts and open questions are organized for the advocate’s review.", message: "“Your report is in lawyer review. We’ll notify you when it’s ready.”" },
  { title: "Next step", text: "Receive the report and guidance on proceeding, resolving issues or investigating further.", message: "“Your reviewed report is ready, with findings and recommended actions.”" },
];

export const VERIFY_SERVICES = [
  { icon: "⌕", title: "Title verification & EC", text: "Review title deed chain, Mother Deed, Encumbrance Certificate and relevant transfer records. Flag gaps and potential conflicts for advocate assessment.", tags: ["Mother Deed", "EC check", "Title chain"] },
  { icon: "⌂", title: "Approval & compliance audit", text: "Check applicable RERA, BBMP/BDA/BMRDA approvals, zoning, OC/CC and available acquisition notices.", tags: ["RERA", "BBMP", "BDA", "BMRDA"] },
  { icon: "⌖", title: "SRO field verification", text: "Where included in the package, coordinate a physical check of relevant registration-office records and report confirmed findings.", tags: ["Physical check", "SRO records", "Status updates"] },
  { icon: "▤", title: "Drafting & vetting", text: "Coordinate sale agreement, sale deed and buyer-protective clauses with the responsible advocate, based on the transaction.", tags: ["Sale Agreement", "Sale Deed", "POA"] },
  { icon: "◎", title: "Plain-English verdict", text: "Understand the decision, material risks, unresolved evidence and conditions to address before proceeding. Report format depends on the package.", tags: ["Risk summary", "Evidence", "Next steps"] },
  { icon: "⌂", title: "Post-purchase care", text: "Support the next steps after registration, including Khata transfer, property-tax name change and BESCOM name transfer where applicable.", tags: ["Khata", "Property tax", "BESCOM"] },
  { icon: "✎", title: "Property deed services", text: "Assistance with POA, Gift Deed, Will registration and other property-related deeds, subject to professional review.", tags: ["POA", "Gift Deed", "Will"] },
  { icon: "▣", title: "Khata & tax services", text: "Assistance with applicable A Khata, B Khata, BDA Khata, e-Khata / e-Swathu, BBMP e-Aasthi and property-tax processes.", tags: ["Khata", "Tax records", "BBMP"] },
  { icon: "⇢", title: "Registration coordination", text: "Coordinate readiness checklists, transaction paperwork and SRO appointment steps. Government fees and statutory outcomes remain separate.", tags: ["Checklist", "Appointment", "Follow-up"] },
];

export const FAQS = [
  { q: "Can you tell me whether a property is safe to buy?", a: "The advocate reviews the available evidence and explains material risks, missing information and next steps. No service can guarantee that every possible risk or dispute will be found." },
  { q: "What documents should I ask the seller for?", a: "The checklist depends on the property type and transaction. It may include title deeds, EC, revenue records, approvals, khata/tax records, survey documents and development-rights documents." },
  { q: "Which package do I need?", a: "A specialist can discuss your property type, transaction stage and support needs before you select a package." },
  { q: "How do I track my request?", a: "Every callback request gets a ticket number. Enter it with the phone number or email you used in Track your request, or ask the chat assistant." },
  { q: "Are stamp duty and registration fees included?", a: "No. Stamp duty, registration fees and other government charges are billed separately at actuals." },
  { q: "Do updates mean the government portal is live-connected?", a: "No. Status updates reflect the case team's recorded progress and confirmed source checks. The site should not imply a live government-data connection unless one has actually been implemented." },
];

export const DOC_SERVICES = [
  { icon: "▤", title: "Land & revenue records", text: "RTC / Pahani, Mutation Register extracts, mutation orders and eligible survey records.", slug: "rtc-mutation-survey-records" },
  { icon: "⌕", title: "Registration documents", text: "Encumbrance Certificate, registered deed copies and eligible certified-copy requests.", slug: "certified-copy-ec" },
  { icon: "⌂", title: "Khata & property records", text: "Khata / e-Khata guidance, property-tax records and application follow-up.", slug: "khata-property-tax-documents" },
  { icon: "⚖", title: "Legal documents & deeds", text: "Sale agreement, sale deed, POA, Gift Deed and other property-document drafting or vetting support.", slug: "deed-drafting-registration" },
  { icon: "✎", title: "Affidavits", text: "Name change, address proof, gap, loss and other affidavits, drafted by an advocate on stamp paper and arranged for notarisation.", slug: "affidavit-drafting" },
];
