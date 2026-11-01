"use client";
import { useRef } from "react";
import Icon from "./Icon";
import { requestService } from "../homeEvents";

export default function SampleReportButton() {
  const dialog = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button
        type="button"
        className="hp-button hp-secondary"
        onClick={() => dialog.current?.showModal()}
      >
        See a sample report
      </button>
      <dialog
        className="hp-report-dialog"
        ref={dialog}
        aria-labelledby="sample-report-title"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const buttons =
            event.currentTarget.querySelectorAll<HTMLButtonElement>(
              "button:not([disabled])",
            );
          const first = buttons[0],
            last = buttons[buttons.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) dialog.current?.close();
        }}
      >
        <div className="hp-report-content">
          <div className="hp-report-top">
            <span className="hp-sample-label">
              Illustrative sample · not a legal opinion
            </span>
            <form method="dialog">
              <button
                className="hp-report-close"
                aria-label="Close sample report"
                autoFocus
              >
                ×
              </button>
            </form>
          </div>
          <p className="hp-eyebrow">What your review can include</p>
          <h2 id="sample-report-title">
            A finding. The evidence.
            <br />
            Your next step.
          </h2>
          <p>
            This fictional example shows how open questions are explained. Your
            report depends on the property, package and records available.
          </p>
          <div className="hp-report-verdict">
            <Icon name="alert" />
            <div>
              <strong>Further documents required</strong>
              <span>Title cannot be assessed from the sale deed alone.</span>
            </div>
          </div>
          <dl className="hp-report-findings">
            <div>
              <dt>Finding</dt>
              <dd>
                The earlier ownership transfer has not been supported by a
                registered deed.
              </dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>
                Example sale deed, page 2: an earlier transfer is mentioned, but
                the corresponding document is missing.
              </dd>
            </div>
            <div>
              <dt>Next step</dt>
              <dd>
                Request the earlier registered deed and relevant encumbrance
                records. Reconcile the names, dates and property description.
              </dd>
            </div>
            <div>
              <dt>Advocate review</dt>
              <dd>
                The advocate assesses the evidence, applicable law and remaining
                limitations before issuing an opinion.
              </dd>
            </div>
          </dl>
          <p className="hp-report-footnote">
            Official-record searches and advocate review may be needed. This
            example does not confirm ownership or authenticate any document.
          </p>
          <button
            type="button"
            className="hp-button hp-primary"
            onClick={() => {
              dialog.current?.close();
              requestService({
                slug: "title-verification",
                message:
                  "Property review selected. Tell us about your property to get started.",
              });
            }}
          >
            Start my property review <Icon name="send" size={18} />
          </button>
        </div>
      </dialog>
    </>
  );
}
