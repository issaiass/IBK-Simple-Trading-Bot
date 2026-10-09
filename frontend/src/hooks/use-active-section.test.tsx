import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useActiveSection } from "./use-active-section";

const IDS = ["overview", "positions", "trades"] as const;

/** Place each section at a vertical position (px from the top of the viewport). */
function layout(tops: Record<string, number>) {
  for (const id of IDS) {
    document.getElementById(id)!.getBoundingClientRect = () => ({ top: tops[id] }) as DOMRect;
  }
}

const scrolled = () => act(() => void window.dispatchEvent(new Event("scroll")));

beforeEach(() => {
  for (const id of IDS) {
    const el = document.createElement("section");
    el.id = id;
    document.body.append(el);
  }
  vi.stubGlobal("innerHeight", 1000);
  layout({ overview: 0, positions: 600, trades: 1200 });
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("useActiveSection", () => {
  it("starts on the first section", () => {
    const { result } = renderHook(() => useActiveSection(IDS));
    expect(result.current).toBe("overview");
  });

  it("follows the page as it scrolls", () => {
    const { result } = renderHook(() => useActiveSection(IDS));
    layout({ overview: -400, positions: 200, trades: 800 });
    scrolled();
    expect(result.current).toBe("positions");
    layout({ overview: -1000, positions: -400, trades: 100 });
    scrolled();
    expect(result.current).toBe("trades");
  });

  it("goes back up too", () => {
    const { result } = renderHook(() => useActiveSection(IDS));
    layout({ overview: -1000, positions: -400, trades: 100 });
    scrolled();
    layout({ overview: 0, positions: 600, trades: 1200 });
    scrolled();
    expect(result.current).toBe("overview");
  });

  it("picks the last section at the very bottom of the page", () => {
    const { result } = renderHook(() => useActiveSection(IDS));
    vi.stubGlobal("scrollY", 1500);
    Object.defineProperty(document.documentElement, "scrollHeight", { configurable: true, value: 2500 });
    layout({ overview: -1500, positions: -900, trades: 600 });
    scrolled();
    expect(result.current).toBe("trades");
    Object.defineProperty(document.documentElement, "scrollHeight", { configurable: true, value: 0 });
  });

  it("re-checks when the window is resized", () => {
    const { result } = renderHook(() => useActiveSection(IDS));
    layout({ overview: -400, positions: 200, trades: 800 });
    act(() => void window.dispatchEvent(new Event("resize")));
    expect(result.current).toBe("positions");
  });

  it("ignores ids that are not on the page", () => {
    const { result } = renderHook(() => useActiveSection(["missing", ...IDS]));
    expect(result.current).toBe("missing"); // the declared first section, until the page says otherwise
    layout({ overview: -400, positions: 200, trades: 800 });
    scrolled();
    expect(result.current).toBe("positions");
  });

  it("stops listening on unmount", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(() => useActiveSection(IDS));
    unmount();
    expect(remove).toHaveBeenCalledWith("scroll", expect.any(Function));
    expect(remove).toHaveBeenCalledWith("resize", expect.any(Function));
  });
});
