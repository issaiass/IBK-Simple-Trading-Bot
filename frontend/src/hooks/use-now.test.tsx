import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useNow } from "./use-now";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-08T17:00:00Z"));
});
afterEach(() => vi.useRealTimers());

describe("useNow", () => {
  it("starts at the current time", () => {
    const { result } = renderHook(() => useNow(1000));
    expect(result.current).toEqual(new Date("2026-10-08T17:00:00Z"));
  });

  it("ticks on the interval so ages stay fresh", () => {
    const { result } = renderHook(() => useNow(1000));
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current).toEqual(new Date("2026-10-08T17:00:03Z"));
  });

  it("stops ticking after unmount", () => {
    const { unmount } = renderHook(() => useNow(1000));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
