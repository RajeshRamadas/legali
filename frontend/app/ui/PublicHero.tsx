import Image from "next/image";
import Link from "next/link";
import ServiceButton from "../ServiceButton";
import Icon from "./Icon";
import SampleReportButton from "./SampleReportButton";

export default function PublicHero() {
  return (
    <section className="hp-hero" aria-labelledby="home-title">
      <div className="hp-container hp-hero-grid">
        <div className="hp-hero-copy">
          <p className="hp-eyebrow">
            <span /> Property due diligence · Karnataka
          </p>
          <h1 id="home-title">
            Know your property.
            <br />
            <em>Before you buy.</em>
          </h1>
          <p className="hp-hero-description">
            A clear review of your property documents, the risks that matter,
            and the next steps — reviewed by an advocate.
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
              Start property review <Icon name="send" size={19} />
            </ServiceButton>
            <SampleReportButton />
          </div>
          <ul className="hp-assurances">
            <li>
              <span>
                <Icon name="file" size={19} />
              </span>
              Clear document
              <br />
              checklist
            </li>
            <li>
              <span>
                <Icon name="search" size={19} />
              </span>
              Evidence-linked
              <br />
              findings
            </li>
            <li>
              <span>
                <Icon name="law" size={19} />
              </span>
              Advocate-reviewed
              <br />
              opinion
            </li>
          </ul>
        </div>
        <div className="hp-hero-visual">
          <div className="hp-architecture" aria-hidden="true">
            <Image
              src="/images/property-architecture.webp"
              alt=""
              fill
              priority
              sizes="(max-width: 760px) 100vw, 45vw"
            />
          </div>
          <div className="hp-paper hp-paper-back" aria-hidden="true">
            <span>PROPERTY RECORDS</span>
            <i />
            <i />
            <i />
            <i />
          </div>
          <div className="hp-paper hp-paper-front" aria-hidden="true">
            <span>SALE DEED</span>
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
          <aside
            className="hp-review"
            aria-label="Illustrative property review"
          >
            <div className="hp-review-heading">
              <h2>Property review</h2>
              <span className="hp-sample-label">Illustrative sample</span>
            </div>
            <div className="hp-review-row">
              <span className="hp-status-icon received">
                <Icon name="check" size={17} />
              </span>
              <div>
                <strong>Sale deed</strong>
                <small>Received</small>
              </div>
              <Icon name="chev" size={15} />
            </div>
            <div className="hp-review-row">
              <span className="hp-status-icon reviewing">
                <Icon name="search" size={17} />
              </span>
              <div>
                <strong>Title chain</strong>
                <small>Under review</small>
              </div>
              <Icon name="chev" size={15} />
            </div>
            <div className="hp-review-row">
              <span className="hp-status-icon requested">
                <Icon name="file" size={17} />
              </span>
              <div>
                <strong>Encumbrance certificate</strong>
                <small>Requested</small>
              </div>
              <Icon name="chev" size={15} />
            </div>
            <div className="hp-review-notice">
              <Icon name="alert" size={18} />
              <div>
                <strong>Documents needed</strong>
                <p>
                  Please share the remaining records to continue the review.
                </p>
              </div>
            </div>
          </aside>
          <div className="hp-next-step">
            <span className="hp-next-icon">
              <Icon name="upload" size={25} />
            </span>
            <div>
              <span className="hp-sample-label">Illustrative sample</span>
              <small>Your next step</small>
              <strong>Upload your sale deed</strong>
            </div>
          </div>
        </div>
      </div>
      <div className="hp-container hp-returning">
        <span>Already have a case?</span>
        <Link href="/documents">
          Upload documents <Icon name="chev" size={14} />
        </Link>
        <Link href="#track">
          Track your request <Icon name="chev" size={14} />
        </Link>
      </div>
    </section>
  );
}
