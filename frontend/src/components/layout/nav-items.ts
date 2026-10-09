import { Bot, ChartColumnBig, History, LayoutDashboard, ListOrdered, Wallet, type LucideIcon } from "lucide-react";

export interface NavItem {
  label: string;
  /** In-page anchor of the section. */
  href: `#${string}`;
  icon: LucideIcon;
}

/** The dashboard is one page, so the nav is a list of its sections, in page order. */
export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Overview", href: "#overview", icon: LayoutDashboard },
  { label: "R-multiples", href: "#r-multiples", icon: ChartColumnBig },
  { label: "Positions", href: "#positions", icon: Wallet },
  { label: "Last cycle", href: "#cycle", icon: History },
  { label: "Trades", href: "#trades", icon: ListOrdered },
];

export const NAV_IDS = NAV_ITEMS.map((item) => item.href.slice(1));

export const BrandIcon = Bot;
