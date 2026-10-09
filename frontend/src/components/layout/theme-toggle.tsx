"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { browserStorage } from "@/lib/period";
import { applyTheme, storeTheme, toggledTheme, type Theme } from "@/lib/theme";

/** The page's own `dark` class is the source of truth (set before first paint by the init script). */
function subscribe(notify: () => void): () => void {
  const observer = new MutationObserver(notify);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

const currentTheme = (): Theme => (document.documentElement.classList.contains("dark") ? "dark" : "light");

/** Light/dark switch. */
export function ThemeToggle() {
  // The server cannot know the viewer's theme, so it renders dark and the client corrects it.
  const theme = useSyncExternalStore<Theme>(subscribe, currentTheme, () => "dark");
  const next = toggledTheme(theme);
  const Icon = theme === "dark" ? Sun : Moon;

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-label={`Switch to ${next} theme`}
      onClick={() => {
        applyTheme(next, document.documentElement);
        storeTheme(next, browserStorage());
      }}
      className="w-full justify-start gap-3 text-zinc-400 hover:bg-white/5 hover:text-zinc-100"
    >
      <Icon aria-hidden />
      {next === "light" ? "Light theme" : "Dark theme"}
    </Button>
  );
}
