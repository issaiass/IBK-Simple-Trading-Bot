import { describe, expect, it } from "vitest";

import { siteConfig } from "./site";

describe("siteConfig", () => {
  it("names the app and its browser title", () => {
    expect(siteConfig.name).toBe("Trading Bot");
    expect(siteConfig.title).toBe("Trading Bot Dashboard");
  });

  it("describes the app for search engines and link previews", () => {
    expect(siteConfig.description.length).toBeGreaterThan(20);
  });
});
