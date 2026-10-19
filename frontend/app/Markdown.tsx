import type { ReactNode } from "react";

// A small Markdown renderer for blog posts: headings, paragraphs, lists, quotes, rules, images, bold,
// italic, code and links. It builds React elements (never raw HTML), so post bodies can't inject markup.

const SAFE_URL = /^(https?:\/\/|mailto:|tel:|\/|#)/i;

function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  // Order matters: images before links, bold before italic.
  const pattern = /!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_|`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const key = `${keyPrefix}-${i++}`;
    const [, imgAlt, imgSrc, linkText, href, bold1, bold2, em1, em2, code] = match;
    if (imgSrc !== undefined) {
      out.push(SAFE_URL.test(imgSrc) ? <img key={key} src={imgSrc} alt={imgAlt} loading="lazy" /> : imgAlt);
    } else if (href !== undefined) {
      const external = /^https?:\/\//i.test(href);
      out.push(SAFE_URL.test(href)
        ? <a key={key} href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>{inline(linkText, key)}</a>
        : linkText);
    } else if (bold1 ?? bold2) {
      out.push(<strong key={key}>{inline(bold1 ?? bold2, key)}</strong>);
    } else if (em1 ?? em2) {
      out.push(<em key={key}>{inline(em1 ?? em2, key)}</em>);
    } else if (code !== undefined) {
      out.push(<code key={key}>{code}</code>);
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function Markdown({ source, className }: { source: string; className?: string }) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;
    if (!line.trim()) {
      i++;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 5); // "#" is h2: the post title is the page's h1.
      const Tag = `h${level}` as "h2";
      blocks.push(<Tag key={key}>{inline(heading[2].trim(), key)}</Tag>);
      i++;
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push(<hr key={key} />);
      i++;
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={key}><Markdown source={quote.join("\n")} /></blockquote>);
      continue;
    }
    const bullet = /^\s*[-*+]\s+/;
    const numbered = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || numbered.test(line)) {
      const marker = bullet.test(line) ? bullet : numbered;
      const items: string[] = [];
      while (i < lines.length && marker.test(lines[i])) {
        let item = lines[i++].replace(marker, "");
        // Indented lines continue the item.
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !bullet.test(lines[i]) && !numbered.test(lines[i])) item += " " + lines[i++].trim();
        items.push(item);
      }
      const List = marker === bullet ? "ul" : "ol";
      blocks.push(<List key={key}>{items.map((item, n) => <li key={n}>{inline(item, `${key}-${n}`)}</li>)}</List>);
      continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|>|\s*[-*+]\s|\s*\d+[.)]\s|(-{3,}|\*{3,}|_{3,})\s*$)/.test(lines[i])) paragraph.push(lines[i++]);
    if (!paragraph.length) paragraph.push(lines[i++]);
    blocks.push(<p key={key}>{inline(paragraph.join(" "), key)}</p>);
  }
  return <div className={className}>{blocks}</div>;
}
