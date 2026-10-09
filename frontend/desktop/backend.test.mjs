// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { ensureBackend } from "./backend.mjs";

function setup({ healthy = [], root = "/repo" } = {}) {
  const answers = [...healthy];
  const child = { kill: vi.fn() };
  return {
    child,
    options: {
      apiUrl: "http://127.0.0.1:8000",
      root,
      probe: vi.fn(async () => (answers.length ? answers.shift() : false)),
      spawn: vi.fn(() => child),
      sleep: vi.fn(async () => {}),
      timeoutMs: 1000,
      pollMs: 100,
    },
  };
}

describe("ensureBackend", () => {
  it("uses a backend that is already running and never stops it", async () => {
    const { options, child } = setup({ healthy: [true] });
    const backend = await ensureBackend(options);

    expect(options.spawn).not.toHaveBeenCalled();
    expect(backend).toEqual(expect.objectContaining({ started: false, ready: true }));
    backend.stop();
    expect(child.kill).not.toHaveBeenCalled();
  });

  it("starts `uv run serve-api` in the project root when nothing answers", async () => {
    const { options } = setup({ healthy: [false, false, true] });
    const backend = await ensureBackend(options);

    expect(options.spawn).toHaveBeenCalledWith(
      "uv",
      ["run", "serve-api"],
      expect.objectContaining({ cwd: "/repo" }),
    );
    expect(backend).toEqual(expect.objectContaining({ started: true, ready: true }));
  });

  it("stops only the process it started", async () => {
    const { options, child } = setup({ healthy: [false, true] });
    const backend = await ensureBackend(options);
    backend.stop();
    expect(child.kill).toHaveBeenCalledTimes(1);
  });

  it("reports not ready, and stops the child, when it never becomes healthy", async () => {
    const { options, child } = setup({ healthy: [] });
    const backend = await ensureBackend(options);

    expect(backend.ready).toBe(false);
    expect(child.kill).toHaveBeenCalledTimes(1);
  });

  it("does not try to start anything without a project root", async () => {
    const { options } = setup({ healthy: [false], root: null });
    const backend = await ensureBackend(options);

    expect(options.spawn).not.toHaveBeenCalled();
    expect(backend).toEqual(expect.objectContaining({ started: false, ready: false }));
  });
});
