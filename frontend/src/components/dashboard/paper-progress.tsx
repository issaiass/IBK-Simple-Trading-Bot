import { FlaskConical, TriangleAlert } from "lucide-react";

import type { PaperProgressData } from "@/types/dashboard";

interface PaperProgressProps {
  progress: PaperProgressData;
}

/** How far the paper run is toward the recommended two weeks, or a warning when the bot is not on paper. */
export function PaperProgress({ progress }: PaperProgressProps) {
  const { paper_mode, first_trade_date, days_traded, target_days, days_remaining, reached } = progress;

  if (!paper_mode) {
    return (
      <section
        aria-label="Paper trading"
        className="flex items-center gap-3 rounded-xl bg-rose-400/10 px-4 py-3 text-sm text-rose-200 ring-1 ring-rose-400/25"
      >
        <TriangleAlert aria-hidden className="size-4 shrink-0" />
        <p>
          <span className="font-medium">This bot is configured for a live account.</span> The paper-run tracker is
          hidden.
        </p>
      </section>
    );
  }

  const shown = Math.min(days_traded, target_days);
  const title = reached
    ? "Two-week paper run complete"
    : first_trade_date
      ? `Day ${days_traded} of ${target_days}`
      : "Paper run not started";
  const note = reached
    ? `${days_traded} days of paper history`
    : first_trade_date
      ? `${days_remaining} ${days_remaining === 1 ? "day" : "days"} to go`
      : "No trades recorded yet";

  return (
    <section
      aria-label="Paper trading"
      className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl bg-white/[0.04] px-4 py-3 text-sm ring-1 ring-white/10"
    >
      <span className="flex items-center gap-2 font-medium text-zinc-100">
        <FlaskConical aria-hidden className="size-4 text-zinc-400" />
        {title}
      </span>

      <div
        role="progressbar"
        aria-label="Paper trading run"
        aria-valuemin={0}
        aria-valuemax={target_days}
        aria-valuenow={shown}
        className="h-1.5 min-w-32 flex-1 overflow-hidden rounded-full bg-white/10"
      >
        <div
          data-reached={reached}
          className="h-full rounded-full bg-sky-400 transition-[width] data-[reached=true]:bg-emerald-400"
          style={{ width: `${(shown / target_days) * 100}%` }}
        />
      </div>

      <span className="text-zinc-400">
        {note}
        {first_trade_date && !reached ? ` · since ${first_trade_date}` : ""}
      </span>
    </section>
  );
}
