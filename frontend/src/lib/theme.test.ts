import { describe, expect, it } from "vitest";

import { applyTheme, readStoredTheme, storeTheme, THEME_INIT_SCRIPT, toggledTheme } from "./theme";

const storage = (initial: Record<string, string> = {}, broken = false) => {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => {
      if (broken) throw new Error("denied");
      return data[k] ?? null;
    },
    setItem: (k: string, v: string) => {
      if (broken) throw new Error("denied");
      data[k] = v;
    },
  };
};

describe("theme", () => {
  it("is dark unless the viewer chose light", () => {
    expect(readStoredTheme(storage())).toBe("dark");
    expect(readStoredTheme(storage({ "dashboard.theme": "light" }))).toBe("light");
    expect(readStoredTheme(storage({ "dashboard.theme": "purple" }))).toBe("dark");
    expect(readStoredTheme(storage({}, true))).toBe("dark");
    expect(readStoredTheme(null)).toBe("dark");
  });

  it("remembers the choice and survives broken storage", () => {
    const s = storage();
    storeTheme("light", s);
    expect(readStoredTheme(s)).toBe("light");
    expect(() => storeTheme("dark", storage({}, true))).not.toThrow();
  });

  it("toggles between the two", () => {
    expect(toggledTheme("dark")).toBe("light");
    expect(toggledTheme("light")).toBe("dark");
  });

  it("applies the theme as a class on the root element, plus the matching colour scheme", () => {
    const root = document.createElement("html");
    applyTheme("dark", root);
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.style.colorScheme).toBe("dark");
    applyTheme("light", root);
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.style.colorScheme).toBe("light");
  });

  it("ships a small inline script that applies the stored theme before the first paint", () => {
    const root = document.documentElement;
    root.classList.add("dark");
    localStorage.setItem("dashboard.theme", "light");
    new Function(THEME_INIT_SCRIPT)();
    expect(root.classList.contains("dark")).toBe(false);
    localStorage.removeItem("dashboard.theme");
    root.classList.remove("dark");
    new Function(THEME_INIT_SCRIPT)();
    expect(root.classList.contains("dark")).toBe(true);
  });
});
