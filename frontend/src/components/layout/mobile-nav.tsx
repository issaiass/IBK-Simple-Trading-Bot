"use client";

import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import { NavLinks } from "./nav-links";
import { Brand } from "./sidebar";
import { ThemeToggle } from "./theme-toggle";

/** Top bar and drop-down menu for screens too small for the sidebar. */
export function MobileNav({ active }: { active?: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div className="sticky top-0 z-30 border-b border-white/10 bg-background/80 backdrop-blur-xl lg:hidden">
      <div className="flex items-center justify-between px-4 py-2">
        <Brand />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="text-zinc-300"
        >
          {open ? <X aria-hidden /> : <Menu aria-hidden />}
        </Button>
      </div>
      {open ? (
        <div className="flex flex-col gap-3 px-4 pb-4">
          <NavLinks active={active} onNavigate={() => setOpen(false)} />
          <ThemeToggle />
        </div>
      ) : null}
    </div>
  );
}
