import type { Metadata } from "next";
import Link from "next/link";
import { GetHelp, Meter, ProjectCard, RiskBadge, SampleNotice, Unavailable, UnitMix, Verdict, day, loadOr404, month, n, pct, rupees, serverApi } from "../../ui";

export const revalidate = 300;

type Params = { params: { slug: string } };

const load = (slug: string) => loadOr404(() => serverApi.getReraProject(slug));

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const p = await load(params.slug);
  if (!p) return { title: "RERA project check · Homexo Legal" };
  return {
    title: `${p.name}, ${p.locality.name}: RERA status and warning signs · Homexo Legal`,
    description: `${p.name} by ${p.promoter.name} (RERA ${p.registration_no}): ${p.status_label.toLowerCase()}, due ${month(p.deadline)}, ${pct(p.booked_pct)} of units booked. ${p.risk.label}.`,
  };
}

export default async function ProjectPage({ params }: Params) {
  const p = await load(params.slug);
  if (!p) return <Unavailable />;
  const done = p.status === "completed";
  const timeline = [
    { label: "Registered with RERA", date: p.registered_on },
    { label: "Completion first promised", date: p.proposed_completion },
    ...(p.revised_completion ? [{ label: `Revised completion${p.extensions ? ` (${p.extensions} extension${p.extensions > 1 ? "s" : ""})` : ""}`, date: p.revised_completion }] : []),
    { label: "Registration valid until", date: p.registration_valid_until },
    ...(p.completed_on ? [{ label: "Completed", date: p.completed_on }] : []),
  ].filter((t) => t.date).sort((a, b) => a.date!.localeCompare(b.date!));
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <section className="rr-band slim">
        <div className="wrap">
          <nav className="rr-crumbs" aria-label="Breadcrumb">
            <Link href="/rera">RERA project check</Link> / <Link href={`/rera/localities/${p.locality.slug}`}>{p.locality.name}</Link>
          </nav>
          <div className="rr-title">
            <div>
              <h1>{p.name}</h1>
              <p>
                {p.type_label} by <Link href={`/rera/developers/${p.promoter.slug}`}>{p.promoter.name}</Link> in{" "}
                <Link href={`/rera/localities/${p.locality.slug}`}>{p.locality.name}</Link>, {p.district}
              </p>
              <p className="rr-reg">RERA {p.registration_no}</p>
            </div>
            <RiskBadge level={p.risk.level} label={p.risk.label} />
          </div>
          <SampleNotice data={p.data} />
        </div>
      </section>

      <section className="wrap rr-section rr-detail">
        <div>
          <div className={`rr-panel rr-verdict-panel ${p.risk.level}`}>
            <h2>What a buyer should know</h2>
            {p.risk.flags.length === 0 && <p>Nothing in the RERA record stands out. That covers registration, dates, complaints and sales; it doesn’t cover the land title or approvals, which still need checking.</p>}
            <ul className="rr-flags">
              {p.risk.flags.map((f) => (
                <li key={f.title} className={f.level}>
                  <RiskBadge level={f.level} label={f.title} />
                  <p>{f.detail}</p>
                </li>
              ))}
            </ul>
            {p.risk.good.length > 0 && (
              <ul className="rr-good">{p.risk.good.map((g) => <li key={g}><span aria-hidden>✓</span>{g}</li>)}</ul>
            )}
          </div>

          <div className="rr-panel">
            <h2>Timeline</h2>
            <ol className="rr-timeline">
              {timeline.map((t) => (
                <li key={t.label} className={t.date! <= today ? "past" : undefined}>
                  <b>{day(t.date!)}</b>
                  <span>{t.label}</span>
                </li>
              ))}
              {!done && <li className="now"><b>Today</b><span>{p.status_label}{p.delay_months ? `, ${p.delay_months} months past the first promised date` : ""}</span></li>}
            </ol>
          </div>

          <div className="rr-panel">
            <h2>Homes in this project</h2>
            <Meter value={p.booked_pct} label={`${n(p.booked_units)} of ${n(p.total_units)} units booked`} />
            <div className="rr-mt"><UnitMix mix={p.unit_mix} /></div>
          </div>

        </div>

        <aside className="rr-side">
          <div className="rr-panel">
            <h2>RERA record</h2>
            <dl className="rr-dl">
              <dt>Status</dt><dd>{p.status_label}</dd>
              <dt>Registration no.</dt><dd className="rr-break">{p.registration_no}</dd>
              <dt>Type</dt><dd>{p.type_label}</dd>
              <dt>Address</dt><dd>{[p.address, p.taluk, p.district, p.pincode].filter(Boolean).join(", ") || "–"}</dd>
              <dt>Total units</dt><dd>{n(p.total_units)}</dd>
              <dt>Land area</dt><dd>{p.land_area_sqm ? `${n(Math.round(p.land_area_sqm))} sq m` : "–"}</dd>
              <dt>Price / sq ft</dt><dd>{rupees(p.price_per_sqft)}</dd>
              <dt>Complaints</dt><dd>{n(p.complaints)}</dd>
            </dl>
            {p.source_url && <a className="rr-source" href={p.source_url} target="_blank" rel="noreferrer">View on the RERA portal ↗</a>}
          </div>
          <div className="rr-panel">
            <h2>The developer</h2>
            <p className="rr-side-title"><Link href={`/rera/developers/${p.developer.slug}`}>{p.developer.name}</Link></p>
            <Verdict record={p.developer} />
            <dl className="rr-dl rr-mt">
              <dt>RERA projects</dt><dd>{n(p.developer.projects)}</dd>
              <dt>Completed on time</dt><dd>{pct(p.developer.on_time_pct)} of {n(p.developer.completed)}</dd>
              <dt>Running late now</dt><dd>{n(p.developer.running_late)}</dd>
              <dt>Lapsed or revoked</dt><dd>{n(p.developer.lapsed_or_revoked)}</dd>
              <dt>Complaints</dt><dd>{n(p.developer.complaints)}</dd>
            </dl>
          </div>
          <div className="rr-panel">
            <h2>{p.locality_market.name} market</h2>
            <dl className="rr-dl">
              <dt>Median price / sq ft</dt><dd>{rupees(p.locality_market.median_price_per_sqft)}</dd>
              <dt>This project</dt><dd>{rupees(p.price_per_sqft)}{p.price_per_sqft && p.locality_market.median_price_per_sqft ? ` (${p.price_per_sqft >= p.locality_market.median_price_per_sqft ? "+" : ""}${Math.round((p.price_per_sqft / p.locality_market.median_price_per_sqft - 1) * 100)}%)` : ""}</dd>
              <dt>RERA projects</dt><dd>{n(p.locality_market.projects)}</dd>
              <dt>Units booked</dt><dd>{pct(p.locality_market.booked_pct)}</dd>
              <dt>Running late</dt><dd>{pct(p.locality_market.late_pct)}</dd>
            </dl>
            <Link className="rr-source" href={`/rera/localities/${p.locality_market.slug}`}>See the {p.locality_market.name} report →</Link>
          </div>
          <GetHelp />
        </aside>
      </section>

      {(p.developer_projects.length > 0 || p.nearby.length > 0) && (
        <section className="wrap rr-section rr-more">
          {p.developer_projects.length > 0 && (
            <div className="rr-related">
              <h2>Other projects by {p.promoter.name}</h2>
              <div className="rr-list">{p.developer_projects.map((x) => <ProjectCard key={x.slug} project={x} />)}</div>
            </div>
          )}
          {p.nearby.length > 0 && (
            <div className="rr-related">
              <h2>Other projects in {p.locality.name}</h2>
              <div className="rr-list">{p.nearby.map((x) => <ProjectCard key={x.slug} project={x} />)}</div>
            </div>
          )}
        </section>
      )}
    </>
  );
}
