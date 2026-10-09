"use client";

import type { ReactNode } from "react";

import { useActiveSection } from "@/hooks/use-active-section";

import { MobileNav } from "./mobile-nav";
import { NAV_IDS } from "./nav-items";
import { Sidebar } from "./sidebar";

/** Navigation (sidebar on desktop, top bar on phones) plus the page's main region. */
export function AppShell({ children }: { children: ReactNode }) {
  const active = useActiveSection(NAV_IDS);

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <MobileNav active={active} />
      <Sidebar active={active} />
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
    </div>
  );
}
