"use client"
// SmartSched media-query hook for the ui layer (2026-10-16, T-R1-04 / T-R1-05 / T-R1-06). Original work.
// `false` on the server and during hydration, so a component that switches between two layouts renders the same
// markup as the server first (no React #418) and re-renders once the client knows.
import { useSyncExternalStore } from "react"

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => undefined
      const mq = window.matchMedia(query)
      mq.addEventListener("change", cb)
      return () => mq.removeEventListener("change", cb)
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  )
}

/** below Tailwind `md` (768 px): phones and small tablets in portrait */
export const BELOW_MD = "(max-width: 767.98px)"
/** a touch screen without hover (phones, tablets) */
export const COARSE_POINTER = "(pointer: coarse)"
