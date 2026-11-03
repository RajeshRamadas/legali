"use client";
import type { ReactNode } from "react";
import SignInForm from "./SignInForm";
import { useSession } from "./session";

export default function CustomerAccess({ children }: { children: ReactNode }) {
  const session = useSession();
  if (session === undefined) return <p role="status">Checking your sign-in…</p>;
  if (!session) return <div className="wrap" style={{ paddingBlock: 32, maxWidth: 560 }}><SignInForm intro="Verify your phone to securely access your requests, documents and bookings. Sign in with the number used for your request." /></div>;
  return <div key={session.profile.contact}>{children}</div>;
}
