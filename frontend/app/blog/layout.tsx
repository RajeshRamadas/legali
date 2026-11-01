import "../ui/views/blog-blog.css";

export default function BlogLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <main className="blog">{children}</main>
      <aside className="hx-context-note">
        <div className="wrap">
          <div className="copyright">© 2026 Homexo Legal. Articles and case studies are general information, not legal advice for your property. Legal opinions must be provided by a qualified advocate. Client details in case studies are shared with consent or anonymised.</div>
        </div>
      </aside>
    </>
  );
}
