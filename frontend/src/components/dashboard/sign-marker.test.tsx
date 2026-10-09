import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SignMarker } from "./sign-marker";

describe("SignMarker", () => {
  it.each([
    ["positive", "▲"],
    ["negative", "▼"],
    ["zero", "–"],
  ] as const)("shows %s as %s", (sign, symbol) => {
    const { container } = render(<SignMarker sign={sign} />);
    expect(container.textContent).toBe(symbol);
  });

  it("shows nothing for an unknown value", () => {
    const { container } = render(<SignMarker sign="unknown" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is decoration only: the number beside it already says the same in words", () => {
    const { container } = render(<SignMarker sign="positive" />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });
});
