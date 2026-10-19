"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { PostList, PostType } from "@homexo/shared";
import { useStaff } from "../AdminShell";
import { adminFetch, timeAgo } from "../api";
import { TEMPLATES } from "./templates";

export default function BlogAdminPage() {
  const { user, onError } = useStaff();
  const [type, setType] = useState<PostType | "">("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<PostList | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user.role !== "admin") return;
    const params = new URLSearchParams();
    if (type) params.set("type", type);
    if (status) params.set("status", status);
    if (q.trim()) params.set("q", q.trim());
    params.set("page_size", "100");
    const timer = setTimeout(() => {
      adminFetch<PostList>(`/admin/posts?${params}`).then(setData).catch((e) => setError(onError(e)));
    }, q ? 250 : 0);
    return () => clearTimeout(timer);
  }, [type, status, q, user.role, onError]);

  if (user.role !== "admin") return <p className="admin-empty">Only admins can manage the blog.</p>;

  return (
    <>
      <header className="admin-head">
        <div><div className="eyebrow">Website</div><h1>Blog</h1></div>
        <div className="blog-new">
          {(Object.keys(TEMPLATES) as PostType[]).map((t) => (
            <Link key={t} className={`btn small${t === "case_study" ? " light" : ""}`} href={`/admin/blog/new?type=${t}`}>New {TEMPLATES[t].label.toLowerCase()}</Link>
          ))}
        </div>
      </header>
      {error && <p className="admin-error" role="alert">{error}</p>}
      <div className="admin-filters blog-filters">
        <input type="search" placeholder="Search titles and summaries" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search posts" />
        <select value={type} onChange={(e) => setType(e.target.value as PostType | "")} aria-label="Type">
          <option value="">All types</option><option value="article">Articles</option><option value="case_study">Case studies</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">Drafts and published</option><option value="draft">Drafts</option><option value="published">Published</option>
        </select>
      </div>
      <section className="admin-card">
        <div className="admin-table">
          <div className="admin-row admin-row-head post-row"><span>Title</span><span>Type</span><span>Status</span><span>Updated</span></div>
          {data?.items.map((post) => (
            <Link key={post.id} href={`/admin/blog/${post.id}`} className="admin-row post-row">
              <span><b>{post.title}</b><small>/blog/{post.slug}</small></span>
              <span>{post.type_label}</span>
              <span><span className={`admin-pill pill-post-${post.status}`}>{post.status === "published" ? "Published" : "Draft"}</span></span>
              <span><small>{timeAgo(post.updated_at)} · {post.author}</small></span>
            </Link>
          ))}
          {data && !data.items.length && <p className="admin-empty">{q || type || status ? "No posts match." : "No posts yet. Start one from a template above."}</p>}
          {!data && !error && <p className="admin-empty">Loading…</p>}
        </div>
      </section>
    </>
  );
}
