import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BRAND_COLORS, Logo } from "./index";

describe("Logo", () => {
  it("has the accessible name SmartSched by default", () => {
    render(<Logo />);
    expect(screen.getByRole("img", { name: "SmartSched" })).toBeInTheDocument();
  });

  it.each(["mark", "tile", "wordmark", "lockup"] as const)("renders the %s variant at the requested height", (variant) => {
    render(<Logo variant={variant} size={40} />);
    const svg = screen.getByRole("img", { name: "SmartSched" });
    expect(svg).toHaveAttribute("height", "40");
    expect(svg).toHaveAttribute("data-variant", variant);
    expect(svg.querySelector("text")).toBeNull(); // outlined, no font dependency
  });

  it("keeps the lockup and wordmark aspect ratio", () => {
    render(<Logo variant="lockup" size={192} />);
    const w = Number(screen.getByRole("img").getAttribute("width"));
    expect(w).toBeGreaterThan(900);
    expect(w).toBeLessThan(1100);
  });

  it("switches to the gapless small cut below 48 px unless told otherwise", () => {
    const { rerender } = render(<Logo size={24} />);
    expect(screen.getByRole("img")).toHaveAttribute("data-cut", "small");
    rerender(<Logo size={64} />);
    expect(screen.getByRole("img")).toHaveAttribute("data-cut", "regular");
    rerender(<Logo size={24} cut="regular" />);
    expect(screen.getByRole("img")).toHaveAttribute("data-cut", "regular");
  });

  it("uses fixed brand colours for light and dark, and currentColor for mono", () => {
    const { container, rerender } = render(<Logo theme="light" />);
    let fills = [...container.querySelectorAll("path")].map((p) => p.getAttribute("fill"));
    expect(fills).toEqual([BRAND_COLORS.blue, BRAND_COLORS.navy]);
    rerender(<Logo theme="dark" />);
    fills = [...container.querySelectorAll("path")].map((p) => p.getAttribute("fill"));
    expect(fills).toEqual([BRAND_COLORS.blueDark, BRAND_COLORS.skyDark]);
    rerender(<Logo theme="mono" variant="lockup" />);
    fills = [...container.querySelectorAll("path")].map((p) => p.getAttribute("fill"));
    expect(new Set(fills)).toEqual(new Set(["currentColor"]));
  });

  it("follows the .dark class through classes in auto theme", () => {
    const { container } = render(<Logo />);
    const first = container.querySelector("path");
    expect(first).not.toHaveAttribute("fill");
    expect(first?.getAttribute("class")).toContain("dark:fill-[#4DA0FF]");
  });

  it("can be decorative when visible text already names it", () => {
    const { container } = render(<Logo decorative />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("accepts a localised label", () => {
    render(<Logo label="SmartSched ana sayfa" />);
    expect(screen.getByRole("img", { name: "SmartSched ana sayfa" })).toBeInTheDocument();
  });
});
