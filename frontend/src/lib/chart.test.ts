import { describe, expect, it } from "vitest";

import { buildChartPath, nearestIndex, niceTicks } from "./chart";

const box = { width: 100, height: 50, padding: 0 };

describe("buildChartPath", () => {
  it("needs at least two points to draw a line", () => {
    expect(buildChartPath([], box)).toBeNull();
    expect(buildChartPath([5], box)).toBeNull();
  });

  it("maps the lowest value to the bottom and the highest to the top", () => {
    const chart = buildChartPath([0, 10], box)!;
    expect(chart.line).toBe("M0.00,50.00 L100.00,0.00");
  });

  it("spreads points evenly across the width", () => {
    const chart = buildChartPath([0, 5, 10], box)!;
    expect(chart.line).toBe("M0.00,50.00 L50.00,25.00 L100.00,0.00");
  });

  it("always includes zero in the range so gains and losses sit on either side", () => {
    const chart = buildChartPath([-10, 10], box)!;
    expect(chart.zeroY).toBeCloseTo(25);
    expect(chart.line).toBe("M0.00,50.00 L100.00,0.00");
  });

  it("keeps an all-positive series above the zero baseline at the bottom", () => {
    const chart = buildChartPath([5, 10], box)!;
    expect(chart.zeroY).toBeCloseTo(50);
    expect(chart.line.startsWith("M0.00,25.00")).toBe(true);
  });

  it("closes the filled area down to the zero line", () => {
    const chart = buildChartPath([0, 10], box)!;
    expect(chart.area).toBe("M0.00,50.00 L100.00,0.00 L100.00,50.00 L0.00,50.00 Z");
  });

  it("does not divide by zero when every value is zero", () => {
    const chart = buildChartPath([0, 0, 0], box)!;
    expect(chart.line).not.toContain("NaN");
    expect(chart.zeroY).toBeCloseTo(25);
  });

  it("respects the padding", () => {
    const chart = buildChartPath([0, 10], { width: 100, height: 50, padding: 10 })!;
    expect(chart.line).toBe("M10.00,40.00 L90.00,10.00");
  });
});

describe("chart points", () => {
  it("exposes each value's coordinates for markers and tooltips", () => {
    const chart = buildChartPath([0, 5, 10], box)!;
    expect(chart.points).toEqual([
      { x: 0, y: 50 },
      { x: 50, y: 25 },
      { x: 100, y: 0 },
    ]);
  });

  it("gives y coordinates for axis ticks", () => {
    const chart = buildChartPath([0, 10], box)!;
    expect(chart.yOf(0)).toBe(50);
    expect(chart.yOf(10)).toBe(0);
    expect(chart.yOf(5)).toBe(25);
  });
});

describe("niceTicks", () => {
  it("picks round values inside the range", () => {
    expect(niceTicks(-14.88, 1.2)).toEqual([-10, -5, 0]);
  });

  it("always includes zero", () => {
    expect(niceTicks(3, 47)).toContain(0);
  });

  it("copes with a flat range", () => {
    expect(niceTicks(0, 0)).toEqual([0]);
  });

  it("handles big numbers", () => {
    expect(niceTicks(0, 4300)).toEqual([0, 1000, 2000, 3000, 4000]);
  });
});

describe("nearestIndex", () => {
  it("maps a horizontal position (0..1) to the closest point", () => {
    expect(nearestIndex(0, 5)).toBe(0);
    expect(nearestIndex(1, 5)).toBe(4);
    expect(nearestIndex(0.49, 5)).toBe(2);
    expect(nearestIndex(0.13, 5)).toBe(1);
  });

  it("clamps positions outside the chart", () => {
    expect(nearestIndex(-3, 5)).toBe(0);
    expect(nearestIndex(9, 5)).toBe(4);
  });

  it("is zero when the position is not a number", () => {
    expect(nearestIndex(NaN, 5)).toBe(0);
  });

  it("is zero for an empty or single-point series", () => {
    expect(nearestIndex(0.7, 0)).toBe(0);
    expect(nearestIndex(0.7, 1)).toBe(0);
  });
});
