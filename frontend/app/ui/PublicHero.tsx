import Link from "next/link";
import type { LawyerCard, ReraProjectCard } from "@homexo/shared";
import HomeHero from "../HomeHero";
import Icon from "./Icon";
export default function PublicHero({
  lawyer,
  flagged,
  sample = false,
}: {
  lawyer?: LawyerCard;
  flagged?: ReraProjectCard | null;
  sample?: boolean;
}) {
  return (
    <>
      <section className="hx-new-hero">
        <div className="hx-hero-text">
          <span className="hx-badge violet">
            Bangalore · property law online
          </span>
          <h1>
            Property lawyers,
            <br />
            on <em>demand.</em>
          </h1>
          <p>
            Check a RERA project, book a verified advocate and verify a
            property, all for one fixed fee. Follow every step from your phone.
          </p>
          <div className="hx-hero-buttons">
            <Link href="/lawyers" className="hx-button dark pill">
              Book a lawyer
            </Link>
            <Link href="/rera" className="hx-button pill">
              Check a RERA project
            </Link>
          </div>
          <HomeHero />
        </div>
        <div
          className="hx-hero-collage"
          aria-label="Property legal services overview"
        >
          <div className="hx-portrait one">
            <span />
          </div>
          <div className="hx-portrait two">
            <span />
          </div>
          <Link
            href={lawyer ? `/lawyers/${lawyer.slug}` : "/lawyers"}
            className="hx-floating lawyer"
          >
            <strong>{lawyer?.name ?? "Find your advocate"}</strong>
            <small>
              {lawyer?.headline ?? "Property title and RERA specialists"}
            </small>
            <span className="hx-badge green">
              {lawyer?.next_available
                ? `${lawyer.next_available.day} · ${lawyer.next_available.label}`
                : "Browse available times"}
            </span>
          </Link>
          <Link href="/#packages" className="hx-floating package">
            <strong>Shield Pro</strong>
            <span className="hx-badge violet">₹9,999 fixed</span>
            <small>Property due diligence</small>
          </Link>
          <div className="hx-floating review">
            <span className="hx-approved-mark">
              <Icon name="check" />
            </span>
            <div>
              <strong>Title review · example</strong>
              <small>One case. Every step tracked.</small>
            </div>
          </div>
          <Link href="/rera" className="hx-floating project">
            <strong>{flagged?.name ?? "Check before you book"}</strong>
            <small>{sample ? "Sample RERA data" : "Karnataka RERA"}</small>
            <span className="hx-badge amber">
              {flagged ? "Inspect warning signs" : "Review project records"}
            </span>
          </Link>
        </div>
      </section>
      <div className="hx-trust-strip">
        {[
          ["shield", "Verified advocates"],
          ["rupee", "Fixed fees"],
          ["video", "Google Meet calls"],
          ["chat", "WhatsApp updates"],
          ["card", "UPI & cards"],
          ["rera", "Karnataka RERA data"],
        ].map(([icon, text]) => (
          <span key={text}>
            <Icon name={icon as "shield"} />
            {text}
          </span>
        ))}
      </div>
    </>
  );
}
