"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => undefined;

/** false during SSR and hydration, true after — keeps server/client markup identical for cache-fed labels. */
export function useHydrated(): boolean {
  return useSyncExternalStore(subscribe, () => true, () => false);
}
