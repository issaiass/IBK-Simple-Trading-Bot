import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
};

const PROXIED_HEADERS = ["content-type", "cache-control"];

function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(JSON.stringify(body));
}

/** Resolve a URL path to a file inside `root`, or null if it escapes or is not a file. */
function resolveFile(root, urlPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(urlPath);
  } catch {
    return null;
  }
  const target = path.resolve(root, `.${path.posix.normalize(`/${decoded}`)}`);
  if (target !== root && !target.startsWith(root + path.sep)) return null;

  const candidates = decoded.endsWith("/") || decoded === "" ? [path.join(target, "index.html")] : [target, `${target}.html`];
  return candidates.find((file) => existsSync(file) && statSync(file).isFile()) ?? null;
}

function serveFile(res, file, status = 200, headOnly = false) {
  res.writeHead(status, { "content-type": CONTENT_TYPES[path.extname(file)] ?? "application/octet-stream" });
  if (headOnly) res.end();
  else createReadStream(file).pipe(res);
}

function proxy(req, res, apiUrl) {
  const upstream = new URL(req.url, apiUrl);
  const forward = http.request(
    upstream,
    { method: req.method, headers: { accept: req.headers.accept ?? "*/*" } },
    (response) => {
      const headers = {};
      for (const name of PROXIED_HEADERS) {
        if (response.headers[name]) headers[name] = response.headers[name];
      }
      res.writeHead(response.statusCode ?? 502, headers);
      response.pipe(res);
    },
  );
  forward.on("error", () => sendJson(res, 502, { error: "backend unavailable" }));
  forward.end();
}

/**
 * The desktop app's local server: the static export from `root`, plus `/api/*` forwarded to
 * the Python backend (what `next.config.ts` rewrites do in the web build).
 */
export function createAppServer({ root, apiUrl }) {
  const base = path.resolve(root);

  return http.createServer((req, res) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405, { allow: "GET, HEAD" });
      res.end();
      return;
    }

    const { pathname } = new URL(req.url, "http://localhost");
    if (pathname.startsWith("/api/")) {
      proxy(req, res, apiUrl);
      return;
    }

    const file = resolveFile(base, pathname);
    if (file) {
      serveFile(res, file, 200, req.method === "HEAD");
      return;
    }

    const notFound = path.join(base, "404.html");
    if (existsSync(notFound)) serveFile(res, notFound, 404, req.method === "HEAD");
    else sendJson(res, 404, { error: "not found" });
  });
}
