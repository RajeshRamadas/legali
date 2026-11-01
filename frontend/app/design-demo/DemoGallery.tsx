"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import "./demo-gallery.css";

const SCREENS = [
  { id: "public", title: "Public home", file: "1-public-home.html", note: "Public site · hero, services and sample enquiry" },
  { id: "customer", title: "Customer portal", file: "2-customer-dashboard.html", note: "Customer portal · attention cards, requests and documents" },
  { id: "staff", title: "Staff workspace", file: "3-staff-workspace.html", note: "Staff workspace · case filters, calendar and queue" },
  { id: "assistant", title: "AI assistant", file: "5-ai-assistant.html", note: "Assistant · scripted demo replies, transcript export and clear" },
] as const;
type Screen = typeof SCREENS[number]["id"];
const isScreen = (value: unknown): value is Screen => SCREENS.some(screen => screen.id === value);

export default function DemoGallery() {
  const [screen, setScreen] = useState<Screen>("public");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [width, setWidth] = useState<"full" | "mobile">("full");
  const [ready, setReady] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = SCREENS.find(item => item.id === screen)!;
  const setFrameTheme = useCallback(() => {
    frame.current?.contentWindow?.postMessage({ type: "homexo-demo:theme", theme }, window.location.origin);
  }, [theme]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("hx-demo-theme");
      setTheme(saved === "dark" || (saved !== "light" && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light");
    } catch { /* A blocked store does not prevent review. */ }
    const id = window.location.hash.slice(1);
    if (isScreen(id)) setScreen(id);
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem("hx-demo-theme", theme); } catch { /* Keep an in-memory preference. */ }
    setFrameTheme();
  }, [theme, ready, setFrameTheme]);
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === "homexo-demo:navigate" && isScreen(event.data.screen)) choose(event.data.screen);
      if (event.data?.type === "homexo-demo:toggle-theme") setTheme(value => value === "light" ? "dark" : "light");
    };
    const onHash = () => { if (isScreen(location.hash.slice(1))) setScreen(location.hash.slice(1) as Screen); };
    window.addEventListener("message", onMessage);
    window.addEventListener("hashchange", onHash);
    return () => { window.removeEventListener("message", onMessage); window.removeEventListener("hashchange", onHash); };
  }, []);
  function choose(id: Screen) {
    setScreen(id);
    history.replaceState(null, "", `#${id}`);
  }
  return <main className="demo-gallery" data-demo-theme={theme}>
    <header className="demo-reviewbar">
      <div className="demo-review-brand"><span className="demo-review-mark">H</span><div><strong>Homexo UI</strong><span>Design review · fictional sample data</span></div></div>
      <nav className="demo-review-tabs" role="tablist" aria-label="Demo screens">
        {SCREENS.map((item, index) => <button key={item.id} id={`demo-tab-${item.id}`} ref={element => { tabRefs.current[index] = element; }} type="button" role="tab" aria-selected={screen === item.id} aria-controls="demo-screen" tabIndex={screen === item.id ? 0 : -1} onClick={() => choose(item.id)} onKeyDown={event => {
          let next = index;
          if (event.key === "ArrowRight") next = (index + 1) % SCREENS.length;
          else if (event.key === "ArrowLeft") next = (index + SCREENS.length - 1) % SCREENS.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = SCREENS.length - 1;
          else return;
          event.preventDefault(); choose(SCREENS[next].id); tabRefs.current[next]?.focus();
        }}>{item.title}</button>)}
      </nav>
      <div className="demo-review-actions">
        <button type="button" onClick={() => setWidth(value => value === "full" ? "mobile" : "full")} aria-pressed={width === "mobile"}>{width === "mobile" ? "Full width" : "Phone view"}</button>
        <button type="button" onClick={() => setTheme(value => value === "light" ? "dark" : "light")} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}>{theme === "light" ? "◐ Dark" : "☀ Light"}</button>
      </div>
    </header>
    <div className="demo-review-caption"><span>{selected.note}</span><span>Preview only · sample interactions · no live cases</span></div>
    <section className={`demo-stage ${width === "mobile" ? "demo-phone" : ""}`} id="demo-screen" role="tabpanel" aria-labelledby={`demo-tab-${screen}`}>
      {ready ? <iframe ref={frame} key={screen} title={`${selected.title} interactive design demo`} src={`/demo-ui/${selected.file}`} onLoad={setFrameTheme} /> : <p className="demo-loading">Preparing design preview…</p>}
    </section>
  </main>;
}
