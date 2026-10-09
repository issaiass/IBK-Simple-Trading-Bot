import type { Sign } from "@/lib/format";

const SYMBOL: Record<Exclude<Sign, "unknown">, string> = {
  positive: "▲",
  negative: "▼",
  zero: "–",
};

/**
 * A ▲/▼ beside a gain or loss, so the direction does not rely on colour alone. Decoration only:
 * the signed number next to it already says the same in words.
 */
export function SignMarker({ sign }: { sign: Sign }) {
  if (sign === "unknown") return null;
  return (
    <span aria-hidden="true" data-marker className="mr-1 inline-block text-[0.6em] align-middle opacity-80">
      {SYMBOL[sign]}
    </span>
  );
}
