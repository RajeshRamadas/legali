"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { formatFee, type LawyerCard, type LawyerFilters, type LawyerSearch, type LawyerSort } from "@homexo/shared";
import { api } from "../api";
import LawyerShell from "./LawyerShell";
import Rating from "./Rating";

const FEE_STEPS = [500, 1000, 1500, 2000, 3000];
const EXPERIENCE_STEPS = [5, 10, 15, 20];
const SORTS: [LawyerSort, string][] = [
  ["relevance", "Most relevant"], ["soonest", "Available soonest"], ["rating", "Highest rated"],
  ["experience", "Most experienced"], ["fee_low", "Fee: low to high"], ["fee_high", "Fee: high to low"],
];

function Card({ lawyer }: { lawyer: LawyerCard }) {
  const href = `/lawyers/${lawyer.slug}`;
  return (
    <article className="lw-card">
      <Link href={href} className="lw-avatar" aria-hidden tabIndex={-1}>{lawyer.initials}</Link>
      <div>
        <h3><Link href={href}>{lawyer.name}</Link></h3>
        <p className="lw-headline">{lawyer.headline}</p>
        <div className="lw-tags">{lawyer.specialisations.map((s) => <span key={s} className="lw-tag">{s}</span>)}</div>
        <ul className="lw-facts">
          <li><b>{lawyer.experience_years} years</b> experience</li>
          <li>{lawyer.locality ? `${lawyer.locality}, ` : ""}{lawyer.city}</li>
          {lawyer.courts.length > 0 && <li className="lw-courts">Practises at <b>{lawyer.courts.join(" · ")}</b></li>}
          <li>Speaks {lawyer.languages.join(", ")}</li>
          {lawyer.consultations > 0 && <li>{lawyer.consultations} consultations</li>}
        </ul>
        <div style={{ marginTop: 8 }}><Rating lawyer={lawyer} /></div>
      </div>
      <div className="lw-book">
        <div>
          <div className="lw-fee"><b>{formatFee(lawyer.consultation_fee)}</b>{lawyer.consultation_minutes}-min video consultation</div>
          {lawyer.next_available
            ? <div className="lw-next">Next available: {lawyer.next_available.day}, {lawyer.next_available.label}</div>
            : <div className="lw-next none">No open slots in the next two weeks</div>}
        </div>
        <Link className="btn small" href={href}>{lawyer.next_available ? "Book consultation" : "View profile"}</Link>
      </div>
    </article>
  );
}

export default function FindLawyerPage() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<LawyerSearch>({ sort: "relevance" });
  const [filters, setFilters] = useState<LawyerFilters | null>(null);
  const [results, setResults] = useState<LawyerCard[] | null>(null);
  const [error, setError] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Arriving from a link like /lawyers?specialisation=Family%20%26%20divorce opens with that filter.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initial: LawyerSearch = { sort: "relevance" };
    for (const key of ["q", "specialisation", "language", "city"] as const) {
      const value = params.get(key);
      if (value) initial[key] = value;
    }
    setQuery(initial.q ?? "");
    setSearch(initial);
    api.lawyerFilters().then(setFilters).catch(() => setFilters(null));
  }, []);

  useEffect(() => {
    setError("");
    api.searchLawyers(search).then((r) => setResults(r.items)).catch((e) => setError(e instanceof Error ? e.message : "Could not load lawyers."));
  }, [search]);

  const set = (patch: Partial<LawyerSearch>) => setSearch((prev) => ({ ...prev, ...patch }));
  const filtered = Boolean(search.q || search.specialisation || search.language || search.city || search.max_fee || search.min_experience || search.available);

  return (
    <LawyerShell>
      <section className="lw-band">
        <div className="wrap">
          <div className="eyebrow">Video consultations · Verified advocates</div>
          <h1>Find a lawyer and book a consultation</h1>
          <p>Compare advocates by specialisation, experience, languages, fees and reviews. Pick a time that suits you and get a Google Meet link on WhatsApp.</p>
          <form className="lw-search" role="search" onSubmit={(e) => { e.preventDefault(); set({ q: query.trim() || undefined }); }}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name, problem or area, e.g. divorce, RERA, Jayanagar" aria-label="Search lawyers" />
            <button className="btn">Search</button>
          </form>
          {filters && (
            <div className="lw-chips" aria-label="Popular specialisations">
              {filters.specialisations.slice(0, 8).map((s) => (
                <button key={s.value} className={`lw-chip${search.specialisation === s.value ? " on" : ""}`} aria-pressed={search.specialisation === s.value}
                  onClick={() => set({ specialisation: search.specialisation === s.value ? undefined : s.value })}>
                  {s.value}<small>{s.count}</small>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <div className="wrap lw-layout">
        <button className="btn small light lw-filter-toggle" aria-expanded={filtersOpen} aria-controls="lw-filters" onClick={() => setFiltersOpen(!filtersOpen)}>
          {filtersOpen ? "Hide filters" : `Filters${filtered ? " (on)" : ""}`}
        </button>
        <aside id="lw-filters" className={`lw-filters${filtersOpen ? " open" : ""}`} aria-label="Filters">
          <h2>Filters</h2>
          <label>Specialisation
            <select value={search.specialisation ?? ""} onChange={(e) => set({ specialisation: e.target.value || undefined })}>
              <option value="">Any</option>
              {filters?.specialisations.map((s) => <option key={s.value} value={s.value}>{s.value} ({s.count})</option>)}
            </select>
          </label>
          <label>Language
            <select value={search.language ?? ""} onChange={(e) => set({ language: e.target.value || undefined })}>
              <option value="">Any</option>
              {filters?.languages.map((s) => <option key={s.value} value={s.value}>{s.value} ({s.count})</option>)}
            </select>
          </label>
          {filters && filters.cities.length > 1 && (
            <label>City
              <select value={search.city ?? ""} onChange={(e) => set({ city: e.target.value || undefined })}>
                <option value="">Any</option>
                {filters.cities.map((s) => <option key={s.value} value={s.value}>{s.value}</option>)}
              </select>
            </label>
          )}
          <label>Consultation fee
            <select value={search.max_fee ?? ""} onChange={(e) => set({ max_fee: e.target.value ? Number(e.target.value) : undefined })}>
              <option value="">Any fee</option>
              {FEE_STEPS.map((f) => <option key={f} value={f}>Up to {formatFee(f)}</option>)}
            </select>
          </label>
          <label>Experience
            <select value={search.min_experience ?? ""} onChange={(e) => set({ min_experience: e.target.value ? Number(e.target.value) : undefined })}>
              <option value="">Any</option>
              {EXPERIENCE_STEPS.map((y) => <option key={y} value={y}>{y}+ years</option>)}
            </select>
          </label>
          <label>Availability
            <select value={search.available ?? ""} onChange={(e) => set({ available: (e.target.value || undefined) as LawyerSearch["available"] })}>
              <option value="">Any time</option>
              <option value="today">Available today</option>
              <option value="3days">Next 3 days</option>
            </select>
          </label>
          {filtered && <button className="lw-clear" onClick={() => { setQuery(""); setSearch({ sort: search.sort }); }}>Clear all filters</button>}
        </aside>

        <section aria-live="polite">
          <div className="lw-results-head">
            <span><b>{results === null ? "Loading…" : `${results.length} lawyer${results.length === 1 ? "" : "s"}`}</b>{search.specialisation ? ` for ${search.specialisation}` : ""}{search.q ? ` matching “${search.q}”` : ""}</span>
            <select value={search.sort} onChange={(e) => set({ sort: e.target.value as LawyerSort })} aria-label="Sort by">
              {SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {error && <p className="lw-error" role="alert">{error}</p>}
          {results?.length === 0 && (
            <div className="lw-empty">
              No lawyers match these filters yet. {filtered ? "Try clearing a filter, or " : ""}<Link href="/#callback" style={{ color: "var(--forest2)", fontWeight: 800 }}>ask us to find one for you</Link>.
            </div>
          )}
          <div className="lw-list">{results?.map((l) => <Card key={l.slug} lawyer={l} />)}</div>
        </section>
      </div>
    </LawyerShell>
  );
}
