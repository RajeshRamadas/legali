"use client";

import { useCallback, useSyncExternalStore } from "react";

export default function useMediaQuery(query: string) {
  const subscribe = useCallback((change: () => void) => {
    const media = window.matchMedia(query);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, [query]);
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false);
}
