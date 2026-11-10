"use client";
import CustomerAccess from "../CustomerAccess";
import MainContent from "../../ui/MainContent";
import SupportDesk from "../../support/SupportDesk";

export default function SupportPage() {
  return <MainContent className="support-page"><header><div className="eyebrow">Here to help</div><h1>Support and complaints</h1><p>Ask a question or raise a service issue. Follow the team&apos;s replies here.</p></header><CustomerAccess intro="Sign in with your verified phone to send and follow support requests."><SupportDesk /></CustomerAccess></MainContent>;
}
