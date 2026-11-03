"use client";
import { useState, type ReactNode } from "react";
import { DEFAULT_API_BASE_URL } from "@homexo/shared";
import { readSession, signOut } from "../account/session";
import { getToken } from "../admin/api";

// Keep session tokens out of URLs and recheck authorization on every download.
export default function FileLink({ href, children, className, staff = false }: {
  href: string | null; children: ReactNode; className?: string; staff?: boolean;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function open() {
    if (!href) return;
    const token = staff ? getToken() : readSession()?.token;
    if (!token) { setError("Sign in again to open this file."); return; }
    const base = new URL(process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);
    const url = new URL(href, base);
    if (url.origin !== base.origin || !url.pathname.startsWith("/api/v1/files/")) {
      setError("This file link is invalid."); return;
    }
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    setBusy(true); setError("");
    try {
      const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, redirect: "error", cache: "no-store" });
      if (!response.ok) {
        if (response.status === 401 && !staff) signOut();
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not open this file. Reopen the request for a fresh link.");
      }
      const blob = URL.createObjectURL(await response.blob());
      if (tab) tab.location.href = blob;
      else { const link = document.createElement("a"); link.href = blob; link.download = "document"; link.click(); }
      window.setTimeout(() => URL.revokeObjectURL(blob), 60_000);
    } catch (e) {
      tab?.close(); setError(e instanceof Error ? e.message : "Could not open this file.");
    } finally { setBusy(false); }
  }
  if (!href) return <span aria-disabled="true" title="This file is quarantined until its security scan passes.">{children}</span>;
  return <><button type="button" className={className ?? "text-link"} disabled={busy} onClick={open}>{busy ? "Opening…" : children}</button>{error && <span role="alert" className="form-error">{error}</span>}</>;
}
