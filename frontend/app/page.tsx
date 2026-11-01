import type { Metadata } from "next";
import Link from "next/link";
import {
  createApiClient,
  DEFAULT_API_BASE_URL,
  formatFee,
  type LawyerCard,
  type PostSummary,
  type ReraProjectCard,
  type ReraSummary,
} from "@homexo/shared";
import CallbackSection from "./CallbackSection";
import Faq from "./Faq";
import PublicHero from "./ui/PublicHero";
import HomeSteps from "./ui/HomeSteps";
import Icon, { type IconName } from "./ui/Icon";
import ServiceButton, { AskButton } from "./ServiceButton";
import { PACKAGES } from "./content";
import { ProjectCard, SampleNotice, n, pct } from "./rera/ui";
import "./ui/views/rera-rera.css";
import "./ui/views/home.css";
import "./ui/home-modern.css";

export const revalidate = 300;
export const metadata: Metadata = {
  title: "Homexo Legal — Know your property. Before you buy.",
  description:
    "Property document review in Karnataka. Get a tailored document checklist, evidence-linked findings and an advocate-reviewed opinion, with clear next steps.",
};
const serverApi = createApiClient(
  process.env.API_INTERNAL_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    DEFAULT_API_BASE_URL,
);
async function load() {
  const [rera, flagged, lawyers, posts] = await Promise.all([
    serverApi.reraSummary().catch(() => null) as Promise<ReraSummary | null>,
    serverApi
      .searchReraProjects({ risk: "red", sort: "risk", page_size: 1 })
      .then((r) => r.items[0] ?? null)
      .catch(() => null) as Promise<ReraProjectCard | null>,
    serverApi
      .searchLawyers({ sort: "soonest" })
      .then((r) => r.items.slice(0, 3))
      .catch(() => []) as Promise<LawyerCard[]>,
    serverApi
      .listPosts({ pageSize: 3 })
      .then((r) => r.items)
      .catch(() => []) as Promise<PostSummary[]>,
  ]);
  return { rera, flagged, lawyers, posts };
}
const services: {
  icon: IconName;
  title: string;
  text: string;
  href: string;
  label: string;
}[] = [
  {
    icon: "shield",
    title: "Property verification",
    text: "Understand the title chain, document gaps and risks before you commit.",
    href: "#packages",
    label: "Compare packages",
  },
  {
    icon: "law",
    title: "An advocate, on your side",
    text: "Find a property lawyer by speciality, language, fee and available time.",
    href: "/lawyers",
    label: "Find an advocate",
  },
  {
    icon: "rera",
    title: "A closer look at your project",
    text: "Explore Karnataka RERA project records and potential warning signs.",
    href: "/rera",
    label: "Check a RERA project",
  },
  {
    icon: "file",
    title: "The documents you need",
    text: "Request ECs, RTCs, certified copies and other property records.",
    href: "/services#documents",
    label: "Explore document services",
  },
  {
    icon: "pen",
    title: "Drafted with care",
    text: "Get help with affidavits, sale agreements and registration documents.",
    href: "/?service=affidavit-drafting#callback",
    label: "Request drafting help",
  },
  {
    icon: "case",
    title: "Support for developers",
    text: "Coordinate land due diligence, registration and post-purchase records.",
    href: "/developers",
    label: "Developer services",
  },
];

export default async function HomePage() {
  const { rera, flagged, lawyers, posts } = await load();
  return (
    <main id="home" className="hx hp-home">
      <PublicHero />
      <HomeSteps />

      <section
        className="hp-section"
        id="services"
        aria-labelledby="services-title"
      >
        <div className="hp-container">
          <div className="hp-section-heading">
            <div>
              <p className="hp-eyebrow">Property decisions, made clearer</p>
              <h2 id="services-title">
                The right help.
                <br />
                Right when you need it.
              </h2>
            </div>
            <p>
              Buying, registering or sorting out your records?
              <br className="hp-desktop-break" /> Start with the service that
              fits.
            </p>
          </div>
          <div className="hp-services-grid">
            {services.map((s) => (
              <Link href={s.href} className="hp-service" key={s.title}>
                <span className="hp-service-icon">
                  <Icon name={s.icon} size={24} />
                </span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
                <span className="hp-text-link">
                  {s.label}
                  <Icon name="send" size={17} />
                </span>
              </Link>
            ))}
          </div>
          <div className="hp-assistant-strip">
            <span className="hp-service-icon">
              <Icon name="chat" size={23} />
            </span>
            <div>
              <h3>Have a question before you start?</h3>
              <p>Ask the assistant, or let us connect you with a person.</p>
            </div>
            <AskButton className="hp-button hp-secondary">
              Ask a question <Icon name="send" size={17} />
            </AskButton>
          </div>
        </div>
      </section>

      <section
        className="hp-section hp-rera rr"
        id="rera"
        aria-labelledby="rera-title"
      >
        <div className="hp-container hp-rera-layout">
          <div>
            <p className="hp-eyebrow">Karnataka RERA project check</p>
            <h2 id="rera-title">
              Look beyond
              <br />
              the brochure.
            </h2>
            <p className="hp-section-description">
              Check registration details, completion timelines and a developer’s
              project history. See the questions worth asking before you book.
            </p>
            <form className="hp-project-search" action="/rera" role="search">
              <label htmlFor="home-project-search">Find a project</label>
              <div>
                <Icon name="search" size={20} />
                <input
                  id="home-project-search"
                  name="q"
                  placeholder="Project, developer or RERA number"
                  required
                />
                <button
                  className="hp-button hp-primary"
                  type="submit"
                  aria-label="Search RERA projects"
                >
                  <Icon name="send" size={20} />
                </button>
              </div>
            </form>
            <Link className="hp-text-link" href="/rera">
              Explore the project directory <Icon name="send" size={17} />
            </Link>
            <p className="hp-source-note">
              Published registry data helps you ask better questions. It does
              not establish a property’s title.
            </p>
          </div>
          <div className="hp-rera-preview">
            {rera ? (
              <>
                <SampleNotice data={rera.data} />
                <div className="hp-rera-stats">
                  <div>
                    <strong>{n(rera.market.projects)}</strong>
                    <span>Projects in the dataset</span>
                  </div>
                  <div>
                    <strong>{pct(rera.market.late_pct)}</strong>
                    <span>Past original completion date</span>
                  </div>
                </div>
                {flagged ? (
                  <>
                    <span className="hp-data-label">
                      A project with warning signs
                    </span>
                    <ProjectCard project={flagged} />
                  </>
                ) : (
                  <div className="hp-rera-placeholder">
                    <Icon name="rera" size={42} />
                    <h3>A clearer picture of your project.</h3>
                    <p>
                      Search project records, review completion dates and
                      explore the developer’s history.
                    </p>
                  </div>
                )}
                <p className="hp-source-note">
                  Dataset as of{" "}
                  {new Date(rera.as_of).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                    timeZone: "Asia/Kolkata",
                  })}
                </p>
              </>
            ) : (
              <div className="hp-rera-placeholder">
                <Icon name="rera" size={48} />
                <h3>Your next home deserves a closer look.</h3>
                <p>
                  Search by project name, developer, locality or registration
                  number in the RERA directory.
                </p>
                <Link className="hp-button hp-secondary" href="/rera">
                  Open RERA check <Icon name="send" size={17} />
                </Link>
              </div>
            )}
          </div>
        </div>
      </section>

      <section
        className="hp-section hp-pricing"
        id="packages"
        aria-labelledby="packages-title"
      >
        <div className="hp-container">
          <div className="hp-section-heading">
            <div>
              <p className="hp-eyebrow">Choose your level of support</p>
              <h2 id="packages-title">Clear scope. Fixed fees.</h2>
            </div>
            <p>
              From an initial title review to registration support.
              <br className="hp-desktop-break" /> We confirm the scope before
              work begins.
            </p>
          </div>
          <div className="hp-package-grid">
            {PACKAGES.map((pkg) => (
              <article
                className={`hp-plan${pkg.popular ? " hp-plan-featured" : ""}`}
                key={pkg.name}
              >
                <div className="hp-plan-top">
                  <span className="hp-eyebrow">{pkg.tier}</span>
                  {pkg.popular && (
                    <span className="hp-plan-tag">Extended review</span>
                  )}
                </div>
                <h3>{pkg.name}</h3>
                <p className="hp-plan-summary">{pkg.summary}</p>
                <div className="hp-plan-price">
                  {pkg.price}
                  <small>Fixed package fee</small>
                </div>
                <ServiceButton
                  className={`hp-button ${pkg.popular ? "hp-primary" : "hp-secondary"}`}
                  request={{
                    slug: pkg.slug,
                    pkg: pkg.name,
                    message: `${pkg.name} selected. Share your details so we can confirm scope, documents and payment.`,
                  }}
                >
                  Choose {pkg.name.replace("Shield ", "")}
                  <Icon name="send" size={17} />
                </ServiceButton>
                <ul>
                  {pkg.features
                    .filter((f) => !f.off)
                    .slice(0, 5)
                    .map((f) => (
                      <li key={f.text}>
                        <Icon name="check" size={17} />
                        {f.text}
                      </li>
                    ))}
                </ul>
                <Link className="hp-text-link" href="/services#verify">
                  View full scope <Icon name="chev" size={14} />
                </Link>
                <p className="hp-plan-delivery">{pkg.delivery}</p>
              </article>
            ))}
          </div>
          <p className="hp-pricing-note">
            Delivery estimates depend on complete records and the agreed scope.
            Government fees, stamp duty and registration charges are extra at
            actuals.
          </p>
        </div>
      </section>

      <section
        className="hp-section"
        id="lawyers"
        aria-labelledby="lawyers-title"
      >
        <div className="hp-container">
          <div className="hp-section-heading">
            <div>
              <p className="hp-eyebrow">A conversation makes a difference</p>
              <h2 id="lawyers-title">
                Real questions.
                <br />
                Experienced advocates.
              </h2>
            </div>
            <Link className="hp-button hp-secondary" href="/lawyers">
              Browse advocates <Icon name="send" size={17} />
            </Link>
          </div>
          <div className="hp-lawyer-grid">
            {lawyers.length ? (
              lawyers.map((lawyer) => (
                <article className="hp-lawyer" key={lawyer.slug}>
                  <div className="hp-lawyer-heading">
                    <span className="hp-lawyer-avatar">{lawyer.initials}</span>
                    <div>
                      <h3>
                        <Link href={`/lawyers/${lawyer.slug}`}>
                          {lawyer.name}
                        </Link>
                      </h3>
                      <p>{lawyer.headline}</p>
                    </div>
                  </div>
                  <p>
                    {lawyer.experience_years} years · {lawyer.city}
                  </p>
                  <p className="hp-lawyer-languages">
                    {lawyer.languages.join(" · ")}
                  </p>
                  <div className="hp-lawyer-book">
                    <div>
                      <strong>{formatFee(lawyer.consultation_fee)}</strong>
                      <small>
                        {lawyer.next_available
                          ? `${lawyer.next_available.day} · ${lawyer.next_available.label}`
                          : "View availability"}
                      </small>
                    </div>
                    <Link
                      className="hp-button hp-secondary"
                      href={`/lawyers/${lawyer.slug}`}
                    >
                      Book a call <Icon name="send" size={16} />
                    </Link>
                  </div>
                </article>
              ))
            ) : (
              <div className="hp-empty-lawyers">
                <Icon name="video" size={32} />
                <div>
                  <h3>Find the right person for your property question.</h3>
                  <p>
                    Explore advocates by speciality, language and consultation
                    fee.
                  </p>
                </div>
                <Link className="hp-button hp-secondary" href="/lawyers">
                  Find an advocate <Icon name="send" size={17} />
                </Link>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="hp-container hp-developer-band" id="developers">
        <div>
          <p className="hp-eyebrow">For real estate teams</p>
          <h2>
            From land acquisition
            <br />
            to registered ownership.
          </h2>
          <p>
            Due diligence, registration operations and records follow-up,
            brought into one workflow.
          </p>
        </div>
        <Link className="hp-button hp-secondary" href="/developers">
          Explore developer services <Icon name="send" size={17} />
        </Link>
      </section>

      <CallbackSection />

      <section
        className="hp-section"
        id="insights"
        aria-labelledby="insights-title"
      >
        <div className="hp-container">
          <div className="hp-section-heading">
            <div>
              <p className="hp-eyebrow">The more you know</p>
              <h2 id="insights-title">Read before you sign.</h2>
            </div>
            <Link className="hp-text-link" href="/blog">
              All insights <Icon name="send" size={17} />
            </Link>
          </div>
          <div className="hp-post-grid">
            {posts.length ? (
              posts.map((post) => (
                <Link
                  className="hp-post"
                  href={`/blog/${post.slug}`}
                  key={post.slug}
                >
                  {post.cover_image_url ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={post.cover_image_url} alt="" loading="lazy" />
                    </>
                  ) : (
                    <div className="hp-post-placeholder">
                      <Icon
                        name={post.post_type === "case_study" ? "law" : "file"}
                        size={40}
                      />
                    </div>
                  )}
                  <div>
                    <span className="hp-eyebrow">{post.type_label}</span>
                    <h3>{post.title}</h3>
                    <small>
                      {post.reading_minutes} min read{" "}
                      <Icon name="send" size={16} />
                    </small>
                  </div>
                </Link>
              ))
            ) : (
              <Link className="hp-insights-empty" href="/blog">
                <span className="hp-service-icon">
                  <Icon name="law" size={26} />
                </span>
                <div>
                  <h3>Make sense of property law.</h3>
                  <p>
                    Explore property guides, case studies and practical
                    explainers.
                  </p>
                </div>
                <Icon name="send" size={22} />
              </Link>
            )}
          </div>
        </div>
      </section>

      <section className="hp-section hp-faq" id="faq">
        <div className="hp-container faq-grid">
          <div>
            <p className="hp-eyebrow">Good questions, clear answers</p>
            <h2>
              Before you
              <br />
              take the next step.
            </h2>
            <p>
              Not sure which service fits? Tell us what you are planning and
              we’ll help you get started.
            </p>
            <a className="hp-text-link" href="#callback">
              Ask for a callback <Icon name="send" size={17} />
            </a>
          </div>
          <Faq />
        </div>
      </section>
      <section className="hp-final">
        <div className="hp-container">
          <div>
            <p className="hp-eyebrow">Your next chapter starts with clarity</p>
            <h2>
              A big decision.
              <br />A better-informed you.
            </h2>
            <p>
              Start with your property details. We’ll help you work through the
              rest.
            </p>
          </div>
          <ServiceButton
            className="hp-button"
            request={{
              slug: "title-verification",
              message:
                "Let's start your property review. Tell us about the property below.",
            }}
          >
            Start property review <Icon name="send" size={20} />
          </ServiceButton>
        </div>
      </section>
    </main>
  );
}
