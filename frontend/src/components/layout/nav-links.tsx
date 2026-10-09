import { cn } from "@/lib/utils";

import { NAV_IDS, NAV_ITEMS } from "./nav-items";

interface NavLinksProps {
  /** Id of the section in view (no #). */
  active?: string;
  onNavigate?: () => void;
}

/** The section links, shared by the desktop sidebar and the phone menu. */
export function NavLinks({ active = NAV_IDS[0], onNavigate }: NavLinksProps) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV_ITEMS.map(({ label, href, icon: Icon }) => (
        <a
          key={href}
          href={href}
          onClick={onNavigate}
          aria-current={href === `#${active}` ? "page" : undefined}
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-zinc-400 transition-colors",
            "hover:bg-white/5 hover:text-zinc-100",
            "aria-[current=page]:bg-emerald-400/10 aria-[current=page]:text-emerald-300",
          )}
        >
          <Icon aria-hidden className="size-4" />
          {label}
        </a>
      ))}
    </nav>
  );
}
