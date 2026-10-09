"use client";

import { useSyncExternalStore } from "react";

/**
 * Whether a CSS media query currently matches. `fallback` is used where there is no
 * `matchMedia` (the server render, and jsdom), so pick the layout you want there.
 */
export function useMediaQuery(query: string, fallback: boolean): boolean {
  const subscribe = (notify: () => void) => {
    if (typeof matchMedia !== "function") return () => {};
    const list = matchMedia(query);
    list.addEventListener("change", notify);
    return () => list.removeEventListener("change", notify);
  };
  const snapshot = () => (typeof matchMedia === "function" ? matchMedia(query).matches : fallback);
  return useSyncExternalStore(subscribe, snapshot, () => fallback);
}
