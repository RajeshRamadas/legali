import Link from "next/link";
import { createApiClient, DEFAULT_API_BASE_URL, formatFee, type LawyerCard, type PostSummary, type ReraProjectCard, type ReraSummary } from "@homexo/shared";
import CallbackSection from "./CallbackSection";
import Faq from "./Faq";
import PublicHero from "./ui/PublicHero";
import ServiceButton, { AskButton } from "./ServiceButton";
import { PACKAGES } from "./content";
import { ProjectCard, RiskBar, SampleNotice, n, pct, rupees } from "./rera/ui";
import "./ui/views/rera-rera.css";
import "./ui/views/home.css";

export const revalidate = 300;

const serverApi = createApiClient(process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);

// Each block of live data is optional: when the API can't be reached the page still renders, without that block.
async function load() {
  const [rera, flagged, lawyers, posts] = await Promise.all([
    serverApi.reraSummary().catch(() => null) as Promise<ReraSummary | null>,
    serverApi.searchReraProjects({ risk: "red", sort: "risk", page_size: 1 }).then((r) => r.items[0] ?? null).catch(() => null) as Promise<ReraProjectCard | null>,
    serverApi.searchLawyers({ sort: "soonest" }).then((r) => r.items.slice(0, 3)).catch(() => []) as Promise<LawyerCard[]>,
    serverApi.listPosts({ pageSize: 3 }).then((r) => r.items).catch(() => []) as Promise<PostSummary[]>,
  ]);
  return { rera, flagged, lawyers, posts };
}

const STEPS = [
  { title: "Tell us what you need", badge: "2 minutes", text: "Ask the assistant in plain words, or pick a service. It explains your options and points you to the right lawyer or package." },
  { title: "Book a time and pay", badge: "One tap", text: "Pick a verified advocate and a slot that suits you, and pay the fixed fee online. You get a request number straight away." },
  { title: "Meet, track, receive", badge: "From home", text: "Join your call on Google Meet, follow each stage as the team updates it, and share papers and download your signed report from your case documents." },
];

const ICONS = {
  rera: <path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></>,
  chat: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />,
  shield: <><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" /></>,
  pen: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></>,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>,
  pulse: <path d="M3 12h4l3 8 4-16 3 8h4" />,
  card: <><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M7 15h4" /></>,
  video: <><rect x="3" y="6" width="13" height="12" rx="2" /><path d="M16 10l5-3v10l-5-3" /></>,
  check: <path d="M5 12l5 5L20 7" />,
  folder: <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />,
};

function Icon({ name, size = 20 }: { name: keyof typeof ICONS; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>;
}

const TILES: { icon: keyof typeof ICONS; title: string; text: string; href: string; cta: string; ask?: boolean }[] = [
  { icon: "rera", title: "Check a RERA project", text: "A free warning-sign check on any registered project and its developer.", href: "/rera", cta: "Check a project" },
  { icon: "search", title: "Find a lawyer", text: "Compare advocates by speciality, language, fee and next free slot.", href: "/lawyers", cta: "Browse lawyers" },
  { icon: "shield", title: "Verify a property", text: "Title, EC, RERA and approvals checked, ending in a plain-English verdict.", href: "#packages", cta: "See packages" },
  { icon: "pen", title: "Make an affidavit", text: "Name change, address proof, gap or loss affidavits, drafted by an advocate and ready to sign.", href: "/?service=affidavit-drafting#callback", cta: "Start an affidavit" },
  { icon: "file", title: "Get a document", text: "EC, RTC, certified copies, deeds and POA, with courier delivery where available.", href: "/services#documents", cta: "Request a document" },
  { icon: "folder", title: "Your case documents", text: "Upload and tag papers for your lawyer, see what the report still needs, and download the signed final report.", href: "/documents", cta: "Open your documents" },
  { icon: "chat", title: "Ask the assistant", text: "Plain-English answers any time, with a hand-off to a person when you need one.", href: "", cta: "Start a chat", ask: true },
  { icon: "card", title: "Pay online", text: "UPI, cards or netbanking when you book a consultation. Government fees stay at actuals.", href: "/lawyers", cta: "Book and pay" },
  { icon: "pulse", title: "Track your request", text: "Enter your request number and phone to see the latest stage and reply to the team.", href: "#track", cta: "Track now" },
];

export default async function HomePage() {
  const { rera, flagged, lawyers, posts } = await load();

  return (
    <>

      <main id="home" className="hx">
        <PublicHero lawyer={lawyers[0]} flagged={flagged} sample={rera?.data.sample}/>




        <section className="section hx-tiles-section" id="services">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Everything in one place</div><h2 className="heading">Start anywhere.<br />It all connects.</h2></div><p>Every request gets one number, so a chat, a booking, a payment and a document all end up on the same case.</p></div>
            <div className="hx-tiles">
              {TILES.map((tile) => {
                const body = <><span className="hx-icon"><Icon name={tile.icon} /></span><b>{tile.title}</b><p>{tile.text}</p><span className="hx-tile-cta">{tile.cta} →</span></>;
                return tile.ask
                  ? <AskButton className="hx-tile" key={tile.title}>{body}</AskButton>
                  : <Link className="hx-tile" href={tile.href} key={tile.title}>{body}</Link>;
              })}
            </div>
          </div>
        </section>

        <section className="section hx-rera rr" id="rera">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">Free RERA project check · Karnataka</div><h2 className="heading">Check a project<br />before you pay a rupee.</h2></div><p>See whether a registration is valid, how late a project is against the date first promised, how much has sold, and how its developer has delivered before.</p></div>
            <form className="rr-search" action="/rera" role="search">
              <input name="q" placeholder="Project name, RERA number, developer, locality or PIN code" aria-label="Search RERA projects" />
              <button className="btn">Check project</button>
            </form>
            {rera ? (
              <>
                <div style={{ marginTop: 14 }}><SampleNotice data={rera.data} /></div>
                <div className="hx-rera-grid">
                  {flagged && (
                    <div className="hx-rera-example">
                      <div className="tiny-label">A project our check flagged</div>
                      <ProjectCard project={flagged} />
                      <div className="hx-rera-help"><b>Found a warning sign?</b><span><Link className="btn small" href="/lawyers?q=RERA">Talk to a property lawyer</Link><Link className="btn small light" href="#packages">Verify the unit</Link></span></div>
                    </div>
                  )}
                  <div className="hx-panel hx-rera-market">
                    <div className="hx-rera-market-head"><h3>What the RERA register says</h3><small>Figures as of {new Date(rera.as_of).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</small></div>
                    <div className="hx-mini-stats">
                      <div><b className="heading">{n(rera.market.projects)}</b><span>RERA projects</span></div>
                      <div><b className="heading">{rupees(rera.market.median_price_per_sqft)}</b><span>Median / sq ft</span></div>
                      <div><b className="heading">{pct(rera.market.late_pct)}</b><span>Running late</span></div>
                      <div><b className="heading">{pct(rera.delivery.on_time_pct)}</b><span>Delivered on time</span></div>
                    </div>
                    <h4>Warning signs across all projects</h4>
                    <RiskBar risk={rera.risk} />
                    <table className="hx-loc">
                      <thead><tr><th scope="col">Locality</th><th scope="col">Booked</th><th scope="col">₹ / sq ft</th><th scope="col">Late</th></tr></thead>
                      <tbody>
                        {rera.localities.slice(0, 4).map((loc) => (
                          <tr key={loc.slug}><td><Link href={`/rera/localities/${loc.slug}`}>{loc.name}</Link></td><td>{pct(loc.booked_pct)}</td><td>{rupees(loc.median_price_per_sqft)}</td><td>{pct(loc.late_pct)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                    <Link className="hx-more" href="/rera">See the full market report →</Link>
                  </div>
                </div>
              </>
            ) : (
              <p className="hx-quiet"><Link href="/rera">Open the RERA project check →</Link></p>
            )}
          </div>
        </section>

        <section className="section hx-steps" id="how-it-works">
          <div className="wrap">
            <div className="section-head"><div><div className="eyebrow">How it works</div><h2 className="heading">Three steps.<br />No office visits.</h2></div><p>Whatever you need, the path is the same: tell us, book and pay, then follow along until it is done.</p></div>
            <div className="hx-steps-grid">
              {STEPS.map((step, i) => (
                <article className="hx-step" key={step.title}>
                  <div className="hx-step-top"><span className="heading">{i + 1}</span><span className="hx-pill">{step.badge}</span></div>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                  {i === 0 && <div className="hx-demo"><span className="me">Do I need an EC before buying a resale flat?</span><span className="bot">Yes. An EC shows loans or claims on the property. Shield Starter covers it.</span></div>}
                  {i === 1 && <div className="hx-demo"><div className="hx-slots"><span>12:30 pm</span><span className="on">4:00 pm</span><span>6:00 pm</span></div><div className="hx-pay"><b>Pay the fee securely</b><span className="hx-pill gold">UPI · Card</span></div></div>}
                  {i === 2 && <div className="hx-demo"><div className="hx-progress" aria-hidden="true"><i className="on" /><i className="on" /><i className="on" /><i /></div><b>Stage 3 of 4 · Lawyer review</b><small>WhatsApp: “Your report is in lawyer review.”</small></div>}
                </article>
              ))}
            </div>
          </div>
        </section>



        {(
          <section className="section hx-lawyers" id="lawyers">
            <div className="wrap">
              <div className="section-head"><div><div className="eyebrow">Book a video consultation</div><h2 className="heading">Talk to a verified advocate.</h2></div><Link className="btn light" href="/lawyers">See all lawyers →</Link></div>
              <div className="hx-lawyer-grid">{lawyers.length===0&&<p>Find an advocate for your property. <Link className="hx-text-link" href="/lawyers">Browse lawyers and available times</Link>.</p>}
                {lawyers.map((lawyer) => (
                  <article className="hx-lawyer" key={lawyer.slug}>
                    <div className="hx-lawyer-top"><span className="hx-avatar">{lawyer.initials}</span><div><h3><Link href={`/lawyers/${lawyer.slug}`}>{lawyer.name}</Link></h3><p>{lawyer.headline}</p></div></div>
                    <small>{lawyer.experience_years} years · {lawyer.locality ? `${lawyer.locality}, ` : ""}{lawyer.city} · {lawyer.languages.join(", ")}</small>
                    <div className="hx-lawyer-foot">
                      <div><b className="heading">{formatFee(lawyer.consultation_fee)}</b>{lawyer.next_available ? <span>Next: {lawyer.next_available.day}, {lawyer.next_available.label}</span> : <span className="none">No open slots soon</span>}</div>
                      <Link className="btn small" href={`/lawyers/${lawyer.slug}`}>Book</Link>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </section>
        )}

        <section className="section hx-packages" id="packages">
          <div className="wrap hx-split">
            <div>
              <div className="eyebrow">Buying a property?</div>
              <h2 className="heading">One flat fee.<br />Clear scope.</h2>
              <p>Each package ends in a plain-English Go / Investigate / Do Not Proceed verdict. Stamp duty, registration fees and government charges are billed at actuals.</p>
              <Link className="hx-more" href="/services">See everything we verify →</Link>
            </div>
            <div className="hx-package-list">
              {PACKAGES.map((pkg) => (
                <div className={`hx-package${pkg.popular ? " popular" : ""}`} key={pkg.name}>
                  <div className="hx-package-name"><b>{pkg.name}</b>{pkg.popular && <span className="hx-pill gold">Most chosen</span>}<small>{pkg.summary}</small></div>
                  <div className="hx-package-price"><b className="heading">{pkg.price}</b><small>{pkg.delivery.replace(/^Delivery in /, "")}</small></div>
                  <ServiceButton className={`btn small${pkg.popular ? "" : " light"}`} request={{ slug: pkg.slug, pkg: pkg.name, message: `${pkg.name} selected. Request a callback so we can confirm scope, documents and payment.` }}>Choose</ServiceButton>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="hx-dev" id="developers">
          <div className="wrap">
            <div className="hx-dev-band">
              <div><div className="eyebrow">For real estate developers</div><h2 className="heading">From land acquisition to registered ownership.</h2><p>Land screening, acquisition due diligence, bulk registration and mutation follow-up, each tracked in one workflow.</p></div>
              <Link className="btn gold" href="/developers">Explore developer services ↗</Link>
            </div>
          </div>
        </section>

        <CallbackSection />

        {(
          <section className="section hx-posts" id="insights">
            <div className="wrap">
              <div className="section-head"><div><div className="eyebrow">Insights</div><h2 className="heading">Know before you sign.</h2></div><Link className="btn light" href="/blog">All articles →</Link></div>
              <div className="hx-post-grid">{posts.length===0&&<p>Explore property guides and case studies in <Link href="/blog">Insights</Link>.</p>}
                {posts.map((post) => (
                  <Link className="hx-post" href={`/blog/${post.slug}`} key={post.slug}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {post.cover_image_url ? <img src={post.cover_image_url} alt="" /> : <span className={`hx-post-cover ${post.post_type}`} />}
                    <div><span className="eyebrow">{post.type_label}</span><b>{post.title}</b><small>{post.reading_minutes} min read</small></div>
                  </Link>
                ))}
              </div>
            </div>
          </section>
        )}

        <section className="section faq" id="faq">
          <div className="wrap faq-grid">
            <div>
              <div className="eyebrow">FAQs</div>
              <h2 className="heading hx-tone-b0e08465" style={{ fontSize: 42, margin: "10px 0 14px" }}>Questions before you begin?</h2>
              <p className="hx-tone-ae860f94" style={{ fontSize: 12, lineHeight: 1.7 }}>Ask the assistant any time, or request a callback if you are unsure which service fits.</p>
              <a className="btn" href="#callback">Ask a specialist →</a>
            </div>
            <Faq />
          </div>
        </section>

        <section className="final-cta">
          <div className="wrap">
            <div><div className="eyebrow hx-tone-63647bec" >Not sure where to start?</div><h2>Check first. Decide with confidence.</h2><p>Ask a question, book a lawyer or leave your number and we will call you back.</p></div>
            <a className="btn gold" href="#callback">Get a free callback ↗</a>
          </div>
        </section>
      </main>


    </>
  );
}
