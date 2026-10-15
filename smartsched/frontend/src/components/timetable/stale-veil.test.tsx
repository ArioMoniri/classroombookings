import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StaleVeil, useDeferredView } from "./stale-veil";

function Probe({ week, day }: { week: number; day: number }) {
  const v = useDeferredView(week, day);
  return <p data-testid="view">{`${v.week}:${v.day}:${v.stale}`}</p>;
}

describe("StaleVeil (motion audit T2)", () => {
  it("dims only while stale, after a 120 ms delay, opacity only, decorative", () => {
    const { rerender } = render(<StaleVeil stale={false} />);
    const veil = screen.getByTestId("stale-veil");
    expect(veil).not.toHaveAttribute("data-stale");
    expect(veil).toHaveAttribute("aria-hidden", "true");
    expect(veil.className).toContain("pointer-events-none");
    expect(veil.className).toContain("data-stale:delay-[120ms]");
    expect(veil.className).not.toMatch(/translate|scale|blur/);
    rerender(<StaleVeil stale />);
    expect(veil).toHaveAttribute("data-stale", "");
  });

  it("useDeferredView settles on the latest week / day and is not stale once committed", () => {
    const { rerender } = render(<Probe week={3} day={2} />);
    expect(screen.getByTestId("view")).toHaveTextContent("3:2:false");
    rerender(<Probe week={4} day={1} />);
    expect(screen.getByTestId("view")).toHaveTextContent("4:1:false");
  });
});
