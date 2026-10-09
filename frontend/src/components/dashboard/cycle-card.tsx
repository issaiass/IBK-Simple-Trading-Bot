import { formatClock, formatGate, describeAction } from "@/lib/format";
import type { CycleData, MarketGate } from "@/types/dashboard";

import { EmptyState } from "./empty-state";
import { SectionCard } from "./section-card";
import { Stat } from "./stat";

export function CycleCard({ cycle }: { cycle: CycleData | null }) {
  if (cycle === null) {
    return (
      <SectionCard id="cycle" title="Last Cycle">
        <EmptyState title="No cycle recorded yet">
          Once the scheduled cycle runs, what it did and why appears here.
        </EmptyState>
      </SectionCard>
    );
  }

  const quiet =
    cycle.entries === 0 && cycle.skipped === 0 && cycle.actions.length === 0 && cycle.errors.length === 0;

  return (
    <SectionCard
      id="cycle"
      title="Last Cycle"
      description={
        <span className="flex flex-wrap items-center gap-x-3">
          <time dateTime={cycle.at} className="tabular-nums">{formatClock(cycle.at)}</time>
          <span>{formatGate(cycle.gate as MarketGate)}</span>
        </span>
      }
    >
      <div className="flex flex-col gap-4">
        {cycle.errors.length > 0 ? (
          <div
            role="alert"
            data-testid="cycle-errors"
            className="rounded-lg bg-rose-400/10 px-3 py-2 text-sm text-rose-300 ring-1 ring-rose-400/25"
          >
            <p className="font-medium">The bot reported problems</p>
            <ul className="mt-1 list-inside list-disc">
              {cycle.errors.map((error, i) => (
                <li key={`${error.event}-${error.symbol}-${i}`}>{describeAction(error)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <dl className="grid grid-cols-2 gap-2 sm:max-w-sm">
          <Stat label="Entries" testId="cycle-entries">{cycle.entries}</Stat>
          <Stat label="Skipped" testId="cycle-skipped">{cycle.skipped}</Stat>
        </dl>

        {quiet ? <p className="text-sm text-zinc-400">Nothing to do this cycle.</p> : null}

        {cycle.actions.length > 0 ? (
          <ul className="flex flex-col gap-1 text-sm text-zinc-200">
            {cycle.actions.map((action, i) => (
              <li key={`${action.event}-${action.symbol}-${i}`}>{describeAction(action)}</li>
            ))}
          </ul>
        ) : null}

        {cycle.skipped > 0 ? <SkippedList cycle={cycle} /> : null}
      </div>
    </SectionCard>
  );
}

function SkippedList({ cycle }: { cycle: CycleData }) {
  const noun = cycle.skipped === 1 ? "candidate" : "candidates";
  return (
    <details className="group rounded-lg bg-white/[0.03] px-3 py-2 text-sm">
      <summary className="cursor-pointer select-none text-zinc-300">
        Why were {cycle.skipped} {noun} skipped?
      </summary>
      <ul className="mt-2 flex flex-col gap-1.5">
        {cycle.skips.map((skip, i) => (
          <li key={`${skip.symbol}-${i}`} className="flex flex-wrap gap-x-2">
            <span className="font-medium text-zinc-100">{skip.symbol}</span>
            <span className="text-zinc-400">{skip.reasons.join(", ") || "no reason recorded"}</span>
          </li>
        ))}
      </ul>
      {cycle.skipped > cycle.skips.length ? (
        <p className="mt-2 text-xs text-zinc-500">
          Showing {cycle.skips.length} of {cycle.skipped}.
        </p>
      ) : null}
    </details>
  );
}
