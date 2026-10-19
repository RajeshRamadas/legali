import Link from "next/link";
import type { PostSummary } from "@homexo/shared";
import { formatPostDate } from "./posts";

export default function PostCard({ post, lead = false }: { post: PostSummary; lead?: boolean }) {
  return (
    <Link href={`/blog/${post.slug}`} className={`post-card${lead ? " lead" : ""}${post.cover_image_url ? "" : " no-cover"}`}>
      {post.cover_image_url
        ? <img src={post.cover_image_url} alt="" loading={lead ? "eager" : "lazy"} />
        : <div className="post-cover-fallback" aria-hidden><span>{post.post_type === "case_study" ? "Case file" : "Guide"}</span></div>}
      <div className="post-card-body">
        <span className={`post-type type-${post.post_type}`}>{post.type_label}</span>
        <h2 className="serif">{post.title}</h2>
        {post.excerpt && <p>{post.excerpt}</p>}
        <small>{formatPostDate(post.published_at)} · {post.reading_minutes} min read</small>
      </div>
    </Link>
  );
}
