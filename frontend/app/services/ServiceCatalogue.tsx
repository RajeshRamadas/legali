"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { Service } from "@homexo/shared";
import { api } from "../api";
import "./catalogue.css";

export default function ServiceCatalogue() {
  const [items, setItems] = useState<Service[] | null>(null), [error, setError] = useState(""), [refresh, setRefresh] = useState(0);
  const [category, setCategory] = useState("all"), [search, setSearch] = useState("");
  useEffect(() => {
    let active = true; setItems(null); setError("");
    api.listServices().then(rows => {
      if (active) { setItems(rows); setCategory(current => current === "all" || rows.some(row => row.category === current) ? current : "all"); }
    }).catch(() => { if (active) setError("We couldn’t load current services. Refresh the catalogue to try again."); });
    return () => { active = false; };
  }, [refresh]);
  const categories = [...new Set(items?.map(item => item.category) ?? [])].sort();
  const term = search.trim().toLowerCase();
  const visible = items?.filter(item => (category === "all" || category === item.category) && `${item.name} ${item.description}`.toLowerCase().includes(term)) ?? [];
  return <section id="live-catalogue" className="section live-catalogue" aria-labelledby="live-catalogue-title"><div className="wrap">
    <div className="section-head"><div><div className="eyebrow">Find the right next step</div><h2 className="heading" id="live-catalogue-title">Services accepting requests</h2></div><p>Explore our current services, then tell us what you need. The team confirms scope, eligibility and charges before proceeding.</p></div>
    <div className="live-catalogue-controls"><label htmlFor="catalogue-category">Service category<select id="catalogue-category" value={category} disabled={!items} onChange={event => setCategory(event.target.value)}><option value="all">All categories</option>{categories.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label htmlFor="catalogue-search">Search services<input id="catalogue-search" type="search" value={search} maxLength={120} onChange={event => setSearch(event.target.value)} placeholder="Try title, documents or registration" /></label>
      <button type="button" className="btn light" disabled={!items && !error} onClick={() => setRefresh(value => value+1)}>Refresh catalogue</button></div>
    {error ? <p role="alert">{error}</p> : !items ? <p role="status">Loading current services…</p> : <>
      <p role="status">{visible.length} {visible.length === 1 ? "service" : "services"} {term || category !== "all" ? visible.length === 1 ? "matches your filters" : "match your filters" : "currently accepting requests"}.</p>
      {!visible.length ? <p>{items.length ? "No services match these filters. Try another category or search." : "No services are accepting new requests right now. Please check again later."}</p> : <div className="service-grid">{visible.map(item => <article className="service-card" key={item.slug}>
        <span className="live-catalogue-category">{item.category}</span><h3>{item.name}</h3><p>{item.description}</p><Link className="text-link" href={`/request?service=${encodeURIComponent(item.slug)}`}>Start request for {item.name} ↗</Link>
      </article>)}</div>}
    </>}
  </div></section>;
}
