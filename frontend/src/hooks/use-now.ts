"use client";

import { useEffect, useState } from "react";

/** The current time, re-read every `intervalMs`, so "3m ago" labels keep moving. */
export function useNow(intervalMs = 15_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
