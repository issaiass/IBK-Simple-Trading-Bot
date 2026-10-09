import { describe, expect, it } from "vitest";

import { PERIODS, readStoredPeriod, storePeriod } from "./period";

function fakeStorage(initial: Record<string, string> = {}, broken = false) {
  const data = { ...initial };
  return {
    data,
    getItem: (key: string) => {
      if (broken) throw new Error("denied");
      return data[key] ?? null;
    },
    setItem: (key: string, value: string) => {
      if (broken) throw new Error("denied");
      data[key] = value;
    },
  };
}

describe("PERIODS", () => {
  it("lists the four choices in display order, with labels", () => {
    expect(PERIODS).toEqual([
      { value: "today", label: "Today" },
      { value: "7d", label: "7 days" },
      { value: "30d", label: "30 days" },
      { value: "all", label: "All time" },
    ]);
  });
});

describe("period persistence", () => {
  it("defaults to today when nothing is stored", () => {
    expect(readStoredPeriod(fakeStorage())).toBe("today");
  });

  it("restores a stored period", () => {
    const storage = fakeStorage();
    storePeriod("30d", storage);
    expect(readStoredPeriod(storage)).toBe("30d");
  });

  it("ignores a stored value that is not a period", () => {
    expect(readStoredPeriod(fakeStorage({ "dashboard.period": "forever" }))).toBe("today");
  });

  it("works without storage (private window, blocked site data)", () => {
    expect(readStoredPeriod(null)).toBe("today");
    expect(readStoredPeriod(fakeStorage({}, true))).toBe("today");
    expect(() => storePeriod("7d", fakeStorage({}, true))).not.toThrow();
    expect(() => storePeriod("7d", null)).not.toThrow();
  });
});
