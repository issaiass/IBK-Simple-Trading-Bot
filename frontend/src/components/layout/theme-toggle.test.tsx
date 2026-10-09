import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeToggle } from "./theme-toggle";

beforeEach(() => {
  document.documentElement.classList.add("dark");
  localStorage.clear();
});
afterEach(() => {
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "";
  localStorage.clear();
});

describe("ThemeToggle", () => {
  it("offers the other theme", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /switch to light theme/i })).toBeInTheDocument();
  });

  it("switches to light, remembers it, and offers dark next", async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: /switch to light theme/i }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("dashboard.theme")).toBe("light");
    expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
  });

  it("switches back to dark", async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: /switch to light theme/i }));
    await userEvent.click(screen.getByRole("button", { name: /switch to dark theme/i }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("dashboard.theme")).toBe("dark");
  });

  it("starts from the theme the page already has", () => {
    document.documentElement.classList.remove("dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
  });
});
