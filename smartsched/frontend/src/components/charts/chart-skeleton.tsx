"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5.4, §8): the loading state. Bars only, no axes; pulses while
// fetching (free transitions.dev `skeleton-reveal`, chart-card.css) and stays still under reduced motion. Original
// work; replaces EvilCharts' 2 s shimmer and its "Loading" pill (never used: `isLoading` is not passed).
import { useReduce } from "@/lib/motion";
import "./chart-card.css";

const HEIGHTS = [46, 62, 38, 74, 55, 68, 42];

export function ChartSkeleton({ height = 240, testId = "chart-skeleton" }: { height?: number; testId?: string }) {
  const reduce = useReduce();
  return (
    <div aria-hidden data-testid={testId} data-pulse={reduce ? "false" : "true"} className="ch-skel flex w-full items-end gap-2 px-2 pb-6" style={{ height }}>
      {HEIGHTS.map((h, i) => (
        <span key={i} className="flex-1 rounded-sm bg-fill-2" style={{ height: `${h}%` }} />
      ))}
    </div>
  );
}
