import type { Metadata } from "next";
import { Suspense } from "react";
import CustomerAccess from "../account/CustomerAccess";
import GuidedIntake from "./GuidedIntake";
import "../ui/views/documents-documents.css";
import "./request.css";

export const metadata: Metadata = { title: "Start a request · Homexo Legal", robots: { index: false, follow: false } };
export default function RequestPage() {
  return <Suspense fallback={<p role="status">Opening guided request…</p>}><CustomerAccess intro="Verify your phone to start or resume a private guided request. Your completed answers stay with this account."><GuidedIntake /></CustomerAccess></Suspense>;
}
