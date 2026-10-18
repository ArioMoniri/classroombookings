import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ChartPatternsToggle } from "./chart-patterns-toggle";
import { readChartPatterns } from "./use-chart-patterns";

beforeEach(() => localStorage.clear());

describe("ChartPatternsToggle (Profil › Grafiklerde desen)", () => {
  it("is off by default and stores the choice per user", () => {
    render(<ChartPatternsToggle userId={7} />);
    const sw = screen.getByRole("switch", { name: "Grafiklerde desen" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/çizgili desen/)).toBeInTheDocument();
    fireEvent.click(sw);
    expect(readChartPatterns(7)).toBe(true);
    expect(readChartPatterns(8)).toBe(false);
    expect(screen.getByRole("switch", { name: "Grafiklerde desen" })).toHaveAttribute("aria-checked", "true");
  });
});
