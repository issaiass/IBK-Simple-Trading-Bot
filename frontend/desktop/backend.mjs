import { spawn as nodeSpawn } from "node:child_process";

const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_POLL_MS = 500;

async function healthy(apiUrl) {
  try {
    const response = await fetch(`${apiUrl}/api/health`, { signal: AbortSignal.timeout(1500) });
    return response.ok;
  } catch {
    return false;
  }
}

const sleepMs = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Make sure the Python API is answering. A backend that is already up is used as it is and left
 * alone; otherwise `uv run serve-api` is started in the project root, and stopped by `stop()`.
 * Never throws: `ready: false` lets the UI show its usual "is the API running?" message.
 */
export async function ensureBackend({
  apiUrl,
  root,
  probe = healthy,
  spawn = nodeSpawn,
  sleep = sleepMs,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  pollMs = DEFAULT_POLL_MS,
}) {
  if (await probe(apiUrl)) return { started: false, ready: true, stop() {} };
  if (!root) return { started: false, ready: false, stop() {} };

  const child = spawn("uv", ["run", "serve-api"], { cwd: root, stdio: "ignore", windowsHide: true });
  const stop = () => child.kill();

  for (let waited = 0; waited < timeoutMs; waited += pollMs) {
    await sleep(pollMs);
    if (await probe(apiUrl)) return { started: true, ready: true, stop };
  }

  stop();
  return { started: true, ready: false, stop() {} };
}
