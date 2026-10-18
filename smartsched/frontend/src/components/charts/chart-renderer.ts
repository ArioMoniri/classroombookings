"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5.6): SVG for ≤ 300 marks, on phones and on print (crisp,
// low memory, a real vector download); canvas above that (ops minute series). Original work.
import { useEffect, useState } from "react";
import { BELOW_MD, useMediaQuery } from "@/components/ui/use-media-query";

export type ChartRenderer = "svg" | "canvas";

export const RENDERER_MARK_LIMIT = 300;

export function pickRenderer({ marks, print = false, phone = false }: { marks: number; print?: boolean; phone?: boolean }): ChartRenderer {
  return print || phone || marks <= RENDERER_MARK_LIMIT ? "svg" : "canvas";
}

/** true between `beforeprint` and `afterprint` (and while `print` media matches) */
export function usePrinting(): boolean {
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    const on = () => setPrinting(true);
    const off = () => setPrinting(false);
    window.addEventListener("beforeprint", on);
    window.addEventListener("afterprint", off);
    const mql = window.matchMedia?.("print");
    const change = (e: MediaQueryListEvent) => setPrinting(e.matches);
    mql?.addEventListener?.("change", change);
    return () => {
      window.removeEventListener("beforeprint", on);
      window.removeEventListener("afterprint", off);
      mql?.removeEventListener?.("change", change);
    };
  }, []);
  return printing;
}

export function useChartRenderer(marks: number): ChartRenderer {
  const phone = useMediaQuery(BELOW_MD);
  const print = usePrinting();
  return pickRenderer({ marks, print, phone });
}
