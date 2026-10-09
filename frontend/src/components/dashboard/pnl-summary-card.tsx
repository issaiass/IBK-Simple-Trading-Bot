import { formatPct, formatPeriodLabel, formatProfitFactor, formatSignedUsd, signOf } from "@/lib/format";
import { signText } from "@/lib/sign";
import { cn } from "@/lib/utils";
import type { Period, SummaryData, TradeHighlight } from "@/types/dashboard";

import { SectionCard } from "./section-card";
import { SignMarker } from "./sign-marker";
import { Stat } from "./stat";

const highlight = (trade: TradeHighlight | null): string =>
  trade ? `${trade.symbol} ${formatSignedUsd(trade.pnl_usd)}` : "—";

export function PnlSummaryCard({ summary, period }: { summary: SummaryData; period: Period }) {
  const sign = signOf(summary.gross_pnl_usd);

  return (
    <SectionCard
      id="overview"
      title={period === "today" ? "Today's P&L" : "P&L"}
      description={<span>{formatPeriodLabel(period, summary)}</span>}
    >
      <p
        data-testid="total-pnl"
        data-sign={sign}
        className={cn("text-4xl font-semibold tracking-tight tabular-nums", signText)}
      >
        <SignMarker sign={sign} />
        {formatSignedUsd(summary.gross_pnl_usd)}
      </p>

      <dl className="mt-5 grid grid-cols-2 gap-2">
        <Stat label="Trades" testId="stat-trades">{summary.total_trades}</Stat>
        <Stat label="Win rate" testId="stat-win-rate">{formatPct(summary.win_rate_pct)}</Stat>
        <Stat label="Wins" testId="stat-wins">{summary.wins}</Stat>
        <Stat label="Losses" testId="stat-losses">{summary.losses}</Stat>
        <Stat label="Profit factor" testId="stat-profit-factor">
          {formatProfitFactor(summary.profit_factor)}
        </Stat>
        <Stat label="Best" testId="stat-best">{highlight(summary.largest_winner)}</Stat>
        <Stat label="Worst" testId="stat-worst" className="col-span-2">
          {highlight(summary.largest_loser)}
        </Stat>
      </dl>
    </SectionCard>
  );
}
