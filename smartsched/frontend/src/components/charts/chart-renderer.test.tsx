import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RENDERER_MARK_LIMIT, pickRenderer, useChartRenderer } from "./chart-renderer";

describe("pickRenderer (charts.md §5.6)", () => {
  it("SVG up to 300 marks, canvas above", () => {
    expect(RENDERER_MARK_LIMIT).toBe(300);
    expect(pickRenderer({ marks: 300 })).toBe("svg");
    expect(pickRenderer({ marks: 301 })).toBe("canvas");
  });
  it("SVG on print and on phones, whatever the size", () => {
    expect(pickRenderer({ marks: 4320, print: true })).toBe("svg");
    expect(pickRenderer({ marks: 4320, phone: true })).toBe("svg");
  });
});

describe("useChartRenderer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("switches a large series to SVG on beforeprint and back on afterprint", () => {
    const { result } = renderHook(() => useChartRenderer(1440));
    expect(result.current).toBe("canvas");
    act(() => {
      window.dispatchEvent(new Event("beforeprint"));
    });
    expect(result.current).toBe("svg");
    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(result.current).toBe("canvas");
  });

  it("uses SVG on a phone-width viewport", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("max-width"),
          media: query,
          onchange: null,
          addListener: () => undefined,
          removeListener: () => undefined,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
          dispatchEvent: () => false,
        }) as MediaQueryList,
    );
    const { result } = renderHook(() => useChartRenderer(1440));
    expect(result.current).toBe("svg");
  });
});
