import http from "node:http";
import path from "node:path";

import { _electron as electron, expect, test, type ElectronApplication } from "@playwright/test";

import { sampleDashboard } from "../src/test/fixtures";

/** A stand-in for the Python backend, so the app test needs neither TWS nor `uv`. */
const requests: string[] = [];

function startFakeApi(): Promise<{ url: string; close: () => Promise<void> }> {
  const server = http.createServer((req, res) => {
    requests.push(req.url ?? "");
    res.setHeader("content-type", "application/json");
    res.end(req.url?.startsWith("/api/health") ? '{"status":"ok"}' : JSON.stringify(sampleDashboard()));
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address() as { port: number };
      resolve({
        url: `http://127.0.0.1:${port}`,
        close: () => new Promise((done) => { server.close(() => done()); server.closeAllConnections(); }),
      });
    });
  });
}

// One Electron instance for the whole file (the app enforces a single instance).
test.describe.configure({ mode: "serial" });

let api: Awaited<ReturnType<typeof startFakeApi>>;
let app: ElectronApplication;

test.beforeAll(async () => {
  api = await startFakeApi();
  app = await electron.launch({
    args: ["."],
    cwd: path.resolve(__dirname, ".."),
    env: { ...process.env, API_URL: api.url },
  });
});

test.afterAll(async () => {
  await app?.close();
  await api?.close();
});

test("the desktop window shows the dashboard with data from the API", async () => {
  const window = await app.firstWindow();
  await expect(window.getByText("Today's P&L", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(window.getByText("-$14.88").first()).toBeVisible();
  await expect(window.getByText("ACTIVE")).toBeVisible();
});

test("the page has no access to Node (isolated renderer)", async () => {
  const window = await app.firstWindow();
  expect(await window.evaluate(() => typeof require)).toBe("undefined");
});

test("serves the page from a local http origin and is titled Trading Bot", async () => {
  const window = await app.firstWindow();
  expect(window.url()).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/$/);
  expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getTitle())).toBe("Trading Bot Dashboard");
});

test("choosing a period reaches the API through the desktop app's proxy", async () => {
  const window = await app.firstWindow();
  await window.getByText("30 days", { exact: true }).click();
  await expect.poll(() => requests.at(-1)).toBe("/api/dashboard?period=30d");
});

test("the theme switch works in the desktop window too", async () => {
  const window = await app.firstWindow();
  await window.getByRole("button", { name: /switch to light theme/i }).click();
  await expect(window.locator("html")).not.toHaveClass(/dark/);
  await window.getByRole("button", { name: /switch to dark theme/i }).click();
  await expect(window.locator("html")).toHaveClass(/dark/);
});
