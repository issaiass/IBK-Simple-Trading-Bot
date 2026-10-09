import path from "node:path";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

/**
 * Where everything lives, from the environment.
 *
 * `appDir` is this `desktop/` folder. Unpackaged, the Python project is the folder above
 * `frontend/`; a packaged exe has no such neighbour, so the project root must be given
 * explicitly (TRADING_BOT_ROOT) or the backend is expected to be running already.
 */
export function resolveSettings({ env, isPackaged, appDir }) {
  const frontendDir = path.resolve(appDir, "..");
  const configuredRoot = env.TRADING_BOT_ROOT;

  let root = null;
  if (configuredRoot) root = path.resolve(configuredRoot);
  else if (!isPackaged) root = path.resolve(frontendDir, "..");

  return {
    apiUrl: (env.API_URL || DEFAULT_API_URL).replace(/\/+$/, ""),
    root,
    staticDir: path.join(frontendDir, "out"),
    devUrl: env.DESKTOP_DEV_URL || null,
    iconPath: path.join(appDir, "assets", "icon.png"),
  };
}
