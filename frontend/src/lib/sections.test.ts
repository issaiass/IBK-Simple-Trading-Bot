import { describe, expect, it } from "vitest";

import { pickActiveSection } from "./sections";

const sections = (...tops: number[]) => tops.map((top, i) => ({ id: `s${i}`, top }));

describe("pickActiveSection", () => {
  it("is the first section at the top of the page", () => {
    expect(pickActiveSection(sections(0, 400, 800), 900, false)).toBe("s0");
  });

  it("is the last section whose top has passed the reading line", () => {
    // reading line = 30% of a 1000 px viewport = 300 px from the top
    expect(pickActiveSection(sections(-900, 250, 700), 1000, false)).toBe("s1");
    expect(pickActiveSection(sections(-900, -300, 299), 1000, false)).toBe("s2");
  });

  it("stays on the previous section until the next one reaches the line", () => {
    expect(pickActiveSection(sections(-500, 301, 900), 1000, false)).toBe("s0");
  });

  it("is the last section when scrolled to the very bottom, even if it never reaches the line", () => {
    expect(pickActiveSection(sections(-1500, -1000, 600), 1000, true)).toBe("s2");
  });

  it("falls back to the first section when none has reached the line", () => {
    expect(pickActiveSection(sections(500, 900), 1000, false)).toBe("s0");
  });

  it("has no section for an empty page", () => {
    expect(pickActiveSection([], 1000, false)).toBeUndefined();
  });
});
