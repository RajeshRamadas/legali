"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Icon, { type IconName } from "./Icon";
import ThemeToggle from "./ThemeToggle";
import { Avatar, IconButton } from "./primitives";
export type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  count?: number;
};
export type NavGroup = { label: string; items: NavItem[] };
export default function AppShell({
  nav,
  user,
  children,
  onSearch,
  searchPlaceholder = "Search",
  bell,
  mobileTabs,
  onSignOut,
  footer,
  area = "Customer portal",
}: {
  nav: NavGroup[];
  user: { name: string; sub: string; initials: string };
  children: ReactNode;
  onSearch?: (q: string) => void;
  searchPlaceholder?: string;
  bell?: {
    count: number;
    items: { label: string; href: string; onClick?: () => void }[];
  };
  mobileTabs?: NavItem[];
  onSignOut: () => void;
  footer?: ReactNode;
  area?: string;
}) {
  const pathname = usePathname();
  const [menu, setMenu] = useState(false),
    [notices, setNotices] = useState(false),
    [searchOpen, setSearchOpen] = useState(false),
    [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null),
    drawer = useRef<HTMLElement>(null),
    menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenu(false);
    setNotices(false);
    setSearchOpen(false);
  }, [pathname]);
  useEffect(() => {
    if (!menu) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [menu]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => search.current?.focus(), 0);
      }
      if (e.key === "Escape") {
        setMenu(false);
        setNotices(false);
        setSearchOpen(false);
        menuButton.current?.focus();
      }
      if (e.key === "Tab" && menu && drawer.current) {
        const nodes = Array.from(
          drawer.current.querySelectorAll<HTMLElement>("a,button,input"),
        );
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    if (menu) drawer.current?.querySelector<HTMLElement>("button,a")?.focus();
    return () => document.removeEventListener("keydown", key);
  }, [menu]);
  const active = (href: string) =>
    href.includes("#")
      ? false
      : href.split("?")[0] === "/admin"
        ? pathname === "/admin" && !href.includes("?")
        : pathname === href || pathname.startsWith(href + "/");
  const Content=area==="Staff workspace"?"main":"div";
  return (
    <div className={`hx-app-shell ${mobileTabs ? "has-bottom-tabs" : ""}`}>
      {menu && (
        <button
          className="hx-menu-shade"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside
        ref={drawer}
        className={`hx-sidebar ${menu ? "open" : ""}`}
        aria-label={`${area} sidebar`}
      >
        <button
          className="hx-drawer-close hx-icon-button"
          onClick={() => setMenu(false)}
          aria-label="Close navigation"
        >
          ×
        </button>
        <Link
          className="hx-brand"
          href={area === "Staff workspace" ? "/admin" : "/account"}
        >
          <span className="hx-mark">H</span>
          <span>
            homexo<small>{area}</small>
          </span>
        </Link>
        <nav aria-label={area}>
          {nav.map((group) => (
            <div key={group.label} className="hx-nav-group">
              <span>{group.label}</span>
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`hx-nav-item ${active(item.href) ? "on" : ""}`}
                  aria-current={active(item.href) ? "page" : undefined}
                  onClick={() => setMenu(false)}
                >
                  <Icon name={item.icon} />
                  {item.label}
                  {!!item.count && (
                    <span className="hx-count">{item.count}</span>
                  )}
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <div className="hx-shell-user">
          <Avatar initials={user.initials} />
          <div>
            <strong>{user.name}</strong>
            <small>{user.sub}</small>
          </div>
        </div>
        {footer}
        <button className="hx-signout" onClick={onSignOut}>
          Sign out
        </button>
      </aside>
      <div className="hx-app-main">
        <header className="hx-topbar">
          <button
            ref={menuButton}
            className="hx-icon-button hx-mobile-menu"
            onClick={() => setMenu(true)}
            aria-label="Open navigation"
            aria-expanded={menu}
          >
            <Icon name="menu" />
          </button>
          <Link className="hx-mobile-brand" href="/">
            <span className="hx-mark">H</span>homexo
          </Link>
          <form
            className={`hx-shell-search ${searchOpen ? "open" : ""}`}
            onSubmit={(e) => {
              e.preventDefault();
              onSearch?.(query);
              setSearchOpen(false);
            }}
          >
            <Icon name="search" />
            <input
              ref={search}
              aria-label={searchPlaceholder}
              placeholder={searchPlaceholder}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
            />
            <kbd>⌘K</kbd>
            <button
              type="button"
              className="hx-search-close"
              onClick={() => setSearchOpen(false)}
              aria-label="Close search"
            >
              ×
            </button>
          </form>
          <div className="hx-topbar-actions">
            <span className="hx-mobile-menu">
              <IconButton
                icon="search"
                label="Open search"
                onClick={() => {
                  setSearchOpen(true);
                  setTimeout(() => search.current?.focus(), 0);
                }}
              />
            </span>
            <ThemeToggle />
            <div className="hx-notification-wrap">
              <IconButton
                icon="bell"
                label={`Notifications (${bell?.count ?? 0})`}
                dot={!!bell?.count}
                onClick={() => setNotices(!notices)}
              />
              {notices && (
                <div
                  className="hx-notifications"
                  role="region"
                  aria-label="Notifications"
                >
                  <strong>Needs attention</strong>
                  {bell?.items.length ? (
                    bell.items.map((item, i) => (
                      <Link
                        href={item.href}
                        key={i}
                        onClick={() => {
                          item.onClick?.();
                          setNotices(false);
                        }}
                      >
                        {item.label}
                      </Link>
                    ))
                  ) : (
                    <p>You are all caught up.</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </header>
        <Content className="hx-app-content">{children}</Content>
      </div>
      {mobileTabs && (
        <nav className="hx-bottom-tabs" aria-label="Customer shortcuts">
          {mobileTabs.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active(item.href) ? "page" : undefined}
            >
              <Icon name={item.icon} size={20} />
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}
