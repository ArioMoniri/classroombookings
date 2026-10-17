"use client";
import { useSyncExternalStore } from "react";

const PHONE = "(max-width: 640px)";
/** below the `lg` breakpoint: the shell shows the tab bar and the toolbars fold their filters into a sheet */
const COMPACT = "(max-width: 1023.98px)";

function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => undefined;
      const mq = window.matchMedia(query);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  );
}

/** Phones get bottom sheets (liquid-glass.md §15). false during SSR. */
export function useIsPhone(): boolean {
  return useMediaQuery(PHONE);
}

/** Phones and tablets (< 1024 px): one compact toolbar row, the rest in a "Filters" sheet. false during SSR. */
export function useIsCompact(): boolean {
  return useMediaQuery(COMPACT);
}
