import type { Metadata } from "next";
import PolicyCentre from "./PolicyCentre";
import { initialPolicy } from "./server";
import type { PolicyIndex } from "./types";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Policies & contact · Homexo Legal" };
export default async function PoliciesPage() {
  return <PolicyCentre initial={await initialPolicy<PolicyIndex>("/policies")} />;
}
