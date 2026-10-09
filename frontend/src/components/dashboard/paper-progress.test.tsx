import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PaperProgressData } from "@/types/dashboard";

import { PaperProgress } from "./paper-progress";

const progress = (overrides: Partial<PaperProgressData> = {}): PaperProgressData => ({
  paper_mode: true,
  first_trade_date: "2026-10-03",
  days_traded: 6,
  target_days: 14,
  days_remaining: 8,
  reached: false,
  ...overrides,
});

describe("PaperProgress", () => {
  it("shows how many days of the paper run are done", () => {
    render(<PaperProgress progress={progress()} />);
    expect(screen.getByText("Day 6 of 14")).toBeInTheDocument();
    expect(screen.getByText(/8 days to go/)).toBeInTheDocument();
    expect(screen.getByText(/since 2026-10-03/i)).toBeInTheDocument();
  });

  it("exposes the progress to assistive technology", () => {
    render(<PaperProgress progress={progress()} />);
    const bar = screen.getByRole("progressbar", { name: /paper trading run/i });
    expect(bar).toHaveAttribute("aria-valuenow", "6");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "14");
  });

  it("uses the singular for the last day", () => {
    render(<PaperProgress progress={progress({ days_traded: 13, days_remaining: 1 })} />);
    expect(screen.getByText(/1 day to go/)).toBeInTheDocument();
  });

  it("says when the run has not started", () => {
    render(<PaperProgress progress={progress({ first_trade_date: null, days_traded: 0, days_remaining: 14 })} />);
    expect(screen.getByText(/not started/i)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("celebrates quietly once the two weeks are done, and keeps counting", () => {
    render(<PaperProgress progress={progress({ days_traded: 21, days_remaining: 0, reached: true })} />);
    expect(screen.getByText(/two-week paper run complete/i)).toBeInTheDocument();
    expect(screen.getByText(/21 days/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "14"); // never past the max
  });

  it("warns instead of showing a paper run when the bot is on a live account", () => {
    render(<PaperProgress progress={progress({ paper_mode: false })} />);
    expect(screen.getByText(/live account/i)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("is labelled as its own region", () => {
    render(<PaperProgress progress={progress()} />);
    expect(screen.getByRole("region", { name: /paper trading/i })).toBeInTheDocument();
  });
});
