"use client";
import { useSyncExternalStore } from "react";

/** `true` while the media query matches (false on the server and in the hydration pass) */
export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (on) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", on);
      return () => mq.removeEventListener("change", on);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** phones (≤ 767 px): tables become card lists, dialogs become bottom sheets, the wizard rail a top stepper */
export const PHONE = "(max-width: 767px)";
export const usePhone = () => useMedia(PHONE);

/** lists on touch: phones and touch tablets below lg read tables as cards (mobile-b phase 2; 768 rows were 36 px) */
export const TOUCH_LIST = "(max-width: 767px), (pointer: coarse) and (max-width: 1023px)";
export const useTouchList = () => useMedia(TOUCH_LIST);
