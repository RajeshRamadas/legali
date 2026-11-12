"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import BrandMark from "./BrandMark";
import Dialog from "./Dialog";
import MainContent from "./MainContent";
import useMediaQuery from "./useMediaQuery";
import Icon, { type IconName } from "./Icon";
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
  const mobile = useMediaQuery("(max-width: 1000px)");
  const search = useRef<HTMLInputElement>(null);
  const notifications = useRef<HTMLDivElement>(null);
  const noticeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenu(false);
    setNotices(false);
    setSearchOpen(false);
  }, [pathname, mobile]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (!event.defaultPrevented && !document.querySelector("dialog[open]") &&
          (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
        setTimeout(() => search.current?.focus(), 0);
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {
    if (!notices) return;
    const panel = notifications.current?.querySelector<HTMLElement>(".hx-notifications");
    (panel?.querySelector<HTMLElement>("a") ?? panel)?.focus();
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !notifications.current?.contains(event.target)) setNotices(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [notices]);
  const exactNavigation = nav.some(group => group.items.some(item => item.href === pathname));
  const active = (href: string) =>
    href.includes("#")
      ? false
      : href.split("?")[0] === "/admin"
        ? pathname === "/admin" && !href.includes("?")
        : href === "/account" ? pathname === href : pathname === href || (!exactNavigation && pathname.startsWith(href + "/"));
  const sidebar = (
      <aside
        id="workspace-navigation"
        className="hx-sidebar"
        aria-label={`${area} sidebar`}
      >
        <button
          type="button"
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
          <BrandMark />
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
        <button className="hx-signout" onClick={() => { setMenu(false); onSignOut(); }}>
          Sign out
        </button>
      </aside>
  );
  const searchForm = (
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
  );
  return (
    <div className={`hx-app-shell ${mobileTabs ? "has-bottom-tabs" : ""}`}>
      {mobile ? <Dialog open={menu} onClose={() => setMenu(false)} label={`${area} navigation`} className="hx-navigation-dialog">
        {sidebar}
      </Dialog> : sidebar}

      <div className="hx-app-main">
        <header className="hx-topbar">
          <button
            className="hx-icon-button hx-mobile-menu"
            onClick={() => setMenu(true)}
            aria-label="Open navigation"
            aria-expanded={menu}
            aria-controls="workspace-navigation"
            aria-haspopup="dialog"
          >
            <Icon name="menu" />
          </button>
          <Link className="hx-mobile-brand" href="/">
            <BrandMark />homexo
          </Link>
          {mobile ? <Dialog open={searchOpen} onClose={() => setSearchOpen(false)} label="Search workspace" className="hx-search-dialog">
            {searchForm}
          </Dialog> : searchForm}

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
            <div className="hx-notification-wrap" ref={notifications} onBlur={(event) => {
              if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setNotices(false);
            }} onKeyDown={(event) => {
              if (event.key === "Escape" && notices) {
                event.preventDefault(); event.stopPropagation(); setNotices(false); noticeButton.current?.focus();
              }
            }}>
              <IconButton
                ref={noticeButton}
                aria-expanded={notices}
                aria-controls="workspace-notifications"
                icon="bell"
                label={`Notifications (${bell?.count ?? 0})`}
                dot={!!bell?.count}
                onClick={() => setNotices(!notices)}
              />
              {notices && (
                <div
                  className="hx-notifications"
                  id="workspace-notifications"
                  tabIndex={-1}
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
        <MainContent className="hx-app-content">{children}</MainContent>
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
