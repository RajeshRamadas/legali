import Link from "next/link";
import ServiceButton from "../ServiceButton";
import Icon from "./Icon";
import SampleReportButton from "./SampleReportButton";
import PropertyReviewPreview from "./PropertyReviewPreview";

export default function PublicHero() {
  return (
    <section className="hp-hero" aria-labelledby="home-title">
      <div className="hp-container">
        <div className="hp-hero-copy">
          <p className="hp-hero-label">
            <span>
              <Icon name="spark" size={14} />
            </span>{" "}
            A clearer way to buy property
          </p>
          <h1 id="home-title">
            Big property decisions.
            <br />
            <em>Small print, understood.</em>
          </h1>
          <p className="hp-hero-description">
            Bring your documents, questions and what-ifs. Get a clear path from
            scattered paperwork to an advocate-reviewed property decision.
          </p>
          <div className="hp-actions">
            <ServiceButton
              className="hp-button hp-primary"
              request={{
                slug: "title-verification",
                message:
                  "Let's start your property review. Share a few details so we can confirm the scope and documents.",
              }}
            >
              Start property review <Icon name="send" size={18} />
            </ServiceButton>
            <SampleReportButton />
          </div>
          <p className="hp-hero-footnote">
            A tailored checklist. Evidence-linked findings. A human legal
            opinion.
          </p>
        </div>
        <PropertyReviewPreview />
        <div className="hp-returning">
          <span>Already working with us?</span>
          <Link href="/documents">
            Upload documents <Icon name="send" size={14} />
          </Link>
          <Link href="#track">
            Track your request <Icon name="send" size={14} />
          </Link>
        </div>
      </div>
    </section>
  );
}
