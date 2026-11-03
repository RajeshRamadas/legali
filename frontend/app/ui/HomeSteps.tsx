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
              <span className="hp-step-number">0{index + 1}</span>
              <div className="hp-step-title">
                <span>
                  <Icon
                    name={index === 0 ? "home" : index === 1 ? "upload" : "search"}
                    size={24}
                  />
                </span>
                <h3>{step.title}</h3>
              </div>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
