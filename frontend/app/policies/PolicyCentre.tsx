"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DEFAULT_API_BASE_URL } from "@homexo/shared";
import MainContent from "../ui/MainContent";
import PolicyBody from "./PolicyBody";
import { POLICY_LABELS, policyDate, type PolicyIndex, type PolicyKind, type PolicySnapshot } from "./types";
import "./policies.css";

export default function PolicyCentre({ kind, version, initial }: { kind?: PolicyKind; version?: number; initial: PolicyIndex | PolicySnapshot | null }) {
  const [data, setData] = useState(initial), [state, setState] = useState<"loading" | "ready" | "missing" | "error">(initial ? "ready" : "loading");
  const [refresh, setRefresh] = useState(0);
  const path = kind ? `/policies/${kind}${version ? `/versions/${version}` : ""}` : "/policies";
  const load = useCallback(() => setRefresh(value => value + 1), []);
  useEffect(() => {
    let active = true;
    fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL}/api/v1${path}`, { cache: "no-store" })
      .then(async response => {
        if (!active) return;
        if (response.status === 404) { setData(null); setState("missing"); return; }
        if (!response.ok) throw new Error("Policy information could not load.");
        const value = await response.json();
        if (active) { setData(value); setState("ready"); }
      }).catch(() => { if (active) { setData(null); setState("error"); } });
    return () => { active = false; };
  }, [path, refresh]);
  const policy = kind && data && state === "ready" ? data as PolicySnapshot : null;
  const index = !kind && data && state === "ready" ? data as PolicyIndex : null;
  return <MainContent className="policies-page"><nav className="policy-nav" aria-label="Policy information">
    <Link href="/policies">Overview</Link>{Object.entries(POLICY_LABELS).map(([key,label]) => <Link key={key} href={`/policies/${key}`} aria-current={key === kind ? "page" : undefined}>{label}</Link>)}
  </nav><header><div className="eyebrow">Information and accountability</div><h1>{policy?.content.title || (kind ? POLICY_LABELS[kind] : "Policies & contact")}</h1>
    {!kind && <p>Read published policy information and find the right route for help.</p>}
    {policy && <><p>{policy.content.summary}</p><p className="policy-meta">Published {policyDate(policy.published_at)} · Version {policy.number} · <Link href={`/policies/${kind}?version=${policy.number}`}>Link to this version</Link>{version && <> · <Link href={`/policies/${kind}`}>Current policy</Link></>}</p></>}
  </header>
    {state === "loading" && <p role="status">Loading policy information…</p>}
    {state === "error" && <div className="policy-card" role="alert"><h2>Policy information is unavailable</h2><p>We couldn&apos;t load the latest information. Please try again.</p><button className="btn light" onClick={load}>Try again</button></div>}
    {state === "missing" && <section className="policy-card"><h2>This policy is not published</h2><p>There is no published information at this address. Use the support routes below for help.</p></section>}
    {index && <div className="policy-grid">{index.items.map(item => <section key={item.kind} className="policy-card"><h2>{item.label}</h2><p>{item.policy?.content.summary || "Published information is not available yet."}</p><Link className="btn light" href={`/policies/${item.kind}`}>{item.available ? "Read published policy" : "View availability"}</Link></section>)}</div>}
    {policy && <article className="policy-document"><PolicyBody content={policy.content} /></article>}
    <aside className="policy-help"><h2>Need help with a request?</h2><p><Link href="/account/support">Support & complaints</Link> gives verified customers a private conversation with the team. For information access, correction or deletion, use <Link href="/account/privacy">Privacy requests</Link>.</p><p>If you cannot sign in, <Link href="/#callback">request a callback</Link>. A callback does not grant access to private records.</p></aside>
  </MainContent>;
}
