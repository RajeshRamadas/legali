import type { Metadata } from "next";
import Link from "next/link";
import type { ReraFilters, ReraRiskLevel, ReraSearch, ReraSearchResult, ReraSort, ReraStatus, ReraSummary } from "@homexo/shared";
import { GetHelp, MarketStats, ProjectCard, RiskBar, SampleNotice, SupplyChart, UnitMix, Verdict, n, pct, rupees, serverApi } from "./ui";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "RERA project check for Karnataka · Homexo Legal",
  description: "Look up any Karnataka RERA project: registration status, promised and revised completion dates, the developer's delivery record, locality prices and warning signs for home buyers.",
};

const PAGE_SIZE = 20;
const SORTS: [ReraSort, string][] = [["name", "Name"], ["risk", "Most warning signs"], ["deadline", "Due soonest"], ["newest", "Newest registration"], ["units", "Largest"], ["price_low", "Price: low to high"]];
type Params = { q?: string; district?: string; locality?: string; status?: string; type?: string; risk?: string; sort?: string; page?: string };

export default async function ReraIndex({ searchParams: query }: { searchParams: Promise<Params> }) {
  const searchParams = await query;
  const search: ReraSearch = {
    q: searchParams.q?.slice(0, 120) || undefined,
    district: searchParams.district || undefined,
    locality: searchParams.locality || undefined,
    status: (searchParams.status || undefined) as ReraStatus | undefined,
    type: searchParams.type || undefined,
    risk: (searchParams.risk || undefined) as ReraRiskLevel | undefined,
    sort: (SORTS.find(([s]) => s === searchParams.sort)?.[0] ?? (searchParams.risk ? "risk" : "name")) as ReraSort,
    page: Math.max(1, Number(searchParams.page) || 1),
    page_size: PAGE_SIZE,
  };
  const searching = Boolean(search.q || search.district || search.locality || search.status || search.type || search.risk);
  const [summary, filters, results] = await Promise.all([
    serverApi.reraSummary().catch(() => null) as Promise<ReraSummary | null>,
    serverApi.reraFilters().catch(() => null) as Promise<ReraFilters | null>,
    (searching ? serverApi.searchReraProjects(search).catch(() => null) : Promise.resolve(null)) as Promise<ReraSearchResult | null>,
  ]);
  const href = (patch: Partial<Params>) => {
    const params = new URLSearchParams();
    Object.entries({ ...searchParams, page: undefined, ...patch }).forEach(([k, v]) => v && params.set(k, String(v)));
    const qs = params.toString();
    return `/rera${qs ? `?${qs}` : ""}#results`;
  };
  const pages = results ? Math.max(1, Math.ceil(results.total / PAGE_SIZE)) : 1;

  return (
    <>
      <section className="rr-band">
        <div className="wrap">
          <div className="eyebrow">Karnataka RERA · For home buyers</div>
          <h1>Check a project before you pay a rupee.</h1>
          <p>Search any RERA-registered project to see whether its registration is valid, how late it is against the date first promised, how many units have sold, and how its developer has delivered before.</p>
          <form className="rr-search" action="/rera#results" method="get" role="search">
            <input name="q" defaultValue={search.q} placeholder="Project name, RERA number, developer, locality or PIN code" aria-label="Search RERA projects" />
            <button className="btn" type="submit">Check project</button>
          </form>
          <div className="rr-quick">
            <span>Quick checks:</span>
            <Link href="/rera?risk=red#results">High-risk projects</Link>
            <Link href="/rera?status=ongoing&sort=deadline#results">Due to complete soonest</Link>
            <Link href="/rera?status=completed#results">Completed projects</Link>
          </div>
          {summary && <SampleNotice data={summary.data} />}
        </div>
      </section>

      {searching && (
        <section className="wrap rr-section" id="results">
          <form className="rr-filters" action="/rera#results" method="get">
            {search.q && <input type="hidden" name="q" value={search.q} />}
            <label>Locality
              <select name="locality" defaultValue={search.locality ?? ""}>
                <option value="">All localities</option>
                {filters?.localities.map((l) => <option key={l.slug} value={l.slug}>{l.name} ({l.projects})</option>)}
              </select>
            </label>
            <label>District
              <select name="district" defaultValue={search.district ?? ""}>
                <option value="">All districts</option>
                {filters?.districts.map((d) => <option key={d.name} value={d.name}>{d.name} ({d.projects})</option>)}
              </select>
            </label>
            <label>Status
              <select name="status" defaultValue={search.status ?? ""}>
                <option value="">Any status</option>
                {filters?.statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </label>
            <label>Type
              <select name="type" defaultValue={search.type ?? ""}>
                <option value="">Any type</option>
                {filters?.types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </label>
            <label>Warning signs
              <select name="risk" defaultValue={search.risk ?? ""}>
                <option value="">Any</option>
                {filters?.risk.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </label>
            <label>Sort by
              <select name="sort" defaultValue={search.sort}>
                {SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <button className="btn small" type="submit">Apply</button>
          </form>
          <div className="rr-results-head">
            <b>{results ? `${n(results.total)} project${results.total === 1 ? "" : "s"}` : "Results"}</b>
            {search.q && <span>matching “{search.q}”</span>}
            <Link href="/rera">Clear search</Link>
          </div>
          {!results && <p className="rr-empty">Projects can’t be loaded right now. Please try again shortly.</p>}
          {results && !results.items.length && <p className="rr-empty">No RERA project matches that. Try the registration number exactly as on the certificate, or fewer words.</p>}
          <div className="rr-list">{results?.items.map((p) => <ProjectCard key={p.slug} project={p} />)}</div>
          {pages > 1 && (
            <nav className="rr-pager" aria-label="Pages">
              {search.page! > 1 ? <Link href={href({ page: String(search.page! - 1) })}>← Previous</Link> : <span />}
              <span>Page {search.page} of {pages}</span>
              {search.page! < pages ? <Link href={href({ page: String(search.page! + 1) })}>Next →</Link> : <span />}
            </nav>
          )}
        </section>
      )}

      {!summary && <section className="wrap rr-section"><p className="rr-empty">The RERA market report can’t be loaded right now. Please try again shortly.</p></section>}
      {summary && summary.data.projects === 0 && <section className="wrap rr-section"><p className="rr-empty">RERA data hasn’t been loaded yet.</p></section>}
      {summary && summary.data.projects > 0 && (
        <section className="wrap rr-section" id="market">
          <div className="rr-section-head">
            <div>
              <div className="eyebrow">Market report</div>
              <h2>What the RERA register says about the market</h2>
            </div>
            <small>Figures as of {new Date(summary.as_of).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</small>
          </div>
          <MarketStats market={summary.market} delivery={summary.delivery} />
          <div className="rr-grid2">
            <div className="rr-panel">
              <h3>New supply by completion year</h3>
              <SupplyChart years={summary.supply_by_year} />
            </div>
            <div className="rr-panel">
              <h3>Warning signs across all projects</h3>
              <RiskBar risk={summary.risk} />
              <h3 className="rr-mt">Homes under construction by type</h3>
              <UnitMix mix={summary.unit_mix} />
            </div>
          </div>

          <div className="rr-panel">
            <h3>Localities by homes registered</h3>
            <div className="rr-table-wrap">
              <table className="rr-table">
                <thead><tr><th>Locality</th><th>Projects</th><th>Units</th><th>Booked</th><th>Median ₹ / sq ft</th><th>Late</th></tr></thead>
                <tbody>
                  {summary.localities.map((l) => (
                    <tr key={l.slug}>
                      <td><Link href={`/rera/localities/${l.slug}`}>{l.name}</Link><small>{l.district}</small></td>
                      <td>{n(l.projects)}</td>
                      <td>{n(l.units)}</td>
                      <td><span className="rr-inline-meter"><i style={{ width: `${l.booked_pct ?? 0}%` }} /></span>{pct(l.booked_pct)}</td>
                      <td>{rupees(l.median_price_per_sqft)}</td>
                      <td>{pct(l.late_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="rr-fine">Booked is the share of units in under-construction and completed projects that are sold. Late is the share of under-construction projects past the completion date first promised.</p>
          </div>

          <div className="rr-panel">
            <h3>Developers with the most RERA projects</h3>
            <div className="rr-table-wrap">
              <table className="rr-table">
                <thead><tr><th>Developer</th><th>Projects</th><th>Completed</th><th>On time</th><th>Running late</th><th>Complaints</th><th>Record</th></tr></thead>
                <tbody>
                  {summary.developers.map((d) => (
                    <tr key={d.slug}>
                      <td><Link href={`/rera/developers/${d.slug}`}>{d.name}</Link></td>
                      <td>{n(d.projects)}</td>
                      <td>{n(d.completed)}</td>
                      <td>{pct(d.on_time_pct)}</td>
                      <td>{n(d.running_late)}</td>
                      <td>{n(d.complaints)}</td>
                      <td><Verdict record={d} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="rr-fine">On time means handed over within 3 months of the completion date first promised to RERA.</p>
          </div>
          <GetHelp />
        </section>
      )}
    </>
  );
}
