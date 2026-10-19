import type { Metadata } from "next";
import Link from "next/link";
import type { PostList, PostType } from "@homexo/shared";
import PostCard from "./PostCard";
import { POST_TYPE_TABS, serverApi } from "./posts";

export const revalidate = 60;

export const metadata: Metadata = {
  title: "Insights · Homexo Legal",
  description: "Articles and case studies on property legal verification, registration and documents in Bangalore.",
};

const PAGE_SIZE = 12;

export default async function BlogIndex({ searchParams }: { searchParams: { type?: string; tag?: string; page?: string } }) {
  const type = (["article", "case_study"] as const).find((t) => t === searchParams.type) as PostType | undefined;
  const tag = searchParams.tag?.slice(0, 40) || undefined;
  const page = Math.max(1, Number(searchParams.page) || 1);
  let data: PostList | null = null;
  try {
    data = await serverApi.listPosts({ type, tag, page, pageSize: PAGE_SIZE });
  } catch {
    // The API is down: show the page with a message instead of failing.
  }
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const query = (next: Record<string, string | number | undefined>) => {
    const params = new URLSearchParams();
    Object.entries({ type, tag, ...next }).forEach(([k, v]) => v !== undefined && v !== "" && params.set(k, String(v)));
    const qs = params.toString();
    return `/blog${qs ? `?${qs}` : ""}`;
  };
  const [lead, ...rest] = data?.items ?? [];

  return (
    <>
      <section className="blog-hero">
        <div className="wrap">
          <div className="eyebrow">Insights</div>
          <h1 className="serif">Property law, explained from real files.</h1>
          <p>Guides to the documents behind a safe purchase, and case studies from the properties our advocates have verified.</p>
          <nav className="blog-tabs" aria-label="Filter posts">
            {POST_TYPE_TABS.map((tab) => <Link key={tab.label} href={tab.href} className={tab.value === (type ?? null) && !tag ? "on" : undefined}>{tab.label}</Link>)}
            {tag && <span className="blog-tag-filter">Tagged “{tag}” <Link href={query({ tag: undefined, page: undefined })} aria-label="Clear tag">×</Link></span>}
          </nav>
        </div>
      </section>
      <section className="wrap blog-list">
        {!data && <p className="blog-empty">Posts can’t be loaded right now. Please try again shortly.</p>}
        {data && !data.items.length && <p className="blog-empty">Nothing published here yet. Check back soon.</p>}
        {lead && page === 1 && <PostCard post={lead} lead />}
        <div className="blog-grid">
          {(page === 1 ? rest : data?.items ?? []).map((post) => <PostCard key={post.id} post={post} />)}
        </div>
        {pages > 1 && (
          <nav className="blog-pager" aria-label="Pages">
            {page > 1 ? <Link href={query({ page: page - 1 })}>← Newer</Link> : <span />}
            <span>Page {page} of {pages}</span>
            {page < pages ? <Link href={query({ page: page + 1 })}>Older →</Link> : <span />}
          </nav>
        )}
      </section>
    </>
  );
}
