import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PeriodSelect } from "./period-select";

describe("PeriodSelect", () => {
  it("is a labelled group with one choice per period", () => {
    render(<PeriodSelect value="today" onChange={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: /period/i });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual([
      "Today",
      "7 days",
      "30 days",
      "All time",
    ]);
  });

  it("marks only the selected period as checked", () => {
    render(<PeriodSelect value="30d" onChange={() => {}} />);
    expect(screen.getByRole("radio", { name: "30 days" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Today" })).not.toBeChecked();
  });

  it("reports the period the viewer picks", async () => {
    const onChange = vi.fn();
    render(<PeriodSelect value="today" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "7 days" }));
    expect(onChange).toHaveBeenCalledWith("7d");
  });

  it("can be operated from the keyboard", async () => {
    const onChange = vi.fn();
    render(<PeriodSelect value="today" onChange={onChange} />);
    await userEvent.tab();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("7d");
  });

  it("can be disabled while a different period loads", () => {
    render(<PeriodSelect value="today" onChange={() => {}} disabled />);
    expect(screen.getByRole("radio", { name: "All time" })).toBeDisabled();
  });
});
