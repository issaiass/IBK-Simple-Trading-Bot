// Builds the static export the desktop app serves (`out/`). A script rather than an inline
// `BUILD_TARGET=desktop next build`, because that syntax does not work in Windows shells.
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const nextBin = createRequire(import.meta.url).resolve("next/dist/bin/next");

const result = spawnSync(process.execPath, [nextBin, "build"], {
  stdio: "inherit",
  env: { ...process.env, BUILD_TARGET: "desktop" },
});

process.exit(result.status ?? 1);
