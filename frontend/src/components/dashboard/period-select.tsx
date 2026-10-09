import { PERIODS } from "@/lib/period";
import type { Period } from "@/types/dashboard";

interface PeriodSelectProps {
  value: Period;
  onChange: (period: Period) => void;
  disabled?: boolean;
}

/**
 * Today / 7 days / 30 days / All time. Native radio buttons underneath, so the browser
 * provides the keyboard behaviour (Tab in, arrow keys to change) and screen-reader semantics.
 */
export function PeriodSelect({ value, onChange, disabled = false }: PeriodSelectProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Period"
      className="inline-flex rounded-full bg-white/[0.04] p-1 ring-1 ring-white/10"
    >
      {PERIODS.map(({ value: option, label }) => (
        <label key={option} className="relative">
          <input
            type="radio"
            name="period"
            value={option}
            checked={value === option}
            disabled={disabled}
            onChange={() => onChange(option)}
            className="peer sr-only"
          />
          <span
            className={
              "block cursor-pointer rounded-full px-3 py-1 text-sm text-zinc-400 transition-colors " +
              "hover:text-zinc-100 peer-checked:bg-emerald-400/15 peer-checked:text-emerald-300 " +
              "peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-400/60 peer-disabled:cursor-wait peer-disabled:opacity-60"
            }
          >
            {label}
          </span>
        </label>
      ))}
    </div>
  );
}
