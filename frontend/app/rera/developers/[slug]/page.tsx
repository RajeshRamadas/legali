import type { Metadata } from "next";
import Link from "next/link";
import { GetHelp, Meter, ProjectCard, SampleNotice, Stat, Unavailable, Verdict, loadOr404, n, pct, serverApi } from "../../ui";

export const revalidate = 300;

type Params = { params: Promise<{ slug: string }> };

const load = (slug: string) => loadOr404(() => serverApi.getReraDeveloper(slug));

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const d = await load((await params).slug);
  if (!d) return { title: "Developer track record · Homexo Legal" };
  return {
    title: `${d.name}: RERA projects and delivery record · Homexo Legal`,
    description: `${d.name} has ${d.record.projects} Karnataka RERA projects. ${d.record.on_time_pct ?? "–"}% of completed projects were handed over on time; ${d.record.running_late} are running late.`,
  };
}

export default async function DeveloperPage({ params }: Params) {
  const d = await load((await params).slug);
  if (!d) return <Unavailable />;
  const r = d.record;
  const ongoing = d.projects.filter((p) => p.status === "ongoing");
  const rest = d.projects.filter((p) => p.status !== "ongoing");
  return (
    <>
      <section className="rr-band slim">
        <div className="wrap">
          <nav className="rr-crumbs" aria-label="Breadcrumb"><Link href="/rera">RERA project check</Link> / Developers</nav>
          <div className="rr-title">
            <div>
              <h1>{d.name}</h1>
              <p>Track record from {n(r.projects)} Karnataka RERA project{r.projects === 1 ? "" : "s"} in {d.localities.map((l, i) => <span key={l.slug}>{i ? ", " : ""}<Link href={`/rera/localities/${l.slug}`}>{l.name}</Link></span>)}</p>
            </div>
            <Verdict record={r} />
          </div>
          <SampleNotice data={d.data} />
        </div>
      </section>
      <section className="wrap rr-section">
        <div className="rr-stats">
          <Stat value={pct(r.on_time_pct)} label="Completed on time" note={`${n(r.completed)} completed project${r.completed === 1 ? "" : "s"}`} />
          <Stat value={r.avg_delay_months === null ? "–" : `${r.avg_delay_months} mo`} label="Average delay at handover" />
          <Stat value={n(r.running_late)} label="Running late now" note={`of ${n(r.ongoing)} under construction`} />
          <Stat value={n(r.lapsed_or_revoked)} label="Lapsed or revoked" />
          <Stat value={n(r.complaints)} label="Complaints with RERA" />
        </div>
        <div className="rr-panel">
          <h3>How to read this</h3>
          <Meter value={r.on_time_pct} label="Projects handed over within 3 months of the date first promised" />
          <p className="rr-fine rr-mt">
            A developer’s past delivery is the best guide to whether your flat arrives on time. A weak record doesn’t mean a new project will fail,
            but it’s worth asking for a realistic date in the agreement and keeping payments tied to construction stages.
          </p>
        </div>
        {ongoing.length > 0 && <div className="rr-related"><h2>Under construction ({ongoing.length})</h2><div className="rr-list">{ongoing.map((p) => <ProjectCard key={p.slug} project={p} />)}</div></div>}
        {rest.length > 0 && <div className="rr-related"><h2>Completed and other projects ({rest.length})</h2><div className="rr-list">{rest.map((p) => <ProjectCard key={p.slug} project={p} />)}</div></div>}
        <GetHelp />
      </section>
    </>
  );
}
