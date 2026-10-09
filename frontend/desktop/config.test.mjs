// @vitest-environment node
import { existsSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { resolveSettings } from "./config.mjs";

const appDir = path.resolve("/app/frontend/desktop");

describe("resolveSettings", () => {
  it("defaults to the local backend and, unpackaged, the repo root next to frontend/", () => {
    const s = resolveSettings({ env: {}, isPackaged: false, appDir });
    expect(s.apiUrl).toBe("http://127.0.0.1:8000");
    expect(s.root).toBe(path.resolve("/app"));
    expect(s.staticDir).toBe(path.resolve("/app/frontend/out"));
    expect(s.devUrl).toBeNull();
  });

  it("takes the backend address and project root from the environment", () => {
    const s = resolveSettings({
      env: { API_URL: "http://10.0.0.5:9000/", TRADING_BOT_ROOT: "/data/bot" },
      isPackaged: false,
      appDir,
    });
    expect(s.apiUrl).toBe("http://10.0.0.5:9000");
    expect(s.root).toBe(path.resolve("/data/bot"));
  });

  it("does not guess a project root when packaged: the bot lives outside the exe", () => {
    const s = resolveSettings({ env: {}, isPackaged: true, appDir });
    expect(s.root).toBeNull();
  });

  it("loads a dev server instead of the built files when DESKTOP_DEV_URL is set", () => {
    const s = resolveSettings({
      env: { DESKTOP_DEV_URL: "http://127.0.0.1:3000" },
      isPackaged: false,
      appDir,
    });
    expect(s.devUrl).toBe("http://127.0.0.1:3000");
  });

  it("points at the window icon, and the icon exists", () => {
    const real = path.resolve(import.meta.dirname);
    const s = resolveSettings({ env: {}, isPackaged: false, appDir: real });
    expect(s.iconPath).toBe(path.join(real, "assets", "icon.png"));
    expect(existsSync(s.iconPath)).toBe(true);
  });
});
