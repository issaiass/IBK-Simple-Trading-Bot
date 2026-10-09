import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { sampleDashboard } from "@/test/fixtures";
import type { CycleData } from "@/types/dashboard";

import { CycleCard } from "./cycle-card";

const cycle = (overrides: Partial<CycleData> = {}): CycleData => ({ ...sampleDashboard().cycle!, ...overrides });

describe("CycleCard", () => {
  it("is titled and anchored for the sidebar", () => {
    const { container } = render(<CycleCard cycle={cycle()} />);
    expect(screen.getByRole("heading", { name: "Last Cycle" })).toBeInTheDocument();
    expect(container.querySelector("#cycle")).not.toBeNull();
  });

  it("shows when it ran and what the market state was", () => {
    render(<CycleCard cycle={cycle({ gate: "manage_only" })} />);
    expect(screen.getByText("12:58 ET")).toBeInTheDocument();
    expect(screen.getByText("Managing positions only")).toBeInTheDocument();
  });

  it("counts entries and skipped candidates", () => {
    render(<CycleCard cycle={cycle()} />);
    expect(within(screen.getByTestId("cycle-entries")).getByText("1")).toBeInTheDocument();
    expect(within(screen.getByTestId("cycle-skipped")).getByText("2")).toBeInTheDocument();
  });

  it("lists what the bot did", () => {
    render(<CycleCard cycle={cycle()} />);
    expect(screen.getByText("Entered BBY")).toBeInTheDocument();
  });

  it("lets the viewer see why candidates were skipped", async () => {
    render(<CycleCard cycle={cycle()} />);
    await userEvent.click(screen.getByText(/why were 2 candidates skipped/i));
    expect(screen.getByText("AMD")).toBeVisible();
    expect(screen.getByText(/gap too small, relative volume low/)).toBeVisible();
    expect(screen.getByText(/already in position/)).toBeVisible();
  });

  it("says when more were skipped than are listed", () => {
    render(<CycleCard cycle={cycle({ skipped: 25 })} />);
    expect(screen.getByText(/showing 2 of 25/i)).toBeInTheDocument();
  });

  it("is calm and clear when nothing happened", () => {
    render(<CycleCard cycle={cycle({ entries: 0, skipped: 0, skips: [], actions: [], errors: [] })} />);
    expect(screen.getByText(/nothing to do this cycle/i)).toBeInTheDocument();
    expect(screen.queryByText(/skipped/i, { selector: "summary" })).not.toBeInTheDocument();
  });

  it("raises errors as an alert, listed by name", () => {
    render(<CycleCard cycle={cycle({ errors: [{ event: "stop_move_failed", symbol: "BBY" }] })} />);
    const alert = screen.getByTestId("cycle-errors");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("Stop move failed: BBY");
  });

  it("has no alert when there are no errors", () => {
    render(<CycleCard cycle={cycle()} />);
    expect(screen.queryByTestId("cycle-errors")).not.toBeInTheDocument();
  });

  it("explains the empty state before the bot has ever run", () => {
    render(<CycleCard cycle={null} />);
    expect(screen.getByText(/no cycle recorded yet/i)).toBeInTheDocument();
  });
});
