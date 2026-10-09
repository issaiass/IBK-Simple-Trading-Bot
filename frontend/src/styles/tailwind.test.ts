// @vitest-environment node
import { readFileSync } from "node:fs";
import path from "node:path";

import { compile } from "@tailwindcss/node";
import { describe, expect, it } from "vitest";

const appDir = path.resolve(process.cwd(), "src/app");
const globalsCss = readFileSync(path.join(appDir, "globals.css"), "utf8");

/** Compile globals.css with Tailwind itself, then ask it for the given classes. */
async function build(candidates: string[]): Promise<string> {
  const compiler = await compile(globalsCss, { base: appDir, onDependency: () => {} });
  return compiler.build(candidates);
}

describe("Tailwind is wired into the build", () => {
  it("registers the PostCSS plugin Next uses to run Tailwind", () => {
    const config = readFileSync(path.resolve(process.cwd(), "postcss.config.mjs"), "utf8");
    expect(config).toContain("@tailwindcss/postcss");
  });

  it("compiles globals.css: every @import resolves and @apply works", async () => {
    // `@theme inline` resolves the token into the utility, so look for the resolved value
    const css = await build(["bg-background"]);
    expect(css).toContain("background-color: var(--background)");
    expect(css).not.toContain("@apply");
    expect(css).not.toContain("@theme");
    expect(css).not.toContain("@custom-variant");
  });

  it("generates the shadcn design tokens as utilities", async () => {
    const css = await build(["bg-background", "text-muted-foreground", "border-border"]);
    for (const utility of [".bg-background", ".text-muted-foreground", ".border-border"]) {
      expect(css).toContain(utility);
    }
  });

  it("generates the sign-driven colours the dashboard components depend on", async () => {
    const css = await build([
      "data-[sign=positive]:text-emerald-400",
      "data-[sign=negative]:text-rose-400",
      "data-[status=ACTIVE]:bg-emerald-400/15",
    ]);
    expect(css).toContain('[data-sign="positive"]');
    expect(css).toContain('[data-sign="negative"]');
    expect(css).toContain('[data-status="ACTIVE"]');
  });

  it("defines the dark theme the app always uses", async () => {
    const css = await build([]);
    expect(css).toContain(".dark");
  });
});
