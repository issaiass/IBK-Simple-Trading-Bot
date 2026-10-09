import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMediaQuery } from "./use-media-query";

type Listener = () => void;

function stubMatchMedia(initial: boolean) {
  let matches = initial;
  const listeners = new Set<Listener>();
  const mql = {
    get matches() {
      return matches;
    },
    addEventListener: (_: string, l: Listener) => listeners.add(l),
    removeEventListener: (_: string, l: Listener) => listeners.delete(l),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => mql));
  return {
    set(value: boolean) {
      matches = value;
      listeners.forEach((l) => l());
    },
    listeners,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("useMediaQuery", () => {
  it("reports whether the query matches", () => {
    stubMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)", true));
    expect(result.current).toBe(false);
  });

  it("follows changes", () => {
    const media = stubMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)", true));
    expect(result.current).toBe(true);
    act(() => media.set(false));
    expect(result.current).toBe(false);
  });

  it("unsubscribes on unmount", () => {
    const media = stubMatchMedia(true);
    const { unmount } = renderHook(() => useMediaQuery("(min-width: 768px)", true));
    unmount();
    expect(media.listeners.size).toBe(0);
  });

  it("uses the fallback where matchMedia does not exist (server, old test environments)", () => {
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)", true));
    expect(result.current).toBe(true);
  });
});
