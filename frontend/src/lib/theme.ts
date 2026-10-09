import type { KeyValueStorage } from "./period";

export type Theme = "dark" | "light";

const STORAGE_KEY = "dashboard.theme";

/** Dark is the design's home theme; light is opt-in. */
export function readStoredTheme(storage: KeyValueStorage | null): Theme {
  try {
    return storage?.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function storeTheme(theme: Theme, storage: KeyValueStorage | null): void {
  try {
    storage?.setItem(STORAGE_KEY, theme);
  } catch {
    // a convenience only
  }
}

export const toggledTheme = (theme: Theme): Theme => (theme === "dark" ? "light" : "dark");

/** The theme is the `dark` class on <html>, as shadcn/Tailwind expect. */
export function applyTheme(theme: Theme, root: HTMLElement): void {
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

/**
 * Runs in <head> before the first paint, so a viewer who chose light never sees a dark flash.
 * Kept in sync with `readStoredTheme` / `applyTheme` by a test.
 */
export const THEME_INIT_SCRIPT = `try{var l=localStorage.getItem("${STORAGE_KEY}")==="light";var r=document.documentElement;r.classList.toggle("dark",!l);r.style.colorScheme=l?"light":"dark"}catch(e){}`;
