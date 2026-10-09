import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emptyDashboard, sampleDashboard } from "@/test/fixtures";
import type { DashboardData } from "@/types/dashboard";

import { useDashboard } from "./use-dashboard";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-08T17:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

/** Let pending promises (the fetch and the state updates) settle. */
const flush = () => act(async () => {});

describe("useDashboard", () => {
  it("starts loading with no data", () => {
    const fetcher = vi.fn(() => new Promise<DashboardData>(() => {}));
    const { result } = renderHook(() => useDashboard({ fetcher }));
    expect(result.current).toMatchObject({ data: null, error: null, isLoading: true, lastUpdated: null });
  });

  it("exposes the data once the first fetch resolves", async () => {
    const data = sampleDashboard();
    const { result } = renderHook(() => useDashboard({ fetcher: async () => data }));
    await flush();
    expect(result.current.data).toEqual(data);
    expect(result.current).toMatchObject({ error: null, isLoading: false });
    expect(result.current.lastUpdated).toEqual(new Date("2026-10-08T17:00:00Z"));
  });

  it("refreshes every 30 seconds by default", async () => {
    const fetcher = vi.fn(async () => emptyDashboard());
    renderHook(() => useDashboard({ fetcher }));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_999);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("honours a custom interval", async () => {
    const fetcher = vi.fn(async () => emptyDashboard());
    renderHook(() => useDashboard({ fetcher, intervalMs: 5_000 }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("reports an error when the very first fetch fails", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("API unreachable");
    });
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    expect(result.current).toMatchObject({ data: null, error: "API unreachable", isLoading: false });
  });

  it("keeps the last good data when a later refresh fails", async () => {
    const data = sampleDashboard();
    const fetcher = vi
      .fn<() => Promise<DashboardData>>()
      .mockResolvedValueOnce(data)
      .mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(result.current.data).toEqual(data);
    expect(result.current.error).toBe("boom");
    expect(result.current.lastUpdated).toEqual(new Date("2026-10-08T17:00:00Z"));
  });

  it("clears the error when a refresh succeeds again", async () => {
    const fetcher = vi
      .fn<() => Promise<DashboardData>>()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(emptyDashboard());
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    expect(result.current.error).toBe("boom");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.data).not.toBeNull();
  });

  it("turns a non-Error rejection into a readable message", async () => {
    const fetcher = vi.fn(async () => {
      throw "weird";
    });
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    expect(result.current.error).toBe("Unknown error");
  });

  it("stops polling after unmount", async () => {
    const fetcher = vi.fn(async () => emptyDashboard());
    const { unmount } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("ignores a response that arrives after unmount", async () => {
    let resolve!: (d: DashboardData) => void;
    const fetcher = vi.fn(() => new Promise<DashboardData>((r) => (resolve = r)));
    const { result, unmount } = renderHook(() => useDashboard({ fetcher }));
    unmount();
    await act(async () => resolve(emptyDashboard()));
    expect(result.current.data).toBeNull(); // no state update, and no React warning
  });
});

describe("useDashboard period and manual refresh", () => {
  it("asks the fetcher for the chosen period, today by default", async () => {
    const fetcher = vi.fn(async () => emptyDashboard());
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    expect(fetcher).toHaveBeenLastCalledWith("today");
    expect(result.current.period).toBe("today");
  });

  it("starts from the period it is given", async () => {
    const fetcher = vi.fn(async () => emptyDashboard());
    renderHook(() => useDashboard({ fetcher, initialPeriod: "7d" }));
    await flush();
    expect(fetcher).toHaveBeenLastCalledWith("7d");
  });

  it("fetches again straight away when the period changes, keeping the old data meanwhile", async () => {
    const first = sampleDashboard();
    let resolveSecond!: (d: DashboardData) => void;
    const fetcher = vi
      .fn<(period: string) => Promise<DashboardData>>()
      .mockResolvedValueOnce(first)
      .mockImplementationOnce(() => new Promise((r) => (resolveSecond = r)));
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();

    act(() => result.current.setPeriod("30d"));
    expect(fetcher).toHaveBeenLastCalledWith("30d");
    expect(result.current.period).toBe("30d");
    expect(result.current.isRefreshing).toBe(true);
    expect(result.current.data).toEqual(first);

    await act(async () => resolveSecond({ ...emptyDashboard(), period: "30d" }));
    expect(result.current.isRefreshing).toBe(false);
    expect(result.current.data?.period).toBe("30d");
  });

  it("ignores a slow answer for a period that is no longer selected", async () => {
    let resolveOld!: (d: DashboardData) => void;
    const fetcher = vi
      .fn<(period: string) => Promise<DashboardData>>()
      .mockImplementationOnce(() => new Promise((r) => (resolveOld = r)))
      .mockResolvedValueOnce({ ...emptyDashboard(), period: "all" });
    const { result } = renderHook(() => useDashboard({ fetcher }));
    act(() => result.current.setPeriod("all"));
    await flush();
    await act(async () => resolveOld({ ...emptyDashboard(), period: "today" }));
    expect(result.current.data?.period).toBe("all");
  });

  it("refresh() fetches immediately and reports that it is refreshing", async () => {
    let resolve!: (d: DashboardData) => void;
    const fetcher = vi
      .fn<(period: string) => Promise<DashboardData>>()
      .mockResolvedValueOnce(emptyDashboard())
      .mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    expect(result.current.isRefreshing).toBe(false);

    act(() => result.current.refresh());
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.isRefreshing).toBe(true);
    await act(async () => resolve(emptyDashboard()));
    expect(result.current.isRefreshing).toBe(false);
  });

  it("does not report a refresh in progress after a failed one", async () => {
    const fetcher = vi
      .fn<(period: string) => Promise<DashboardData>>()
      .mockResolvedValueOnce(emptyDashboard())
      .mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useDashboard({ fetcher }));
    await flush();
    act(() => result.current.refresh());
    await flush();
    expect(result.current).toMatchObject({ isRefreshing: false, error: "boom" });
  });
});
