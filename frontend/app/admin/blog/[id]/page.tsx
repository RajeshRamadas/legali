"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { Post, PostType } from "@homexo/shared";
import Markdown from "../../../Markdown";
import { useStaff } from "../../AdminShell";
import { adminFetch, formatDate } from "../../api";
import { TEMPLATES } from "../templates";

type Form = {
  post_type: PostType;
  title: string;
  slug: string;
  excerpt: string;
  cover_image_url: string;
  tags: string;
  highlights: { label: string; value: string }[];
  body: string;
};

function fromTemplate(type: PostType): Form {
  const t = TEMPLATES[type];
  return { post_type: type, title: "", slug: "", excerpt: t.excerpt, cover_image_url: "", tags: "", highlights: t.highlights.map((h) => ({ ...h })), body: t.body };
}

function fromPost(post: Post): Form {
  return {
    post_type: post.post_type, title: post.title, slug: post.slug, excerpt: post.excerpt, cover_image_url: post.cover_image_url ?? "",
    tags: post.tags.join(", "), highlights: post.highlights.map((h) => ({ ...h })), body: post.body,
  };
}

function payload(form: Form) {
  return {
    post_type: form.post_type,
    title: form.title.trim(),
    ...(form.slug.trim() ? { slug: form.slug.trim() } : {}),
    excerpt: form.excerpt.trim(),
    cover_image_url: form.cover_image_url.trim(),
    tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
    highlights: form.highlights.filter((h) => h.label.trim() && h.value.trim()).map((h) => ({ label: h.label.trim(), value: h.value.trim() })),
    body: form.body,
  };
}

export default function PostEditorPage() {
  const { user, onError } = useStaff();
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const isNew = id === "new";
  const [post, setPost] = useState<Post | null>(null);
  const [form, setForm] = useState<Form | null>(isNew ? fromTemplate(searchParams.get("type") === "case_study" ? "case_study" : "article") : null);
  const [saved, setSaved] = useState<string>(form ? JSON.stringify(form) : "");
  const [view, setView] = useState<"write" | "preview">("write");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isNew || user.role !== "admin") return;
    adminFetch<Post>(`/admin/posts/${id}`).then((p) => {
      setPost(p);
      const f = fromPost(p);
      setForm(f);
      setSaved(JSON.stringify(f));
    }).catch((e) => setError(onError(e)));
  }, [id, isNew, user.role, onError]);

  const dirty = form !== null && JSON.stringify(form) !== saved;
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (user.role !== "admin") return <p className="admin-empty">Only admins can manage the blog.</p>;
  if (!form) return error ? <p className="admin-error" role="alert">{error}</p> : <p className="admin-empty">Loading…</p>;

  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  function changeType(type: PostType) {
    // On a new post still holding the untouched template, switch to the other template.
    const untouched = isNew && form!.body === TEMPLATES[form!.post_type].body;
    set(untouched ? { ...fromTemplate(type), title: form!.title, slug: form!.slug, tags: form!.tags, cover_image_url: form!.cover_image_url } : { post_type: type });
  }

  async function save(status?: "draft" | "published") {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const body = JSON.stringify({ ...payload(form!), ...(status ? { status } : {}) });
      const result = isNew
        ? await adminFetch<Post>("/admin/posts", { method: "POST", body })
        : await adminFetch<Post>(`/admin/posts/${post!.id}`, { method: "PATCH", body });
      const f = fromPost(result);
      setPost(result);
      setForm(f);
      setSaved(JSON.stringify(f));
      setNotice(status === "published" ? "Published. It’s live on the website." : status === "draft" && post?.status === "published" ? "Unpublished. It’s hidden from the website." : "Saved.");
      if (isNew) router.replace(`/admin/blog/${result.id}`);
    } catch (e) {
      setError(onError(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!post || !window.confirm(`Delete “${post.title}”? This can’t be undone.`)) return;
    setBusy(true);
    try {
      await adminFetch(`/admin/posts/${post.id}`, { method: "DELETE" });
      setSaved(JSON.stringify(form));
      router.push("/admin/blog");
    } catch (e) {
      setError(onError(e));
      setBusy(false);
    }
  }

  const published = post?.status === "published";
  const template = TEMPLATES[form.post_type];

  return (
    <>
      <Link className="admin-back" href="/admin/blog">← All posts</Link>
      <header className="admin-head">
        <div>
          <div className="eyebrow">{isNew ? `New ${template.label.toLowerCase()}` : template.label}</div>
          <h1>{form.title.trim() || "Untitled"}</h1>
          <div className="ticket-badges">
            <span className={`admin-pill pill-post-${post?.status ?? "draft"}`}>{published ? "Published" : "Draft"}</span>
            {post?.published_at && <small className="muted">First published {formatDate(post.published_at)}</small>}
            {dirty && <small className="needs-reply">Unsaved changes</small>}
          </div>
        </div>
        <div className="blog-actions">
          {published && <a className="btn small light" href={`/blog/${post!.slug}`} target="_blank" rel="noreferrer">View on site ↗</a>}
          <button className="btn small light" disabled={busy || (!dirty && !isNew)} onClick={() => save()}>{published ? "Save changes" : "Save draft"}</button>
          {published
            ? <button className="btn small light" disabled={busy} onClick={() => save("draft")}>Unpublish</button>
            : <button className="btn small" disabled={busy} onClick={() => save("published")}>Publish</button>}
        </div>
      </header>
      {(error || notice) && <p className={error ? "admin-error" : "admin-notice"} role={error ? "alert" : "status"}>{error || notice}</p>}

      <div className="post-editor">
        <section className="admin-card admin-form post-editor-main">
          <label>Title<input required minLength={3} maxLength={200} value={form.title} placeholder={form.post_type === "case_study" ? "e.g. Whitefield apartment: a missing link in the title chain" : "e.g. How to read an Encumbrance Certificate"} onChange={(e) => set({ title: e.target.value })} /></label>
          <label>Summary<textarea rows={2} maxLength={400} value={form.excerpt} placeholder="One or two sentences shown on the blog page and in search results." onChange={(e) => set({ excerpt: e.target.value })} /></label>
          <div className="post-body-head">
            <span>Body</span>
            <div className="admin-toggle">
              <button type="button" className={view === "write" ? "on" : undefined} onClick={() => setView("write")}>Write</button>
              <button type="button" className={view === "preview" ? "on" : undefined} onClick={() => setView("preview")}>Preview</button>
            </div>
          </div>
          {view === "write"
            ? <textarea className="post-body-input" aria-label="Body" value={form.body} onChange={(e) => set({ body: e.target.value })} />
            : <div className="post-preview"><Markdown className="post-body" source={form.body || "_Nothing written yet._"} /></div>}
          <small className="admin-footnote">Formatting: <code>## Heading</code>, <code>**bold**</code>, <code>*italic*</code>, <code>- list</code>, <code>1. list</code>, <code>&gt; quote</code>, <code>[link](https://…)</code>, <code>![image](https://…)</code>. Replace the [bracketed] prompts from the template.</small>
        </section>

        <aside className="post-editor-side">
          <section className="admin-card admin-form">
            <h2>Settings</h2>
            <label>Type
              <select value={form.post_type} onChange={(e) => changeType(e.target.value as PostType)}>
                <option value="article">Article</option><option value="case_study">Case study</option>
              </select>
            </label>
            <small className="admin-footnote">{template.hint}</small>
            <label>Web address
              <div className="slug-input"><span>/blog/</span><input value={form.slug} pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder={isNew ? "made from the title" : ""} onChange={(e) => set({ slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} /></div>
            </label>
            {published && form.slug !== post!.slug && <small className="admin-footnote needs-reply">Changing the address breaks links people already shared.</small>}
            <label>Cover image URL<input type="url" value={form.cover_image_url} placeholder="https://…" onChange={(e) => set({ cover_image_url: e.target.value })} /></label>
            {form.cover_image_url && /^(https?:\/\/|\/)/.test(form.cover_image_url) && <img className="post-cover-preview" src={form.cover_image_url} alt="" />}
            <label>Tags<input value={form.tags} placeholder="e.g. Title verification, Whitefield" onChange={(e) => set({ tags: e.target.value })} /></label>
            <small className="admin-footnote">Comma-separated, up to 8.</small>
          </section>

          <section className="admin-card admin-form">
            <h2>{form.post_type === "case_study" ? "Case at a glance" : "Key points"}</h2>
            <small className="admin-footnote">Short facts shown beside the post. Leave empty to hide the box.</small>
            {form.highlights.map((h, i) => (
              <div className="highlight-row" key={i}>
                <input aria-label="Label" placeholder="Label" maxLength={40} value={h.label} onChange={(e) => set({ highlights: form.highlights.map((x, n) => (n === i ? { ...x, label: e.target.value } : x)) })} />
                <input aria-label="Value" placeholder="Value" maxLength={160} value={h.value} onChange={(e) => set({ highlights: form.highlights.map((x, n) => (n === i ? { ...x, value: e.target.value } : x)) })} />
                <button type="button" className="admin-link" aria-label="Remove" onClick={() => set({ highlights: form.highlights.filter((_, n) => n !== i) })}>×</button>
              </div>
            ))}
            {form.highlights.length < 8 && <button type="button" className="admin-link" onClick={() => set({ highlights: [...form.highlights, { label: "", value: "" }] })}>+ Add a fact</button>}
          </section>

          {post && (
            <section className="admin-card">
              <h2>Danger zone</h2>
              <button className="admin-link danger" disabled={busy} onClick={remove}>Delete this post</button>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
