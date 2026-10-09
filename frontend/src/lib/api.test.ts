import { afterEach, describe, expect, it, vi } from "vitest";

import { sampleDashboard } from "@/test/fixtures";

import { ApiError, fetchDashboard } from "./api";

function mockFetch(response: Partial<Response> | Error) {
  const fn = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchDashboard", () => {
  it("requests the dashboard endpoint without caching and returns the parsed body", async () => {
    const data = sampleDashboard();
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => data });
    await expect(fetchDashboard()).resolves.toEqual(data);
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard?period=today", { cache: "no-store" });
  });

  it.each(["today", "7d", "30d", "all"] as const)("asks for the %s period", async (period) => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => sampleDashboard() });
    await fetchDashboard(period);
    expect(fetchMock).toHaveBeenCalledWith(`/api/dashboard?period=${period}`, { cache: "no-store" });
  });

  it("throws an ApiError carrying the status when the server answers with an error", async () => {
    mockFetch({ ok: false, status: 500, json: async () => ({ error: "internal server error" }) });
    const failure = fetchDashboard();
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 500, message: "internal server error" });
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    mockFetch({
      ok: false,
      status: 502,
      json: async () => {
        throw new SyntaxError("not json");
      },
    });
    await expect(fetchDashboard()).rejects.toMatchObject({ status: 502, message: "Request failed (502)" });
  });

  it("lets network errors through so the UI can tell the API is unreachable", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    await expect(fetchDashboard()).rejects.toThrow("Failed to fetch");
  });
});
