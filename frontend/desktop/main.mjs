import path from "node:path";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, shell } from "electron";

import { ensureBackend } from "./backend.mjs";
import { resolveSettings } from "./config.mjs";
import { createAppServer } from "./static-server.mjs";

const appDir = path.dirname(fileURLToPath(import.meta.url));
const settings = resolveSettings({ env: process.env, isPackaged: app.isPackaged, appDir });

let server = null;
let backend = null;

/** Serve the static export on a free localhost port and return its URL. */
function startServer() {
  server = createAppServer({ root: settings.staticDir, apiUrl: settings.apiUrl });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

function createWindow(url) {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 380,
    backgroundColor: "#030b0c",
    title: "Trading Bot",
    icon: settings.iconPath,
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });

  const origin = new URL(url).origin;
  // The window only ever shows the dashboard: anything else opens in the real browser.
  window.webContents.setWindowOpenHandler(({ url: target }) => {
    void shell.openExternal(target);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, target) => {
    if (new URL(target).origin !== origin) {
      event.preventDefault();
      void shell.openExternal(target);
    }
  });

  void window.loadURL(url);
  return window;
}

async function start() {
  backend = await ensureBackend({ apiUrl: settings.apiUrl, root: settings.root });
  const url = settings.devUrl ?? (await startServer());
  createWindow(url);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const [window] = BrowserWindow.getAllWindows();
    if (window) {
      if (window.isMinimized()) window.restore();
      window.focus();
    }
  });
  app.on("window-all-closed", () => app.quit());
  app.on("will-quit", () => {
    server?.close();
    backend?.stop();
  });
  void app.whenReady().then(start);
}
