import { Badge } from "@/components/ui/badge";
import { siteConfig } from "@/config/site";

import { BrandIcon } from "./nav-items";
import { NavLinks } from "./nav-links";
import { ThemeToggle } from "./theme-toggle";

export function Brand() {
  return (
    <div className="flex items-center gap-3 px-2">
      <span className="grid size-9 place-items-center rounded-xl bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-400/30">
        <BrandIcon aria-hidden className="size-5" />
      </span>
      <div className="flex flex-col gap-1">
        <span className="font-semibold leading-none text-zinc-50">{siteConfig.name}</span>
        <Badge variant="outline" className="h-4 border-white/10 px-1.5 text-[10px] text-zinc-400">
          Paper trading
        </Badge>
      </div>
    </div>
  );
}

/** Desktop navigation. The aside stretches the full page height; its content stays in view. */
export function Sidebar({ active }: { active?: string }) {
  return (
    <aside className="hidden w-60 shrink-0 border-r border-white/10 bg-black/20 backdrop-blur-xl lg:block">
      <div className="sticky top-0 flex h-screen flex-col justify-between gap-8 px-4 py-6">
        <div className="flex flex-col gap-8">
          <Brand />
          <NavLinks active={active} />
        </div>
        <div className="px-2">
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
