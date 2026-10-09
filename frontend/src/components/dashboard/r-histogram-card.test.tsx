import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { emptyDashboard, sampleDashboard } from "@/test/fixtures";

import { RHistogramCard } from "./r-histogram-card";

describe("RHistogramCard", () => {
  it("is titled as the R-multiple distribution", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    expect(screen.getByRole("heading", { name: "R-Multiple Distribution" })).toBeInTheDocument();
  });

  it("shows one row per bucket with its label and count", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    for (const label of ["≤ -2R", "-2R to -1R", "-1R to 0R", "0R to +1R", "+1R to +2R", "+2R to +3R", "> +3R"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    const counts = screen.getAllByTestId("bucket-count").map((el) => el.textContent);
    expect(counts).toEqual(["0", "1", "4", "2", "1", "0", "0"]);
  });

  it("sizes each bar in proportion to the largest bucket", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    const widths = screen.getAllByTestId("bucket-bar").map((el) => (el as HTMLElement).style.width);
    expect(widths).toEqual(["0%", "25%", "100%", "50%", "25%", "0%", "0%"]);
  });

  it("colours losing buckets differently from winning ones", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    const signs = screen.getAllByTestId("bucket-bar").map((el) => el.getAttribute("data-sign"));
    expect(signs).toEqual([
      "negative", "negative", "negative", "positive", "positive", "positive", "positive",
    ]);
  });

  it("exposes the chart to screen readers as a list", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    expect(screen.getByRole("list", { name: /r-multiple distribution/i })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
  });

  it("shows an empty state instead of empty bars when there are no closed trades", () => {
    render(<RHistogramCard buckets={emptyDashboard().r_histogram} />);
    expect(screen.getByText("No closed trades in this period")).toBeInTheDocument();
    expect(screen.queryAllByTestId("bucket-bar")).toHaveLength(0);
  });

  it("explains what R means", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    expect(screen.getByText(/gain divided by the risk/i)).toBeInTheDocument();
  });

  it("draws zeros with a slash, so 0R is not read as OR", () => {
    render(<RHistogramCard buckets={sampleDashboard().r_histogram} />);
    expect(screen.getByText("0R to +1R")).toHaveClass("slashed-zero");
  });
});
