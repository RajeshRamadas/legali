import { notFound } from "next/navigation";
import PolicyCentre from "../PolicyCentre";
import { initialPolicy } from "../server";
import { POLICY_LABELS, type PolicyKind, type PolicySnapshot } from "../types";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ kind: string }> }) {
  const { kind } = await params;
  return { title: `${POLICY_LABELS[kind as PolicyKind] || "Policies"} · Homexo Legal` };
}
export default async function PolicyPage({ params, searchParams }: { params: Promise<{ kind: string }>; searchParams: Promise<{ version?: string }> }) {
  const { kind } = await params, query = await searchParams;
  if (!Object.hasOwn(POLICY_LABELS, kind)) notFound();
  const version = query.version ? Number(query.version) : undefined;
  if (query.version && (!/^\d+$/.test(query.version) || !Number.isSafeInteger(version) || !version || version > 2147483647)) notFound();
  return <PolicyCentre kind={kind as PolicyKind} version={version} initial={await initialPolicy<PolicySnapshot>(`/policies/${kind}${version ? `/versions/${version}` : ""}`)} />;
}
