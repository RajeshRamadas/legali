"use client";
import Link from "next/link";
import { useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import Icon, { type IconName } from "./Icon";
export type Tone =
  | "violet"
  | "green"
  | "amber"
  | "blue"
  | "pink"
  | "red"
  | "gray";
export function Button({
  href,
  icon,
  children,
  variant = "default",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  href?: string;
  icon?: IconName;
  variant?: "default" | "primary" | "dark";
  size?: "sm" | "md" | "pill";
}) {
  const content = (
    <>
      {icon && <Icon name={icon} />} {children}
    </>
  );
  const cls = `hx-button ${variant} ${size} ${className}`;
  return href ? (
    <Link className={cls} href={href}>
      {content}
    </Link>
  ) : (
    <button type="button" className={cls} {...props}>
      {content}
    </button>
  );
}
export function IconButton({
  icon,
  label,
  dot,
  onClick,
}: {
  icon: IconName;
  label: string;
  dot?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      className="hx-icon-button"
      aria-label={label}
      onClick={onClick}
    >
      <Icon name={icon} />
      {dot && <span className="hx-dot" />}
    </button>
  );
}
export function Badge({
  tone = "gray",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return <span className={`hx-badge ${tone}`}>{children}</span>;
}
export function Chip({
  selected,
  onClick,
  children,
}: {
  selected?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`hx-chip ${selected ? "on" : ""}`}
      aria-pressed={selected}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
export function Card({
  title,
  icon,
  action,
  children,
  className = "",
}: {
  title?: string;
  icon?: IconName;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`hx-card ${className}`}>
      {(title || action) && (
        <div className="hx-card-head">
          {title && (
            <h2>
              {icon && (
                <span className="hx-icon-chip">
                  <Icon name={icon} />
                </span>
              )}
              {title}
            </h2>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function StatTile({
  tone,
  icon,
  label,
  value,
  onClick,
}: {
  tone: Tone;
  icon: IconName;
  label: string;
  value: ReactNode;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="hx-stat-icon">
        <Icon name={icon} size={22} />
      </span>
      <span>
        <small>{label}</small>
        <strong>{value}</strong>
      </span>
    </>
  );
  return onClick ? (
    <button type="button" className={`hx-stat ${tone}`} onClick={onClick}>
      {content}
    </button>
  ) : (
    <div className={`hx-stat ${tone}`}>{content}</div>
  );
}
export function Tabs({
  items,
  value,
  onChange,
  label = "Views",
  panelId,
}: {
  items: { id: string; label: string; count?: number }[];
  value: string;
  onChange: (id: string) => void;
  label?: string;
  panelId?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div className="hx-ui-tabs" role="tablist" aria-label={label}>
      {items.map((item, i) => (
        <button
          key={item.id}
          ref={(e) => {
            refs.current[i] = e;
          }}
          type="button"
          role="tab"
          id={panelId ? `${panelId}-tab-${item.id}` : undefined}
          aria-controls={panelId}
          aria-selected={value === item.id}
          tabIndex={value === item.id ? 0 : -1}
          onClick={() => onChange(item.id)}
          onKeyDown={(e) => {
            const n =
              e.key === "ArrowRight"
                ? (i + 1) % items.length
                : e.key === "ArrowLeft"
                  ? (i + items.length - 1) % items.length
                  : e.key === "Home"
                    ? 0
                    : e.key === "End"
                      ? items.length - 1
                      : -1;
            if (n < 0) return;
            e.preventDefault();
            onChange(items[n].id);
            refs.current[n]?.focus();
          }}
        >
          {item.label}
          {item.count !== undefined && <span>{item.count}</span>}
        </button>
      ))}
    </div>
  );
}
export function Avatar({ initials }: { initials: string }) {
  return (
    <span className={`hx-avatar avatar-${initials.charCodeAt(0) % 4}`}>
      {initials}
    </span>
  );
}
export function Skeleton({
  height = 120,
  width = "100%",
}: {
  height?: number;
  width?: string;
}) {
  return (
    <div
      className="hx-skeleton"
      style={{ height, width }}
      role="status"
      aria-label="Loading"
    />
  );
}
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: ReactNode;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="hx-page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="hx-page-actions">{actions}</div>
    </header>
  );
}
export function CaseCard({
  title,
  subtitle,
  stage,
  progress,
  actions,
  badge,
  icon = "case",
  meta,
}: {
  title: string;
  subtitle?: string;
  stage: string;
  progress?: number;
  actions: ReactNode;
  badge?: { tone: Tone; label: string };
  icon?: IconName;
  meta?: ReactNode;
}) {
  return (
    <article className="hx-case">
      <div className="hx-case-top">
        <span className="hx-icon-chip">
          <Icon name={icon} size={22} />
        </span>
        <div>
          <h3>
            {title} {badge && <Badge tone={badge.tone}>{badge.label}</Badge>}
          </h3>
          <p>{subtitle}</p>
        </div>
        {meta && <div className="hx-case-meta">{meta}</div>}
      </div>
      <div className="hx-case-bottom">
        <span>{stage}</span>
        {progress !== undefined && (
          <progress
            max={1}
            value={Math.max(0, Math.min(1, progress))}
            aria-label="Case progress"
          />
        )}
        <div>{actions}</div>
      </div>
    </article>
  );
}
export function AttentionCard({
  title,
  meta,
  featured,
  badge,
  href,
  onClick,
}: {
  title: string;
  meta: string;
  featured?: boolean;
  badge: { tone: Tone; label: string };
  href?: string;
  onClick?: () => void;
}) {
  const content = (
    <>
      <Badge tone={badge.tone}>{badge.label}</Badge>
      <strong>{title}</strong>
      <small>{meta}</small>
    </>
  );
  return href ? (
    <Link className={`hx-attention ${featured ? "featured" : ""}`} href={href}>
      {content}
    </Link>
  ) : (
    <button
      type="button"
      className={`hx-attention ${featured ? "featured" : ""}`}
      onClick={onClick}
    >
      {content}
    </button>
  );
}
export function ListRow({
  leading,
  title,
  meta,
  trailing,
}: {
  leading?: ReactNode;
  title: string;
  meta?: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="hx-list-row">
      {leading}
      <div>
        <strong>{title}</strong>
        <small>{meta}</small>
      </div>
      {trailing && <div className="hx-list-trailing">{trailing}</div>}
    </div>
  );
}
