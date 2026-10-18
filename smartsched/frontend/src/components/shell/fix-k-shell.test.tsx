// FIX-K (orchestrator asks after round 4):
// 1. at a 32 px root (WCAG 1.4.4 test) a 390 px phone has no room for the tab bar's search capsule (E2EB-F02:
//    /analytics/heatmap 469 px wide). A container query in root rem hides it there and shows the top bar's search,
//    the same 22.5rem rule the media query keeps for real large text.
// 2. with the helper sheet open the shell chrome drops its blur (motion.md: shell bar + sheet ≤ 3 surfaces).
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/analytics/heatmap" }));
import { useHelperStore } from "@/components/helper/helper-store";
import { useTintOnlyChrome } from "./blur-budget";

const src = (f: string) => readFileSync(path.join(__dirname, f), "utf8");
const lineOf = (f: string, needle: string) => src(f).split("\n").find((l) => l.includes(needle)) ?? "";

describe("tab bar search at a 32 px root", () => {
  it("the tab bar is a container and its search capsule hides below 22.5rem of root text", () => {
    expect(lineOf("tab-bar.tsx", 'data-slot="tab-bar"')).toContain("@container");
    expect(lineOf("tab-bar.tsx", 'data-testid="open-palette-mobile"')).toContain("@max-[22.5rem]:hidden");
    expect(lineOf("tab-bar.tsx", 'data-testid="open-palette-mobile"')).toContain("max-[22.5rem]:hidden");
  });
  it("the top bar shows its own search in that case", () => {
    expect(lineOf("top-bar.tsx", '<header className="sticky top-0 z-30')).toContain("@container");
    expect(lineOf("top-bar.tsx", 'data-testid="open-palette-narrow"')).toContain("@max-[22.5rem]:inline-flex");
  });
});

function Probe() {
  return <span data-testid="tint">{String(useTintOnlyChrome())}</span>;
}

describe("blur budget with the helper sheet open", () => {
  afterEach(() => act(() => useHelperStore.setState({ open: false })));
  it("the shell chrome is tint-only while the sheet is open, and glass again after", () => {
    render(<Probe />);
    expect(screen.getByTestId("tint")).toHaveTextContent("false");
    act(() => useHelperStore.setState({ open: true }));
    expect(screen.getByTestId("tint")).toHaveTextContent("true");
    act(() => useHelperStore.setState({ open: false }));
    expect(screen.getByTestId("tint")).toHaveTextContent("false");
  });
  it("the tab bar takes the tint-only material too", () => {
    expect(src("tab-bar.tsx")).toContain("TINT_ONLY_OVER_CONTENT");
  });
});
