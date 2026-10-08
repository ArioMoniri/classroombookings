"use client";
import { useSyncExternalStore } from "react";

const QUERY = "(max-width: 640px)";

function subscribe(cb: () => void) {
  if (typeof window === "undefined" || !window.matchMedia) return () => undefined;
  const mq = window.matchMedia(QUERY);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

/** Phones get bottom sheets (liquid-glass.md §15). false during SSR. */
export function useIsPhone(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(QUERY).matches : false),
    () => false,
  );
}
