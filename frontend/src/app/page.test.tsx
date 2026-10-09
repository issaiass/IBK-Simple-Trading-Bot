import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { sampleDashboard } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  fetchDashboard: vi.fn(async () => sampleDashboard()),
}));

import Home from "./page";

describe("Home page", () => {
  it("is the dashboard inside the app shell", async () => {
    render(<Home />);
    await act(async () => {});
    expect(screen.getByRole("navigation", { name: /main/i })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Today's P&L" })).toBeInTheDocument();
  });

  it("no longer shows the create-next-app boilerplate or the placeholder page", async () => {
    render(<Home />);
    await act(async () => {});
    expect(screen.queryByText(/get started by editing/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Paper-trading dashboard")).not.toBeInTheDocument();
  });
});
