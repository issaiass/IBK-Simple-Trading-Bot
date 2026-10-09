import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MobileNav } from "./mobile-nav";

describe("MobileNav", () => {
  it("shows the app name and a menu button, with the menu closed", () => {
    render(<MobileNav />);
    expect(screen.getByText("Trading Bot")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: /menu/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: /main/i })).not.toBeInTheDocument();
  });

  it("opens a navigation with every section link", async () => {
    render(<MobileNav />);
    await userEvent.click(screen.getByRole("button", { name: /menu/i }));
    expect(screen.getByRole("button", { name: /close menu/i })).toHaveAttribute("aria-expanded", "true");
    const nav = screen.getByRole("navigation", { name: /main/i });
    expect(nav).toBeInTheDocument();
    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "#overview", "#r-multiples", "#positions", "#cycle", "#trades",
    ]);
  });

  it("closes after a link is chosen", async () => {
    render(<MobileNav />);
    await userEvent.click(screen.getByRole("button", { name: /menu/i }));
    await userEvent.click(screen.getByRole("link", { name: "Trades" }));
    expect(screen.queryByRole("navigation", { name: /main/i })).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    render(<MobileNav />);
    await userEvent.click(screen.getByRole("button", { name: /menu/i }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("navigation", { name: /main/i })).not.toBeInTheDocument();
  });

  it("marks the current section", async () => {
    render(<MobileNav active="trades" />);
    await userEvent.click(screen.getByRole("button", { name: /menu/i }));
    expect(screen.getByRole("link", { name: "Trades" })).toHaveAttribute("aria-current", "page");
  });
});
