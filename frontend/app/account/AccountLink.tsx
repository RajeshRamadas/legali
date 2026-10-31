"use client";

import Link from "next/link";
import { useSession } from "./session";

// "Sign in" until the customer signs in on this browser, then "My account".
export default function AccountLink({ className, onClick }: { className?: string; onClick?: () => void }) {
  const session = useSession();
  return <Link className={className} href="/account" onClick={onClick}>{session ? "My account" : "Sign in"}</Link>;
}
