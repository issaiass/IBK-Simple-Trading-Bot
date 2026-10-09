import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emptyDashboard, sampleDashboard } from "@/test/fixtures";
import type { DashboardData } from "@/types/dashboard";

import { DashboardView } from "./dashboard-view";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-08T17:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

const flush = () => act(async () => {});

describe("DashboardView", () => {
  it("shows a loading skeleton before the first data arrives", () => {
    render(<DashboardView fetcher={() => new Promise<DashboardData>(() => {})} />);
    expect(screen.getByTestId("dashboard-skeleton")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Today's P&L" })).not.toBeInTheDocument();
  });

  it("shows all the cards once data arrives", async () => {
    render(<DashboardView fetcher={async () => sampleDashboard()} />);
    await flush();
    expect(screen.queryByTestId("dashboard-skeleton")).not.toBeInTheDocument();
    for (const name of ["Today's P&L", "Cumulative P&L", "R-Multiple Distribution", "Open Positions", "Last Cycle", "Recent Closed Trades"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
  });

  it("shows the bot status in the header", async () => {
    render(<DashboardView fetcher={async () => sampleDashboard()} />);
    await flush();
    expect(screen.getByTestId("bot-status")).toHaveTextContent("ACTIVE");
  });

  it("gives each section an anchor the sidebar can link to", async () => {
    const { container } = render(<DashboardView fetcher={async () => sampleDashboard()} />);
    await flush();
    for (const id of ["overview", "r-multiples", "positions", "cycle", "trades"]) {
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("feeds each card its own slice of the data", async () => {
    render(<DashboardView fetcher={async () => sampleDashboard()} />);
    await flush();
    expect(screen.getByTestId("total-pnl")).toHaveTextContent("-$14.88");
    expect(screen.getByRole("row", { name: /BBY.*\+0\.52R/ })).toBeInTheDocument();
  });

  it("works with a brand-new, empty bot", async () => {
    render(<DashboardView fetcher={async () => emptyDashboard()} />);
    await flush();
    expect(screen.getByText("no cycle data yet")).toBeInTheDocument();
    expect(screen.getByText("No open positions")).toBeInTheDocument();
    expect(screen.getAllByText("No closed trades in this period").length).toBeGreaterThan(0);
    expect(screen.getByText(/no cycle recorded yet/i)).toBeInTheDocument();
  });

  it("shows an error, with a way to tell what happened, when the API is down at first load", async () => {
    render(
      <DashboardView
        fetcher={async () => {
          throw new Error("Failed to fetch");
        }}
      />,
    );
    await flush();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/couldn't load the dashboard/i);
    expect(alert).toHaveTextContent("Failed to fetch");
    expect(screen.queryByTestId("dashboard-skeleton")).not.toBeInTheDocument();
  });

  it("keeps showing the last data, with a stale warning, when a refresh fails", async () => {
    const fetcher = vi
      .fn<() => Promise<DashboardData>>()
      .mockResolvedValueOnce(sampleDashboard())
      .mockRejectedValueOnce(new Error("boom"));
    render(<DashboardView fetcher={fetcher} />);
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(screen.getByTestId("total-pnl")).toBeInTheDocument();
    expect(within(screen.getByRole("alert")).getByText(/showing the last data/i)).toBeInTheDocument();
  });

  it("shows warnings the API reports", async () => {
    const data = { ...sampleDashboard(), warnings: ["live prices unavailable: yahoo down"] };
    render(<DashboardView fetcher={async () => data} />);
    await flush();
    expect(screen.getByText("live prices unavailable: yahoo down")).toBeInTheDocument();
  });

  it("refreshes itself on the interval", async () => {
    const fetcher = vi.fn(async () => sampleDashboard());
    render(<DashboardView fetcher={fetcher} intervalMs={30_000} />);
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("shows the market state next to the bot status", async () => {
    render(<DashboardView fetcher={async () => sampleDashboard()} />);
    await flush();
    expect(screen.getByTestId("market-state")).toHaveTextContent("Scanning for entries");
  });
});

describe("DashboardView period", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("starts on today and offers the other periods", async () => {
    const fetcher = vi.fn(async () => sampleDashboard());
    render(<DashboardView fetcher={fetcher} />);
    await flush();
    expect(fetcher).toHaveBeenCalledWith("today");
    expect(screen.getByRole("radio", { name: "Today" })).toBeChecked();
  });

  it("reloads every section for the period the viewer picks", async () => {
    vi.useRealTimers();
    const fetcher = vi.fn(async (period?: string) => ({ ...sampleDashboard(), period: period as "7d" }));
    render(<DashboardView fetcher={fetcher} />);
    await screen.findByTestId("total-pnl");
    await userEvent.click(screen.getByRole("radio", { name: "7 days" }));
    expect(fetcher).toHaveBeenLastCalledWith("7d");
    expect(screen.getByRole("radio", { name: "7 days" })).toBeChecked();
  });

  it("remembers the choice for next time", async () => {
    vi.useRealTimers();
    render(<DashboardView fetcher={async () => sampleDashboard()} />);
    await screen.findByTestId("total-pnl");
    await userEvent.click(screen.getByRole("radio", { name: "30 days" }));
    expect(localStorage.getItem("dashboard.period")).toBe("30d");
  });

  it("opens on the remembered period", async () => {
    localStorage.setItem("dashboard.period", "all");
    const fetcher = vi.fn(async () => sampleDashboard());
    render(<DashboardView fetcher={fetcher} />);
    await flush();
    expect(fetcher).toHaveBeenCalledWith("all");
    expect(screen.getByRole("radio", { name: "All time" })).toBeChecked();
  });
});

describe("DashboardView refresh", () => {
  it("refreshes straight away when the viewer asks", async () => {
    const fetcher = vi.fn(async () => sampleDashboard());
    render(<DashboardView fetcher={fetcher} />);
    await flush();
    await act(async () => {
      screen.getByRole("button", { name: /refresh now/i }).click();
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("warns when the data has gone stale", async () => {
    const fetcher = vi.fn(async () => sampleDashboard());
    render(<DashboardView fetcher={fetcher} intervalMs={10 * 60_000} />);
    await flush();
    expect(screen.queryByTestId("stale")).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3 * 60_000);
    });
    expect(screen.getByTestId("stale")).toBeInTheDocument();
  });
});
