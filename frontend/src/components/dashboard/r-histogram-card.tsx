import { cn } from "@/lib/utils";
import type { RBucket } from "@/types/dashboard";

import { SectionCard } from "./section-card";

/** Buckets that end at or below zero are losses; the rest are gains. */
const bucketSign = (bucket: RBucket): "positive" | "negative" =>
  bucket.upper !== null && bucket.upper <= 0 ? "negative" : "positive";

export function RHistogramCard({ buckets }: { buckets: RBucket[] }) {
  const largest = Math.max(0, ...buckets.map((b) => b.count));
  const isEmpty = largest === 0;

  return (
    <SectionCard
      id="r-multiples"
      title="R-Multiple Distribution"
      description="R = gain divided by the risk taken (entry minus initial stop)."
    >
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-zinc-500">No closed trades in this period</p>
      ) : (
        <ul aria-label="R-multiple distribution" className="flex flex-col gap-2.5">
          {buckets.map((bucket) => (
            <li key={bucket.label} className="grid grid-cols-[6.5rem_1fr_2rem] items-center gap-3 text-sm">
              <span className="slashed-zero font-mono text-xs text-zinc-400">{bucket.label}</span>
              <span className="h-2.5 overflow-hidden rounded-full bg-white/[0.06]">
                <span
                  data-testid="bucket-bar"
                  data-sign={bucketSign(bucket)}
                  className={cn(
                    "block h-full rounded-full transition-[width] duration-500",
                    "data-[sign=positive]:bg-emerald-400 data-[sign=negative]:bg-rose-400",
                  )}
                  style={{ width: `${Math.round((bucket.count / largest) * 100)}%` }}
                />
              </span>
              <span data-testid="bucket-count" className="text-right tabular-nums text-zinc-200">
                {bucket.count}
              </span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
