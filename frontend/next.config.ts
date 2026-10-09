import path from "node:path";

import type { NextConfig } from "next";

/** Where the Python backend (`uv run serve-api`) listens. */
const apiUrl = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

/** `BUILD_TARGET=desktop` builds the static files the Electron app serves (see desktop/). */
const isDesktop = process.env.BUILD_TARGET === "desktop";

const shared: NextConfig = {
  // Without this Turbopack guesses the root from the nearest lockfile, which can be one in a
  // parent folder (e.g. the home directory), and then fails to resolve this app's packages.
  // Next runs from the app directory (via the npm scripts), so the cwd is this app's root.
  turbopack: { root: path.resolve(process.cwd()) },
};

// Web: the browser only ever talks to this app; Next proxies /api/* to the backend,
// so there is no CORS to configure and the backend stays on localhost.
const web: NextConfig = {
  ...shared,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

// Desktop: a static export (rewrites are not supported there). The Electron main process
// serves `out/` and does the /api/* proxying itself, so the page code is identical.
const desktop: NextConfig = {
  ...shared,
  output: "export",
  distDir: "out",
  images: { unoptimized: true },
};

export default isDesktop ? desktop : web;
