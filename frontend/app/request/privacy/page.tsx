"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { IntakeNotice } from "@homexo/shared";
import { api } from "../../api";
import "../request.css";
export default function IntakePrivacy() {
  const [notice, setNotice] = useState<IntakeNotice | null>(null), [error, setError] = useState("");
  useEffect(() => { api.intakeNotice().then(setNotice).catch(() => setError("The notice could not be loaded. Please try again before starting a draft.")); }, []);
  return <main className="guided-intake"><header className="intake-header"><div className="eyebrow">Your information</div><h1>Guided request privacy notice</h1></header><section className="intake-card">{error ? <p role="alert">{error}</p> : !notice ? <p role="status">Loading notice…</p> : <><p>Notice version: {notice.version}</p>{notice.details.map(text => <p key={text}>{text}</p>)}<h2>Saving a draft</h2><p>{notice.saving}</p><h2>Submitting a request</h2><p>{notice.submission}</p></>}<Link className="btn light" href="/request">Open guided requests</Link></section></main>;
}
