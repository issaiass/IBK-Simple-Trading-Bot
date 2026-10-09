import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { sampleDashboard } from "@/test/fixtures";
import type { StatusData } from "@/types/dashboard";

import { StatusHeader } from "./status-header";

const NOW = new Date("2026-10-08T17:00:30Z");

const status = (overrides: Partial<StatusData> = {}): StatusData => ({
  ...sampleDashboard().status,
  ...overrides,
});

function renderHeader(props: Partial<React.ComponentProps<typeof StatusHeader>> = {}) {
  return render(
    <StatusHeader
      status={status()}
      lastUpdated={null}
      now={NOW}
      isRefreshing={false}
      onRefresh={() => {}}
      {...props}
    />,
  );
}

describe("StatusHeader", () => {
  it("has the page's single level-one heading", () => {
    renderHeader();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Dashboard");
  });

  it("shows the bot status", () => {
    renderHeader();
    expect(screen.getByText(/bot status/i)).toBeInTheDocument();
    const badge = screen.getByTestId("bot-status");
    expect(badge).toHaveTextContent("ACTIVE");
    expect(badge).toHaveAttribute("data-status", "ACTIVE");
  });

  it.each(["IDLE", "NO_DATA"] as const)("marks %s distinctly from ACTIVE", (value) => {
    renderHeader({ status: status({ bot_status: value }) });
    expect(screen.getByTestId("bot-status")).toHaveAttribute("data-status", value);
  });

  it("explains the market state, so IDLE is not a mystery", () => {
    renderHeader({ status: status({ bot_status: "IDLE", gate: "closed" }) });
    expect(screen.getByTestId("market-state")).toHaveTextContent("Market closed");
  });

  it("shows the last cycle time in Eastern time", () => {
    renderHeader();
    expect(screen.getByText(/last cycle/i)).toBeInTheDocument();
    expect(screen.getByText("12:58 ET")).toBeInTheDocument();
  });

  it("says so plainly when there is no cycle data yet", () => {
    renderHeader({
      status: status({ bot_status: "NO_DATA", last_cycle_at: null, message: "no cycle data yet" }),
    });
    expect(screen.getByText("no cycle data yet")).toBeInTheDocument();
    expect(screen.queryByText(/ ET$/)).not.toBeInTheDocument();
  });

  it("shows how long ago the dashboard itself refreshed", () => {
    renderHeader({ lastUpdated: new Date("2026-10-08T17:00:05Z") });
    expect(screen.getByTestId("updated")).toHaveTextContent("Updated 25s ago");
  });

  it("does not claim an update time before the first load", () => {
    renderHeader();
    expect(screen.queryByTestId("updated")).not.toBeInTheDocument();
  });

  it("announces updates politely to screen readers", () => {
    renderHeader({ lastUpdated: new Date("2026-10-08T17:00:05Z") });
    expect(screen.getByRole("status")).toHaveTextContent(/dashboard updated 13:00 ET/i);
  });
});

describe("staleness", () => {
  it("does not warn about fresh data", () => {
    renderHeader({ lastUpdated: new Date("2026-10-08T17:00:00Z") });
    expect(screen.queryByTestId("stale")).not.toBeInTheDocument();
  });

  it("warns when the data is more than two minutes old", () => {
    renderHeader({ lastUpdated: new Date("2026-10-08T16:57:00Z") });
    expect(screen.getByTestId("stale")).toHaveTextContent(/stale/i);
  });
});

describe("manual refresh", () => {
  it("has a labelled button that asks for a refresh", async () => {
    const onRefresh = vi.fn();
    renderHeader({ onRefresh });
    await userEvent.click(screen.getByRole("button", { name: /refresh now/i }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("is disabled and shows progress while refreshing", () => {
    renderHeader({ isRefreshing: true });
    const button = screen.getByRole("button", { name: /refresh now/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("data-refreshing", "true");
  });
});

describe("header slot", () => {
  it("shows whatever controls the page puts next to the status", () => {
    renderHeader({ controls: <span>period controls</span> });
    expect(screen.getByText("period controls")).toBeInTheDocument();
  });
});
