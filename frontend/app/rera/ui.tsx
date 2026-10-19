import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient, DEFAULT_API_BASE_URL, type ReraDataInfo, type ReraMarket, type ReraProjectCard, type ReraRiskCount, type ReraRiskLevel, type ReraSupplyYear, type ReraTrackRecord, type ReraUnitMix } from "@homexo/shared";

// RERA pages render on the server, which may reach the API at a different address than browsers do.
export const serverApi = createApiClient(process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);

// Loads a page's data: a 404 from the API becomes the not-found page, an unreachable API returns null.
export async function loadOr404<T>(load: () => Promise<T>): Promise<T | null> {
  try {
    return await load();
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("We couldn't find")) notFound();
    return null;
  }
}

const num = new Intl.NumberFormat("en-IN");
export const n = (value: number | null | undefined) => (value === null || value === undefined ? "–" : num.format(value));
export const pct = (value: number | null | undefined) => (value === null || value === undefined ? "–" : `${value}%`);
export const rupees = (value: number | null | undefined) => (value ? `₹${num.format(value)}` : "–");
const monthYear = new Intl.DateTimeFormat("en-IN", { month: "short", year: "numeric" });
const longDate = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const month = (iso: string | null) => (iso ? monthYear.format(new Date(iso)) : "–");
export const day = (iso: string | null) => (iso ? longDate.format(new Date(iso)) : "–");

const RISK_ICON: Record<ReraRiskLevel, string> = { green: "✓", amber: "!", red: "✕" };

export function RiskBadge({ level, label }: { level: ReraRiskLevel; label: string }) {
  return <span className={`rr-risk ${level}`}><i aria-hidden>{RISK_ICON[level]}</i>{label}</span>;
}

export function SampleNotice({ data }: { data: ReraDataInfo }) {
  if (data.sample) {
    return (
      <div className="rr-sample" role="note">
        <b>Sample data.</b> These projects and developers are made up to show how the pages work. Real Karnataka RERA records will replace them.
      </div>
    );
  }
  return null;
}

export function ProjectCard({ project }: { project: ReraProjectCard }) {
  const done = project.status === "completed";
  return (
    <article className={`rr-card ${project.risk.level}`}>
      <div className="rr-card-top">
        <div>
          <h3><Link href={`/rera/projects/${project.slug}`}>{project.name}</Link></h3>
          <p>
            by <Link href={`/rera/developers/${project.promoter.slug}`}>{project.promoter.name}</Link> ·{" "}
            <Link href={`/rera/localities/${project.locality.slug}`}>{project.locality.name}</Link>
          </p>
        </div>
        <RiskBadge level={project.risk.level} label={project.risk.label} />
      </div>
      <ul className="rr-facts">
        <li><small>Status</small>{project.status_label}</li>
        <li><small>{done ? "Completed" : "Due"}</small>{month(done ? project.completed_on : project.deadline)}</li>
        <li><small>Units</small>{n(project.total_units)}</li>
        <li><small>Booked</small>{pct(project.booked_pct)}</li>
        <li><small>₹ / sq ft</small>{rupees(project.price_per_sqft)}</li>
      </ul>
      {project.risk.headline && <p className="rr-card-flag">{project.risk.headline}</p>}
      <small className="rr-reg">{project.registration_no} · {project.type_label}</small>
    </article>
  );
}

export function Stat({ value, label, note }: { value: string; label: string; note?: string }) {
  return <div className="rr-stat"><b>{value}</b><span>{label}</span>{note && <small>{note}</small>}</div>;
}

export function MarketStats({ market, delivery }: { market: ReraMarket; delivery?: ReraTrackRecord }) {
  return (
    <div className="rr-stats">
      <Stat value={n(market.projects)} label="RERA projects" note={`${n(market.ongoing)} under construction`} />
      <Stat value={n(market.units)} label="Units registered" note={`${pct(market.booked_pct)} booked`} />
      <Stat value={rupees(market.median_price_per_sqft)} label="Median price / sq ft" note={market.price_range ? `${rupees(market.price_range[0])} to ${rupees(market.price_range[1])}` : undefined} />
      <Stat value={pct(market.late_pct)} label="Under construction and late" note="past the date first promised" />
      {delivery && <Stat value={pct(delivery.on_time_pct)} label="Completed on time" note={`of ${n(delivery.completed)} completed projects`} />}
    </div>
  );
}

// One-series column chart: units due to complete each year. Each column shows its value on hover and in its label.
export function SupplyChart({ years }: { years: ReraSupplyYear[] }) {
  const max = Math.max(1, ...years.map((y) => y.units));
  return (
    <figure className="rr-chart">
      <div className="rr-columns" role="img" aria-label={years.map((y) => `${y.label}: ${y.units} units in ${y.projects} projects`).join("; ")}>
        {years.map((y) => (
          <div key={y.label} className={`rr-col${y.label === "Overdue" ? " overdue" : ""}`} title={`${y.label}: ${n(y.units)} units in ${y.projects} project${y.projects === 1 ? "" : "s"}`}>
            <span className="rr-col-value">{y.units ? n(y.units) : ""}</span>
            <span className="rr-col-bar" style={{ height: `calc(${Math.max(y.units ? 0.02 : 0, y.units / max)} * (100% - 18px))` }} />
            <span className="rr-col-label">{y.label}</span>
          </div>
        ))}
      </div>
      <figcaption>Units in projects under construction, by the year they’re due. Overdue means past the current deadline.</figcaption>
    </figure>
  );
}

export function RiskBar({ risk }: { risk: ReraRiskCount[] }) {
  const total = risk.reduce((sum, r) => sum + r.projects, 0) || 1;
  return (
    <div className="rr-riskbar-wrap">
      <div className="rr-riskbar" role="img" aria-label={risk.map((r) => `${r.label}: ${r.projects}`).join("; ")}>
        {risk.filter((r) => r.projects).map((r) => <span key={r.level} className={r.level} style={{ width: `${(r.projects / total) * 100}%` }} title={`${r.label}: ${r.projects} projects`} />)}
      </div>
      <ul className="rr-legend">
        {risk.map((r) => <li key={r.level}><RiskBadge level={r.level} label={r.label} /> <b>{r.projects}</b> <small>({Math.round((r.projects / total) * 100)}%)</small></li>)}
      </ul>
    </div>
  );
}

export function UnitMix({ mix }: { mix: ReraUnitMix }) {
  const max = Math.max(1, ...mix.map((m) => m.units));
  if (!mix.length) return <p className="rr-muted">No unit breakdown on record.</p>;
  return (
    <ul className="rr-hbars">
      {mix.map((m) => (
        <li key={m.type} title={`${m.type}: ${n(m.units)} units`}>
          <span>{m.type}</span>
          <span className="rr-hbar"><i style={{ width: `${(m.units / max) * 100}%` }} /></span>
          <b>{n(m.units)}</b>
        </li>
      ))}
    </ul>
  );
}

export function Meter({ value, label }: { value: number | null; label: string }) {
  return (
    <div className="rr-meter" title={`${label}: ${pct(value)}`}>
      <div className="rr-meter-head"><span>{label}</span><b>{pct(value)}</b></div>
      <div className="rr-meter-track"><i style={{ width: `${value ?? 0}%` }} /></div>
    </div>
  );
}

export function Verdict({ record }: { record: Pick<ReraTrackRecord, "verdict" | "verdict_label"> }) {
  return <span className={`rr-verdict ${record.verdict}`}>{record.verdict_label}</span>;
}

export function Unavailable() {
  return <section className="wrap rr-section"><p className="rr-empty">RERA data can’t be loaded right now. Please try again shortly.</p></section>;
}

export function GetHelp() {
  return (
    <aside className="rr-help">
      <div>
        <b>Found a warning sign, or about to pay a booking amount?</b>
        <p>Our advocates check the title, approvals and RERA record of the exact unit before you commit, and can help with RERA complaints.</p>
      </div>
      <div className="rr-help-actions">
        <Link className="btn gold small" href="/#packages">See verification packages</Link>
        <Link className="btn light small" href="/lawyers?specialisation=Property%20%26%20real%20estate">Talk to a property lawyer</Link>
      </div>
    </aside>
  );
}
