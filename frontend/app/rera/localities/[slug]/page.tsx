import type { Metadata } from "next";
import Link from "next/link";
import { GetHelp, MarketStats, ProjectCard, RiskBar, SampleNotice, SupplyChart, Unavailable, UnitMix, Verdict, loadOr404, n, pct, rupees, serverApi } from "../../ui";

export const revalidate = 300;

type Params = { params: { slug: string } };

const load = (slug: string) => loadOr404(() => serverApi.getReraLocality(slug));

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const l = await load(params.slug);
  if (!l) return { title: "Locality report · Homexo Legal" };
  return {
    title: `${l.name} property market: RERA projects, prices and delays · Homexo Legal`,
    description: `${l.market.projects} RERA projects in ${l.name}, ${l.district}. Median ${rupees(l.market.median_price_per_sqft)} per sq ft, ${pct(l.market.booked_pct)} of units booked, ${pct(l.market.late_pct)} of projects under construction running late.`,
  };
}

export default async function LocalityPage({ params }: Params) {
  const l = await load(params.slug);
  if (!l) return <Unavailable />;
  const ongoing = l.projects.filter((p) => p.status === "ongoing");
  const rest = l.projects.filter((p) => p.status !== "ongoing");
  return (
    <>
      <section className="rr-band slim">
        <div className="wrap">
          <nav className="rr-crumbs" aria-label="Breadcrumb"><Link href="/rera">RERA project check</Link> / Localities</nav>
          <div className="rr-title">
            <div>
              <h1>{l.name}</h1>
              <p>Property market from the RERA register · {[l.taluk, l.district].filter(Boolean).join(", ")}</p>
            </div>
          </div>
          <SampleNotice data={l.data} />
        </div>
      </section>
      <section className="wrap rr-section">
        <MarketStats market={l.market} delivery={l.delivery} />
        <div className="rr-grid2">
          <div className="rr-panel">
            <h3>Upcoming supply</h3>
            <SupplyChart years={l.supply_by_year} />
          </div>
          <div className="rr-panel">
            <h3>Warning signs</h3>
            <RiskBar risk={l.risk} />
            <h3 className="rr-mt">Homes under construction by type</h3>
            <UnitMix mix={l.unit_mix} />
          </div>
        </div>
        <div className="rr-panel">
          <h3>Developers active in {l.name}</h3>
          <div className="rr-table-wrap">
            <table className="rr-table">
              <thead><tr><th>Developer</th><th>Projects here</th><th>On time (all projects)</th><th>Record</th></tr></thead>
              <tbody>
                {l.developers.map((d) => (
                  <tr key={d.slug}>
                    <td><Link href={`/rera/developers/${d.slug}`}>{d.name}</Link></td>
                    <td>{n(d.projects)}</td>
                    <td>{pct(d.on_time_pct)}</td>
                    <td><Verdict record={d} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {ongoing.length > 0 && <div className="rr-related"><h2>Under construction ({ongoing.length})</h2><div className="rr-list">{ongoing.map((p) => <ProjectCard key={p.slug} project={p} />)}</div></div>}
        {rest.length > 0 && <div className="rr-related"><h2>Completed and other projects ({rest.length})</h2><div className="rr-list">{rest.map((p) => <ProjectCard key={p.slug} project={p} />)}</div></div>}
        <GetHelp />
      </section>
    </>
  );
}
