"use client";
import { useStaff } from "../AdminShell";
import MainContent from "../../ui/MainContent";
import SupportDesk from "../../support/SupportDesk";

export default function SupportQueue() {
  const { user, onError } = useStaff();
  return <MainContent className="support-page"><header><div className="eyebrow">Customer care</div><h1>Support queue</h1><p>Review questions and complaints, reply to customers and track what still needs attention.</p></header>{user.role === "admin" ? <SupportDesk staff onError={onError} /> : <p>Administrator access is required to review support requests.</p>}</MainContent>;
}
