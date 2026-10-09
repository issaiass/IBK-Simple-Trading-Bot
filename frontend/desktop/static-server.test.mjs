// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { createAppServer } from "./static-server.mjs";

const listen = (server) =>
  new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
const close = (server) =>
  new Promise((resolve) => {
    server.close(resolve);
    server.closeAllConnections();
  });

let root;
let outer;
let upstream;
let upstreamHits;
let base;

beforeEach(async () => {
  root = mkdtempSync(path.join(tmpdir(), "app-"));
  writeFileSync(path.join(root, "index.html"), "<h1>home</h1>");
  writeFileSync(path.join(root, "404.html"), "<h1>missing</h1>");
  mkdirSync(path.join(root, "_next"));
  writeFileSync(path.join(root, "_next", "app.js"), "console.log(1)");

  upstreamHits = [];
  upstream = http.createServer((req, res) => {
    upstreamHits.push({ method: req.method, url: req.url });
    res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    res.end('{"ok":true}');
  });
  const upstreamPort = await listen(upstream);
  outer = createAppServer({ root, apiUrl: `http://127.0.0.1:${upstreamPort}` });
  base = `http://127.0.0.1:${await listen(outer)}`;
});

afterEach(async () => {
  await close(outer);
  await close(upstream);
  rmSync(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
});

describe("static files", () => {
  it("serves index.html at /", async () => {
    const res = await fetch(`${base}/`);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    expect(await res.text()).toBe("<h1>home</h1>");
  });

  it("serves assets with the right content type", async () => {
    const res = await fetch(`${base}/_next/app.js`);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("javascript");
    await res.text();
  });

  it("answers an unknown path with 404.html and status 404", async () => {
    const res = await fetch(`${base}/nope`);
    expect(res.status).toBe(404);
    expect(await res.text()).toBe("<h1>missing</h1>");
  });

  it("never serves files outside the root", async () => {
    writeFileSync(path.join(root, "..", "outside-secret.txt"), "nope");
    const res = await fetch(`${base}/..%2foutside-secret.txt`);
    await res.text();
    expect(res.status).toBe(404);
    rmSync(path.join(root, "..", "outside-secret.txt"), { force: true });
  });

  it("only answers GET and HEAD", async () => {
    const res = await fetch(`${base}/`, { method: "POST" });
    expect(res.status).toBe(405);
  });
});

describe("API proxy", () => {
  it("forwards /api/* to the backend with the query string", async () => {
    const res = await fetch(`${base}/api/dashboard?x=1`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(upstreamHits).toEqual([{ method: "GET", url: "/api/dashboard?x=1" }]);
  });

  it("answers 502 JSON when the backend is down", async () => {
    await close(upstream);
    upstream = http.createServer();
    const res = await fetch(`${base}/api/dashboard`);
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "backend unavailable" });
  });

  it("does not proxy anything outside /api/", async () => {
    await (await fetch(`${base}/other`)).text();
    expect(upstreamHits).toEqual([]);
  });
});
