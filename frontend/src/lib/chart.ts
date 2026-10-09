/** Geometry for the cumulative P&L curve, kept pure so it can be unit-tested. */

export interface ChartBox {
  width: number;
  height: number;
  padding: number;
}

export interface ChartPath {
  /** SVG path for the line. */
  line: string;
  /** The same path closed down to the zero line, for a filled area. */
  area: string;
  /** y coordinate of the zero baseline. */
  zeroY: number;
  /** Where each value landed, in the same coordinates as the paths. */
  points: { x: number; y: number }[];
  /** y coordinate for any value (for axis ticks). */
  yOf: (value: number) => number;
}

const fixed = (n: number): string => n.toFixed(2);

/**
 * Lay `values` out left to right. The vertical range always includes zero, so gains
 * sit above the baseline and losses below it. Returns null if there is no line to draw.
 */
export function buildChartPath(values: number[], box: ChartBox): ChartPath | null {
  if (values.length < 2) return null;

  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const range = high - low;
  const innerWidth = box.width - 2 * box.padding;
  const innerHeight = box.height - 2 * box.padding;

  const y = (value: number): number =>
    range === 0 ? box.padding + innerHeight / 2 : box.padding + ((high - value) / range) * innerHeight;
  const x = (index: number): number => box.padding + (index * innerWidth) / (values.length - 1);

  const points = values.map((value, i) => `${fixed(x(i))},${fixed(y(value))}`);
  const line = `M${points.join(" L")}`;
  const zeroY = y(0);
  const last = values.length - 1;
  const area = `${line} L${fixed(x(last))},${fixed(zeroY)} L${fixed(x(0))},${fixed(zeroY)} Z`;

  const round = (n: number): number => Number(n.toFixed(2));
  return {
    line,
    area,
    zeroY,
    points: values.map((value, i) => ({ x: round(x(i)), y: round(y(value)) })),
    yOf: (value) => round(y(value)),
  };
}

/** 1, 2, 5 or 10 times a power of ten: a step that reads well on an axis. */
function niceStep(raw: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / magnitude;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * magnitude;
}

/** Round axis values within [min, max], always including zero. About `count` of them. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  const low = Math.min(0, min);
  const high = Math.max(0, max);
  if (high === low) return [0];

  const step = niceStep((high - low) / count);
  const ticks: number[] = [];
  for (let value = Math.ceil(low / step) * step; value <= high + step * 1e-9; value += step) {
    ticks.push(Number(value.toFixed(10)) + 0); // + 0 turns -0 into 0
  }
  return ticks;
}

/** The point closest to a horizontal position given as a fraction (0 to 1) of the chart width. */
export function nearestIndex(fraction: number, count: number): number {
  if (count <= 1 || Number.isNaN(fraction)) return 0;
  const clamped = Math.min(1, Math.max(0, fraction));
  return Math.round(clamped * (count - 1));
}
