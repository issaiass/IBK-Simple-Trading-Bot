import type { ReactNode } from "react";

/** A card's "nothing here" message, centred in whatever height the card has. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex h-full min-h-40 flex-col items-center justify-center gap-1 px-4 text-center">
      <p className="text-sm font-medium text-zinc-300">{title}</p>
      {children ? <p className="max-w-sm text-xs text-zinc-500">{children}</p> : null}
    </div>
  );
}
