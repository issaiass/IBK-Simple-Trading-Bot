import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { NAV_ITEMS } from "./nav-items";
import { Sidebar } from "./sidebar";

beforeEach(() => document.documentElement.classList.add("dark"));
afterEach(() => document.documentElement.classList.remove("dark"));

describe("Sidebar", () => {
  it("shows the app name", () => {
    render(<Sidebar />);
    expect(screen.getByText("Trading Bot")).toBeInTheDocument();
  });

  it("is a labelled navigation landmark", () => {
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: /main/i })).toBeInTheDocument();
  });

  it("links to each dashboard section", () => {
    render(<Sidebar />);
    const links = screen.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]);
    expect(links).toEqual([
      ["Overview", "#overview"],
      ["R-multiples", "#r-multiples"],
      ["Positions", "#positions"],
      ["Last cycle", "#cycle"],
      ["Trades", "#trades"],
    ]);
  });

  it("shares its items with the mobile menu", () => {
    expect(NAV_ITEMS.map((i) => i.href)).toEqual(["#overview", "#r-multiples", "#positions", "#cycle", "#trades"]);
  });

  it("marks the first section as current by default", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Trades" })).not.toHaveAttribute("aria-current");
  });

  it("marks whichever section is in view", () => {
    render(<Sidebar active="positions" />);
    expect(screen.getByRole("link", { name: "Positions" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("says this is paper trading, not live", () => {
    render(<Sidebar />);
    expect(screen.getByText(/paper trading/i)).toBeInTheDocument();
  });

  it("holds the theme switch", () => {
    render(<Sidebar />);
    expect(screen.getByRole("button", { name: /switch to light theme/i })).toBeInTheDocument();
  });
});
