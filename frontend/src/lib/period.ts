import type { Period } from "@/types/dashboard";

export const PERIODS: { value: Period; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "all", label: "All time" },
];

const STORAGE_KEY = "dashboard.period";
const DEFAULT_PERIOD: Period = "today";

/** The part of `Storage` we use, so tests can pass a fake. */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const isPeriod = (value: string | null): value is Period => PERIODS.some((p) => p.value === value);

/** The viewer's last choice, or today. Storage can be missing or throw (private windows). */
export function readStoredPeriod(storage: KeyValueStorage | null): Period {
  try {
    const stored = storage?.getItem(STORAGE_KEY) ?? null;
    return isPeriod(stored) ? stored : DEFAULT_PERIOD;
  } catch {
    return DEFAULT_PERIOD;
  }
}

export function storePeriod(period: Period, storage: KeyValueStorage | null): void {
  try {
    storage?.setItem(STORAGE_KEY, period);
  } catch {
    // remembering the choice is a convenience, never a requirement
  }
}

/** `localStorage` if this browser allows touching it at all. */
export function browserStorage(): KeyValueStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
