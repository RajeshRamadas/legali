"use client";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import Icon, { type IconName } from "./Icon";

const stages: {
  label: string;
  icon: IconName;
  title: string;
  subtitle: string;
  filename: string;
  status: string;
  heading: string;
  detail: string;
  rows: { label: string; value: string; tone?: string }[];
  note: string;
}[] = [
  {
    label: "Documents",
    icon: "file",
    title: "Every paper. In its place.",
    subtitle: "A checklist shaped around your property.",
    filename: "Sale deed.pdf",
    status: "Received",
    heading: "Know what’s missing",
    detail:
      "The sale deed is available. The earlier title record and current EC are still needed.",
    rows: [
      { label: "Sale deed", value: "Received", tone: "green" },
      { label: "Earlier title deed", value: "Requested", tone: "amber" },
      { label: "Encumbrance certificate", value: "Requested", tone: "amber" },
    ],
    note: "Your checklist adapts to the property and transaction.",
  },
  {
    label: "Title chain",
    icon: "case",
    title: "Follow the ownership story.",
    subtitle: "Understand each transfer and the gaps between them.",
    filename: "Ownership chain",
    status: "Under review",
    heading: "A gap worth investigating",
    detail:
      "A prior transfer is mentioned in the sale deed, but its supporting document has not been shared.",
    rows: [
      { label: "Earlier ownership", value: "Document needed", tone: "amber" },
      { label: "Recorded seller", value: "Deed available", tone: "green" },
      { label: "Proposed purchase", value: "Review pending" },
    ],
    note: "A title-chain gap stays open until the evidence is reviewed.",
  },
  {
    label: "Cross-checks",
    icon: "search",
    title: "Spot the details that differ.",
    subtitle: "Compare the same property across different records.",
    filename: "Document comparison",
    status: "Question raised",
    heading: "Different survey numbers",
    detail:
      "In this example, the sale deed and tax record describe different survey numbers. The discrepancy needs clarification.",
    rows: [
      { label: "Sale deed · survey number", value: "48/2" },
      { label: "Tax record · survey number", value: "48/3", tone: "amber" },
      { label: "Next action", value: "Reconcile records", tone: "amber" },
    ],
    note: "A mismatch is a question to resolve, not an automatic legal conclusion.",
  },
  {
    label: "Legal context",
    icon: "law",
    title: "Put the evidence in context.",
    subtitle: "Applicable law belongs alongside the facts.",
    filename: "Legal review notes",
    status: "Advocate review",
    heading: "Relevant law, explained",
    detail:
      "The advocate considers transfer and registration requirements against the actual property records and transaction.",
    rows: [
      {
        label: "Transfer of Property Act, 1882",
        value: "Sale & seller obligations",
      },
      { label: "Registration Act, 1908", value: "Registration requirements" },
      {
        label: "Applicability & current position",
        value: "To be confirmed",
        tone: "amber",
      },
    ],
    note: "These are illustrative references; applicability requires current-law review.",
  },
  {
    label: "Advocate review",
    icon: "shield",
    title: "A reasoned next step.",
    subtitle: "Findings, limitations and advice in one report.",
    filename: "Property review report",
    status: "Not yet issued",
    heading: "Evidence before an opinion",
    detail:
      "The missing records and open discrepancies must be addressed before the advocate can assess the title and issue an opinion.",
    rows: [
      {
        label: "Open document requests",
        value: "2 outstanding",
        tone: "amber",
      },
      { label: "Record discrepancy", value: "Unresolved", tone: "amber" },
      { label: "Final legal opinion", value: "Pending advocate review" },
    ],
    note: "No purchase recommendation is implied by this fictional example.",
  },
];

export default function PropertyReviewPreview() {
  const [selected, setSelected] = useState(0);
  const id = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const stage = stages[selected];
  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown")
      next = (index + 1) % stages.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = (index + stages.length - 1) % stages.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = stages.length - 1;
    else return;
    event.preventDefault();
    setSelected(next);
    tabs.current[next]?.focus();
  }
  return (
    <div className="lt-product-story">
      <div className="lt-story-heading">
        <span>From paperwork to perspective</span>
        <span>
          <i /> Explore an illustrative case
        </span>
      </div>
      <div
        className="lt-stage-tabs"
        role="tablist"
        aria-label="Explore the property review workflow"
      >
        {stages.map((item, index) => (
          <button
            key={item.label}
            ref={(node) => {
              tabs.current[index] = node;
            }}
            id={`${id}-tab-${index}`}
            aria-controls={`${id}-panel`}
            aria-selected={selected === index}
            tabIndex={selected === index ? 0 : -1}
            role="tab"
            onClick={() => setSelected(index)}
            onKeyDown={(event) => navigate(event, index)}
          >
            <Icon name={item.icon} size={17} />
            <span>{item.label}</span>
            <span className="lt-tab-number">0{index + 1}</span>
          </button>
        ))}
      </div>
      <div className="lt-workspace">
        <div className="lt-workspace-top">
          <div>
            <span className="lt-workspace-logo">
              <Icon name="home" size={17} />
            </span>
            <strong>My property workspace</strong>
            <span className="lt-workspace-slash">/</span>
            <span>Resale apartment</span>
          </div>
          <span className="lt-example-tag">Illustrative sample</span>
        </div>
        <div
          role="tabpanel"
          id={`${id}-panel`}
          aria-labelledby={`${id}-tab-${selected}`}
          tabIndex={0}
          className="lt-workspace-content"
        >
          <aside
            className="lt-workspace-sidebar"
            aria-label="Example case overview"
          >
            <span className="lt-sidebar-eyebrow">YOUR CASE</span>
            <strong>Home, next.</strong>
            <small>Karnataka · Apartment</small>
            <div className="lt-sidebar-item">
              <Icon name="case" size={16} /> Overview
            </div>
            <div className="lt-sidebar-item active">
              <Icon name={stage.icon} size={16} />
              {stage.label}
            </div>
            <div className="lt-sidebar-item">
              <Icon name="chat" size={16} /> Conversations
            </div>
            <div className="lt-sidebar-bottom">
              <span>Next up</span>
              <strong>Share remaining records</strong>
              <small>This is a fictional case.</small>
            </div>
          </aside>
          <div className="lt-case-document">
            <div className="lt-document-overline">
              <span>STEP 0{selected + 1} / 05</span>
              <span>
                <Icon name={stage.icon} size={15} />
                {stage.label}
              </span>
            </div>
            <h2>{stage.title}</h2>
            <p>{stage.subtitle}</p>
            <div className="lt-document-sheet">
              <div className="lt-sheet-title">
                <span>
                  <Icon name={stage.icon} size={22} />
                </span>
                <div>
                  <strong>{stage.filename}</strong>
                  <small>Illustrative property record</small>
                </div>
                <span className="lt-sheet-status">{stage.status}</span>
              </div>
              {selected === 0 ? (
                <div className="lt-paper-excerpt">
                  <span>SALE DEED</span>
                  <i />
                  <i />
                  <i className="short" />
                  <div>
                    <Icon name="search" size={14} /> Earlier ownership document
                    referenced
                  </div>
                  <i />
                  <i className="short" />
                </div>
              ) : (
                <div className="lt-evidence-list">
                  {stage.rows.map((row, index) => (
                    <div key={row.label}>
                      <span className={`lt-evidence-icon ${row.tone || ""}`}>
                        <Icon
                          name={
                            row.tone === "amber"
                              ? "alert"
                              : selected === 1
                                ? "users"
                                : stage.icon
                          }
                          size={17}
                        />
                      </span>
                      <div>
                        <small>
                          {selected === 1
                            ? `Transfer 0${index + 1}`
                            : `Review item 0${index + 1}`}
                        </small>
                        <strong>{row.label}</strong>
                        <span>{row.value}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="lt-document-footer">
                <Icon name="shield" size={14} /> Original records remain
                essential to the review
              </div>
            </div>
          </div>
          <aside className="lt-findings" aria-label="Example finding">
            <div className="lt-finding-label">
              <Icon name="spark" size={16} /> Review insight
            </div>
            <span className="lt-finding-status">
              <i />
              {selected === 3 ? "Legal context" : "Action needed"}
            </span>
            <h3>{stage.heading}</h3>
            <p>{stage.detail}</p>
            <dl>
              {stage.rows.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd className={row.tone || ""}>{row.value}</dd>
                </div>
              ))}
            </dl>
            <div className="lt-finding-note">
              <Icon name="alert" size={14} />
              <p>{stage.note}</p>
            </div>
          </aside>
        </div>
        <div className="lt-workspace-footer">
          <span>
            <Icon name="shield" size={14} /> Evidence first. Advocate reviewed.
          </span>
          <span>Interactive example · not a live case or legal opinion</span>
        </div>
      </div>
      <div className="lt-story-caption">
        <span>One property. One workspace. A clearer next step.</span>
        <a href="#how-it-works">
          See how it works <Icon name="send" size={16} />
        </a>
      </div>
    </div>
  );
}
