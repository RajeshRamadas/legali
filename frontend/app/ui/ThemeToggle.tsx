"use client";
import { useEffect, useState } from "react";
import { IconButton } from "./primitives";
export default function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const sync = () =>
      setDark(document.documentElement.dataset.theme === "dark");
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  return (
    <IconButton
      icon={dark ? "sun" : "moon"}
      label={`Switch to ${dark ? "light" : "dark"} theme`}
      onClick={() => {
        const theme = dark ? "light" : "dark";
        document.documentElement.dataset.theme = theme;
        try {
          localStorage.setItem("hx-theme", theme);
        } catch {}
        setDark(!dark);
      }}
    />
  );
}
