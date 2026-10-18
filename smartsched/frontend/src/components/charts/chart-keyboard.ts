"use client";
// SmartSched charts (CH-03, docs/design/v3/charts.md §9 "Keyboard"): the plot wrapper is one tab stop; ←/→ move a
// focused bucket, Home/End jump, Esc hides, Enter/Space selects it when the caller passes `onSelect` (CH-08). The tooltip follows at once (ECharts `showTip`); a polite live region
// reads the bucket after 250 ms, so holding an arrow key does not flood the screen reader. Original work.
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ChartColumn } from "./chart-csv";
import type { ChartFormat } from "./chart-format";
import type { ChartApi } from "./chart-form-types";
import type { Translate } from "./chart-summary";

export const LIVE_DEBOUNCE_MS = 250;

/** the next focused bucket, "hide", or null when the key is not ours */
export function keyMove(key: string, current: number | null, count: number): number | "hide" | null {
  if (key === "Escape") return "hide";
  if (count <= 0) return null;
  const last = count - 1;
  switch (key) {
    case "ArrowRight":
      return current == null ? 0 : Math.min(last, current + 1);
    case "ArrowLeft":
      return current == null ? last : Math.max(0, current - 1);
    case "Home":
      return 0;
    case "End":
      return last;
    default:
      return null;
  }
}

/** "14 Ekim Çarşamba: toplam 82.300 token; Sohbet 37.120, Kurallar 45.180" */
export function bucketSentence<R>({ row, columns, f, t, unit, partial }: { row: R; columns: readonly ChartColumn<R>[]; f: ChartFormat; t: Translate; unit?: string; partial?: string }): string {
  const [first, ...rest] = columns;
  if (!first) return "";
  const raw = row[first.key] as unknown;
  let label = first.format ? first.format(row[first.key], row) : first.kind === "date" ? f.dayLong(raw as string) : String(raw ?? "");
  if (partial) label = `${label} ${partial}`;
  const values = rest
    .filter((c) => c.kind === "number" || c.kind === "percent")
    .map((c) => {
      const v = row[c.key] as unknown;
      const n = typeof v === "number" ? v : 0;
      return { c, n, text: c.kind === "percent" ? f.pct(n) : f.num(n) };
    });
  const withUnit = (s: string) => (unit ? `${s} ${unit}` : s);
  if (values.length === 1) return `${label}: ${withUnit(values[0]!.text)}`;
  const sum = values.filter((v) => v.c.kind === "number").reduce((s, v) => s + v.n, 0);
  return `${label}: ${t("charts.kb.total", { value: withUnit(f.num(sum)) })}; ${values.map((v) => `${v.c.label} ${v.text}`).join(", ")}`;
}

export function useChartKeyboard({ count, api, describe, announce, onSelect }: { count: number; api: ChartApi | null; describe: (index: number) => string; announce: (text: string) => void; onSelect?: (index: number) => void }) {
  const [index, setIndex] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLElement>) => {
      // CH-08 / CH-10: Enter or Space opens the focused bucket (a run, a day) when the chart is selectable
      if ((e.key === "Enter" || e.key === " ") && onSelect && index != null) {
        e.preventDefault();
        onSelect(index);
        return;
      }
      const move = keyMove(e.key, index, count);
      if (move == null) return;
      e.preventDefault();
      if (timer.current) clearTimeout(timer.current);
      if (move === "hide") {
        api?.hideTip();
        setIndex(null);
        return;
      }
      setIndex(move);
      api?.showTip(move);
      timer.current = setTimeout(() => announce(describe(move)), LIVE_DEBOUNCE_MS);
    },
    [index, count, api, describe, announce, onSelect],
  );
  // F-CH-2: a key pressed while the chart's chunk is still loading (the 390 touch run focused the plot ~50 ms
  // after it appeared) had no API to call; show the focused bucket as soon as the chart is ready
  const indexRef = useRef(index);
  indexRef.current = index;
  useEffect(() => {
    if (api && indexRef.current != null) api.showTip(indexRef.current);
  }, [api]);
  const onBlur = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    if (index != null) api?.hideTip();
    setIndex(null);
  }, [index, api]);
  return { index, onKeyDown, onBlur };
}
