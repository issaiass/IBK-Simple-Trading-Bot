"use client";

import { useEffect, useState } from "react";

import { pickActiveSection } from "@/lib/sections";

/** Tracks which of the page's sections the reader is on, for highlighting the matching nav link. */
export function useActiveSection(ids: readonly string[]): string {
  const [active, setActive] = useState(ids[0]);
  const key = ids.join("|");

  useEffect(() => {
    const update = () => {
      const sections = key
        .split("|")
        .map((id) => ({ id, element: document.getElementById(id) }))
        .filter((section): section is { id: string; element: HTMLElement } => section.element !== null)
        .map(({ id, element }) => ({ id, top: element.getBoundingClientRect().top }));

      const page = document.documentElement;
      const scrollable = page.scrollHeight > window.innerHeight;
      const atBottom = scrollable && window.innerHeight + window.scrollY >= page.scrollHeight - 2;

      const next = pickActiveSection(sections, window.innerHeight, atBottom);
      if (next) setActive(next);
    };

    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [key]);

  return active;
}
