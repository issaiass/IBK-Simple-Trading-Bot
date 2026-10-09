import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function loadRewrites() {
  const { default: nextConfig } = await import("../../next.config");
  return (await nextConfig.rewrites!()) as { source: string; destination: string }[];
}

describe("next.config project root", () => {
  it("pins the Turbopack root to this app, not to a lockfile found in a parent folder", async () => {
    const { default: nextConfig } = await import("../../next.config");
    expect(nextConfig.turbopack?.root).toBe(path.resolve(process.cwd()));
    expect(path.isAbsolute(nextConfig.turbopack!.root!)).toBe(true);
  });
});

describe("next.config rewrites", () => {
  it("proxies /api/* to the Python backend on localhost by default", async () => {
    vi.stubEnv("API_URL", "");
    expect(await loadRewrites()).toEqual([
      { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" },
    ]);
  });

  it("uses API_URL when set, ignoring a trailing slash", async () => {
    vi.stubEnv("API_URL", "http://backend.internal:9000/");
    expect(await loadRewrites()).toEqual([
      { source: "/api/:path*", destination: "http://backend.internal:9000/api/:path*" },
    ]);
  });
});

describe("next.config build target", () => {
  it("is a normal server build by default (web)", async () => {
    vi.stubEnv("BUILD_TARGET", "");
    const { default: nextConfig } = await import("../../next.config");
    expect(nextConfig.output).toBeUndefined();
    expect(nextConfig.rewrites).toBeDefined();
  });

  it("is a static export for the desktop app, which cannot use rewrites", async () => {
    vi.stubEnv("BUILD_TARGET", "desktop");
    const { default: nextConfig } = await import("../../next.config");
    expect(nextConfig.output).toBe("export");
    expect(nextConfig.rewrites).toBeUndefined();
  });

  it("exports to out/, apart from the web .next cache", async () => {
    vi.stubEnv("BUILD_TARGET", "desktop");
    const { default: nextConfig } = await import("../../next.config");
    expect(nextConfig.distDir).toBe("out");
  });
});
