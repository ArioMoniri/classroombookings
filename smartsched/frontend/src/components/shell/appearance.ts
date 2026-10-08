"use client";
// Accent preset (liquid-glass.md §5.2) as an app preference, stored next to the motion / transparency
// preferences of `components/ui/appearance-preferences.tsx` in `localStorage["smartsched.appearance.<userId>"]`
// (that module spreads unknown keys through, so `accent` survives its writes and vice versa).
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { ACCENT_PRESETS, APPEARANCE_KEY_PREFIX } from "./appearance-init";

export const ACCENTS = ACCENT_PRESETS;
export type Accent = (typeof ACCENTS)[number];

const KEY_PREFIX = APPEARANCE_KEY_PREFIX;
const EVENT = "smartsched:appearance";

const keyFor = (userId?: string | number | null) => `${KEY_PREFIX}${userId ?? "anon"}`;

export function isAccent(v: unknown): v is Accent {
  return typeof v === "string" && (ACCENTS as readonly string[]).includes(v);
}

function readRaw(userId?: string | number | null): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(keyFor(userId));
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export function applyAccent(accent: Accent) {
  const root = document.documentElement;
  if (accent === "blue") delete root.dataset.accent;
  else root.dataset.accent = accent;
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Current user's accent preset; `set` applies it to <html> at once (no colour tween, motion.md §3.1). */
export function useAccentPreference(userId?: string | number | null): { accent: Accent; set: (a: Accent) => void } {
  const accent = useSyncExternalStore(
    subscribe,
    () => {
      const a = readRaw(userId).accent;
      return isAccent(a) ? a : "blue";
    },
    () => "blue" as Accent,
  );
  useEffect(() => {
    applyAccent(accent);
  }, [accent]);
  const set = useCallback(
    (a: Accent) => {
      try {
        localStorage.setItem(keyFor(userId), JSON.stringify({ ...readRaw(userId), accent: a }));
      } catch {
        /* private mode: the attribute still applies for this session */
      }
      applyAccent(a);
      window.dispatchEvent(new Event(EVENT));
    },
    [userId],
  );
  return { accent, set };
}
