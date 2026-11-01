import Icon from "./Icon";

const steps = [
  {
    title: "Share your property details",
    text: "Tell us about the property, its location and the transaction you are planning.",
    kind: "intake",
  },
  {
    title: "Upload the documents we request",
    text: "Get a checklist tailored to your property. Share what you have and see what is still needed.",
    kind: "documents",
  },
  {
    title: "Get a reasoned review",
    text: "Understand the findings, open questions and next steps in an advocate-reviewed report.",
    kind: "report",
  },
];
export default function HomeSteps() {
  return (
    <section
      className="hp-workflow"
      id="how-it-works"
      aria-labelledby="workflow-title"
    >
      <div className="hp-container">
        <div className="hp-section-heading">
          <div>
            <p className="hp-eyebrow">A clear path forward</p>
            <h2 id="workflow-title">Clarity at every step.</h2>
          </div>
          <p>
            From your first document to your final decision,
            <br className="hp-desktop-break" /> know where things stand.
          </p>
        </div>
        <ol className="hp-workflow-grid">
          {steps.map((step, index) => (
            <li key={step.kind}>
              <div className="hp-step-title">
                <span>{index + 1}</span>
                <h3>{step.title}</h3>
              </div>
              <p>{step.text}</p>
              <div
                className={`hp-step-illustration ${step.kind}`}
                aria-hidden="true"
              >
                {step.kind === "intake" ? (
                  <>
                    <div>
                      <b>Property details</b>
                      <i />
                      <i className="short" />
                      <i />
                    </div>
                    <span className="hp-mini-pin">
                      <Icon name="home" size={25} />
                    </span>
                  </>
                ) : step.kind === "documents" ? (
                  <>
                    <div>
                      <Icon name="file" size={22} />
                      <b>Sale deed</b>
                      <i />
                      <i />
                    </div>
                    <div>
                      <Icon name="file" size={22} />
                      <b>Title records</b>
                      <i />
                      <i />
                    </div>
                    <div>
                      <Icon name="file" size={22} />
                      <b>EC</b>
                      <i />
                      <i />
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <b>Property review report</b>
                      <i />
                      <i className="short" />
                      <i />
                    </div>
                    <div className="hp-mini-findings">
                      <span>
                        <Icon name="check" size={12} />
                        <i />
                      </span>
                      <span>
                        <Icon name="alert" size={12} />
                        <i />
                      </span>
                      <span>
                        <Icon name="search" size={12} />
                        <i />
                      </span>
                    </div>
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
