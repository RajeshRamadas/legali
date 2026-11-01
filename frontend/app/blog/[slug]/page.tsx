import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { PublicPost } from "@homexo/shared";
import Markdown from "../../Markdown";
import PostCard from "../PostCard";
import { formatPostDate, serverApi } from "../posts";

export const revalidate = 60;

type Params = { params: { slug: string } };

async function load(slug: string): Promise<PublicPost | null> {
  try {
    return await serverApi.getPost(slug);
  } catch (error) {
    if (error instanceof Error && error.message === "Post not found") notFound();
    return null; // API unreachable
  }
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const post = await load(params.slug);
  if (!post) return { title: "Insights · Homexo Legal" };
  return {
    title: `${post.title} · Homexo Legal`,
    description: post.excerpt || undefined,
    openGraph: { title: post.title, description: post.excerpt || undefined, type: "article", publishedTime: post.published_at ?? undefined, images: post.cover_image_url ? [post.cover_image_url] : undefined },
  };
}

export default async function PostPage({ params }: Params) {
  const post = await load(params.slug);
  if (!post) return <section className="wrap blog-list"><p className="blog-empty">This post can’t be loaded right now. Please try again shortly.</p></section>;
  const isCase = post.post_type === "case_study";
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: post.title,
    description: post.excerpt,
    datePublished: post.published_at,
    dateModified: post.updated_at,
    author: { "@type": "Organization", name: "Homexo Legal" },
    image: post.cover_image_url ?? undefined,
  };

  return (
    <>
      <article className="post">
        <header className="wrap post-head">
          <Link className="post-back" href={isCase ? "/blog?type=case_study" : "/blog?type=article"}>← {isCase ? "Case studies" : "Articles"}</Link>
          <span className={`post-type type-${post.post_type}`}>{post.type_label}</span>
          <h1 className="heading">{post.title}</h1>
          {post.excerpt && <p className="post-lede">{post.excerpt}</p>}
          <small>{post.author} · {formatPostDate(post.published_at)} · {post.reading_minutes} min read</small>
        </header>
        {post.cover_image_url && <img className="post-cover wrap" src={post.cover_image_url} alt="" />}
        <div className={`wrap post-layout${post.highlights.length ? " with-facts" : ""}`}>
          <Markdown className="post-body" source={post.body} />
          {post.highlights.length > 0 && (
            <aside className="post-facts">
              <h2>{isCase ? "Case at a glance" : "Key points"}</h2>
              <dl>{post.highlights.map((h, i) => <div key={i}><dt>{h.label}</dt><dd>{h.value}</dd></div>)}</dl>
              <Link className="btn small" href="/#callback">Get a free callback ↗</Link>
            </aside>
          )}
        </div>
        {post.tags.length > 0 && (
          <div className="wrap post-tags">{post.tags.map((tag) => <Link key={tag} href={`/blog?tag=${encodeURIComponent(tag)}`}>#{tag}</Link>)}</div>
        )}
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      </article>
      <section className="wrap post-cta">
        <div><div className="eyebrow">Buying or building?</div><h2 className="heading">Have our advocates check the documents before you pay.</h2></div>
        <Link className="btn gold" href="/#callback">Get a free callback ↗</Link>
      </section>
      {post.related.length > 0 && (
        <section className="wrap blog-list">
          <h2 className="related-title">More {isCase ? "case studies" : "articles"}</h2>
          <div className="blog-grid">{post.related.map((p) => <PostCard key={p.id} post={p} />)}</div>
        </section>
      )}
    </>
  );
}
