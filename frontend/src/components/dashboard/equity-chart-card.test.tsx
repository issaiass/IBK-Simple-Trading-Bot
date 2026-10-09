import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { sampleDashboard } from "@/test/fixtures";

import { EquityChartCard } from "./equity-chart-card";

/** jsdom has no PointerEvent, so send a mouse event under the pointer event's name. */
const pointerMove = (target: Element, clientX: number) =>
  fireEvent(target, new MouseEvent("pointermove", { bubbles: true, clientX }));

const points = () => sampleDashboard().equity_curve; // NVDA +1.20 (total 1.20), BBY -7.00 (total -5.80)

describe("EquityChartCard", () => {
  it("is titled as the cumulative P&L", () => {
    render(<EquityChartCard points={points()} period="today" />);
    expect(screen.getByRole("heading", { name: "Cumulative P&L" })).toBeInTheDocument();
  });

  it("says which trades it covers", () => {
    render(<EquityChartCard points={points()} period="7d" />);
    expect(screen.getByText(/closed trades in this period/i)).toBeInTheDocument();
  });

  it("draws the curve as an accessible SVG", () => {
    render(<EquityChartCard points={points()} period="today" />);
    const chart = screen.getByRole("img", { name: /cumulative p&l chart/i });
    expect(chart.tagName.toLowerCase()).toBe("svg");
    expect(chart.querySelector("path[data-testid='equity-line']")!.getAttribute("d")).toMatch(/^M/);
  });

  it("starts the curve from zero, so a single trade still draws a line", () => {
    render(<EquityChartCard points={points().slice(0, 1)} period="today" />);
    expect(screen.getByRole("img", { name: /cumulative p&l chart/i })).toBeInTheDocument();
  });

  it("shows the latest cumulative value with its sign", () => {
    render(<EquityChartCard points={points()} period="today" />);
    const latest = screen.getByTestId("equity-latest");
    expect(latest).toHaveTextContent("-$5.80");
    expect(latest).toHaveAttribute("data-sign", "negative");
  });

  it("explains an empty period instead of drawing nothing", () => {
    render(<EquityChartCard points={[]} period="today" />);
    expect(screen.getByText(/no closed trades in this period/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByTestId("equity-latest")).not.toBeInTheDocument();
  });

  it("labels the vertical axis with round dollar values, including zero", () => {
    render(<EquityChartCard points={points()} period="today" />);
    const ticks = screen.getAllByTestId("y-tick").map((el) => el.textContent);
    expect(ticks).toContain("$0");
    expect(ticks.some((t) => t?.startsWith("-$"))).toBe(true);
  });

  it("labels the horizontal axis with the first and last close time", () => {
    render(<EquityChartCard points={points()} period="today" />);
    expect(screen.getByTestId("x-start")).toHaveTextContent("Oct 8, 12:32");
    expect(screen.getByTestId("x-end")).toHaveTextContent("Oct 8, 13:07");
  });
});

describe("EquityChartCard readout", () => {
  const focusChart = () => screen.getByRole("group", { name: /chart readout/i });

  it("shows the latest trade by default", () => {
    render(<EquityChartCard points={points()} period="today" />);
    expect(screen.getByTestId("readout")).toHaveTextContent("BBY");
    expect(screen.getByTestId("readout")).toHaveTextContent("-$7.00");
    expect(screen.getByTestId("readout")).toHaveTextContent("-$5.80");
  });

  it("steps through the trades with the arrow keys", () => {
    render(<EquityChartCard points={points()} period="today" />);
    fireEvent.keyDown(focusChart(), { key: "ArrowLeft" });
    expect(screen.getByTestId("readout")).toHaveTextContent("NVDA");
    expect(screen.getByTestId("readout")).toHaveTextContent("+$1.20");
    fireEvent.keyDown(focusChart(), { key: "ArrowRight" });
    expect(screen.getByTestId("readout")).toHaveTextContent("BBY");
  });

  it("does not run off either end", () => {
    render(<EquityChartCard points={points()} period="today" />);
    for (let i = 0; i < 5; i++) fireEvent.keyDown(focusChart(), { key: "ArrowLeft" });
    expect(screen.getByTestId("readout")).toHaveTextContent(/start of period/i);
    for (let i = 0; i < 5; i++) fireEvent.keyDown(focusChart(), { key: "ArrowRight" });
    expect(screen.getByTestId("readout")).toHaveTextContent("BBY");
  });

  it("follows the pointer, and goes back to the latest trade when it leaves", () => {
    render(<EquityChartCard points={points()} period="today" />);
    const area = focusChart();
    area.getBoundingClientRect = () => ({ left: 0, width: 152, top: 0, height: 10, right: 152, bottom: 10, x: 0, y: 0, toJSON: () => ({}) }); // 52px label gutter + 100px plot
    pointerMove(area, 102); // the middle of the plot, of 3 points (origin, NVDA, BBY): NVDA
    expect(screen.getByTestId("readout")).toHaveTextContent("NVDA");
    fireEvent.pointerLeave(area);
    expect(screen.getByTestId("readout")).toHaveTextContent("BBY");
  });

  it("describes the starting point honestly", () => {
    render(<EquityChartCard points={points()} period="today" />);
    const area = focusChart();
    area.getBoundingClientRect = () => ({ left: 0, width: 152, top: 0, height: 10, right: 152, bottom: 10, x: 0, y: 0, toJSON: () => ({}) }); // 52px label gutter + 100px plot
    pointerMove(area, 0);
    expect(screen.getByTestId("readout")).toHaveTextContent(/start/i);
  });
});
