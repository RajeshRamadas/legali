import Link from "next/link";
import AssistantPanel from "../ui/AssistantPanel";
import { Card, ListRow, PageHeader } from "../ui/primitives";
import Icon from "../ui/Icon";
export default function AssistantPage() {
  return (
    <main className="hx-assistant-page">
      <PageHeader
        eyebrow="Homexo Legal"
        title="A little clarity goes a long way"
        subtitle="Ask a question. Understand your next step."
      />
      <div className="hx-assistant-grid">
        <AssistantPanel />
        <aside className="hx-dashboard-rail">
          <Card title="Quick actions" icon="spark">
            {[
              [
                "/rera",
                "Check a RERA project",
                "Warning signs and registration records",
                "rera",
              ],
              [
                "/documents",
                "Explain a document",
                "Share papers with your case team",
                "file",
              ],
              [
                "/?service=affidavit-drafting#callback",
                "Draft an affidavit",
                "Reviewed by an advocate",
                "pen",
              ],
              [
                "/lawyers",
                "Talk to a lawyer",
                "Find a consultation slot",
                "law",
              ],
            ].map(([href, title, meta, icon]) => (
              <Link href={href} key={href}>
                <ListRow
                  leading={<Icon name={icon as "rera"} />}
                  title={title}
                  meta={meta}
                  trailing={<Icon name="chev" />}
                />
              </Link>
            ))}
          </Card>
          <Card title="Tips">
            <ul>
              <li>Mention the location and property type.</li>
              <li>Use the exact RERA number when available.</li>
              <li>Verify your ticket to ask about your case.</li>
              <li>
                Independent checks and an advocate’s opinion remain necessary.
              </li>
            </ul>
          </Card>
        </aside>
      </div>
    </main>
  );
}
