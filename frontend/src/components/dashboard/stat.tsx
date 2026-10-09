import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface StatProps {
  label: string;
  testId: string;
  children: ReactNode;
  className?: string;
}

/** One labelled figure inside a <dl>. */
export function Stat({ label, testId, children, className }: StatProps) {
  return (
    <div data-testid={testId} className={cn("rounded-lg bg-white/[0.04] px-3 py-2", className)}>
      <dt className="text-xs text-zinc-400">{label}</dt>
      <dd className="mt-0.5 text-base font-medium tabular-nums text-zinc-100">{children}</dd>
    </div>
  );
}
