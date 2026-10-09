import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3100);
// Next only serves its scripts to the host it was started for; use E2E_HOST=localhost to reuse a `npm run dev` server.
const HOST = process.env.E2E_HOST ?? "127.0.0.1";

/**
 * The browser tests mock `/api/dashboard`, so only the Next dev server is started:
 * they never need the Python backend or TWS.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: `http://${HOST}:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      testIgnore: /desktop-app\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    // The Electron build: needs `npm run desktop:build` first (see the `e2e:desktop` script).
    { name: "desktop-app", testMatch: /desktop-app\.spec\.ts/ },
    {
      name: "phone",
      testMatch: /responsive\.spec\.ts/,
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: {
    command: `npm run dev -- -p ${PORT} -H ${HOST}`,
    url: `http://${HOST}:${PORT}`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
