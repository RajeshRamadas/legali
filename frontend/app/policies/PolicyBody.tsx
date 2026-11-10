import Markdown from "../Markdown";
import type { PolicyContent } from "./types";

export default function PolicyBody({ content }: { content: PolicyContent }) {
  // Policy reading does not load third-party image beacons. HTML stays escaped by Markdown.
  return <><Markdown className="policy-body" source={content.body.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")} />
    <section className="policy-contact"><h2>Contact details</h2><address>
      <strong>{content.organization}</strong>
      {content.grievance_officer && <p>Accountable contact: {content.grievance_officer}</p>}
      {content.contact_email && <p><a href={`mailto:${encodeURIComponent(content.contact_email).replace("%40", "@")}`}>{content.contact_email}</a></p>}
      {content.contact_phone && <p>{content.contact_phone}</p>}
      {content.postal_address && <p className="policy-address">{content.postal_address}</p>}
    </address></section></>;
}
