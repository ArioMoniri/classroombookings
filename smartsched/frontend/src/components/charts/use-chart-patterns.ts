"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §6 "Texture"): the "Grafiklerde desen" preference. Hatch
// patterns (ECharts `aria.decal`) per series, so colour is never the only channel. Per user, default off, stored
// like the Appearance preferences (localStorage, per user id); forced-colors mode turns it on. The profile/settings
// toggle that writes it is CH-03 (charts.md §13.3). Original work.
import { useSyncExternalStore } from "react";
import { useMediaQuery } from "@/components/ui/use-media-query";

const KEY_PREFIX = "smartsched.charts.patterns.";
const EVENT = "smartsched:chart-patterns";
export const FORCED_COLORS = "(forced-colors: active)";

const keyFor = (userId?: string | number | null) => `${KEY_PREFIX}${userId ?? "anon"}`;

export function readChartPatterns(userId?: string | number | null): boolean {
  try {
    return localStorage.getItem(keyFor(userId)) === "1";
  } catch {
    return false;
  }
}

export function setChartPatterns(userId: string | number | null | undefined, on: boolean): void {
  try {
    if (on) localStorage.setItem(keyFor(userId), "1");
    else localStorage.removeItem(keyFor(userId));
  } catch {
    /* storage blocked: the preference stays off */
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** The user's stored choice (default off), or on when the OS forces colours. */
export function useChartPatterns(userId?: string | number | null): boolean {
  const stored = useSyncExternalStore(subscribe, () => readChartPatterns(userId), () => false);
  const forced = useMediaQuery(FORCED_COLORS);
  return stored || forced;
}
