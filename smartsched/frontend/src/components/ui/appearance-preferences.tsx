"use client"
// SmartSched Liquid Glass v2 — in-app Appearance preferences. Original work (docs/design/v2/liquid-glass.md §8,
// motion.md §5). `prefers-reduced-transparency` only exists in Chromium, and some users want less motion in
// this app without changing the OS, so both are app preferences too:
//   <html data-motion="reduced">        → globals.css zeroes CSS transitions/animations + spring durations;
//                                          <AppearanceMotionConfig> makes motion/react skip transform/layout.
//   <html data-transparency="reduced">  → every --mat-* resolves to its solid value, no backdrop-filter.
// Stored per user in localStorage ("smartsched.appearance.<userId>"); "system" defers to the OS query.
//
// Wiring (owned by the shell / settings agents, outside components/ui):
//   1. layout.tsx <head>: <script dangerouslySetInnerHTML={{ __html: appearanceInitScript }} /> (no flash)
//   2. providers.tsx: wrap children in <AppearanceMotionConfig> (inside the existing providers)
//   3. settings → Appearance: <AppearancePreferencesControl userId={me.id} labels={…} />
import * as React from "react"
import { MotionConfig } from "motion/react"

import { Switch } from "@/components/ui/switch"
import { springs } from "@/lib/motion"

export type AppearancePrefs = { motion: "system" | "reduced"; transparency: "system" | "reduced" }
const DEFAULTS: AppearancePrefs = { motion: "system", transparency: "system" }
const KEY_PREFIX = "smartsched.appearance."
const LAST_USER_KEY = "smartsched.appearance.lastUser"
const EVENT = "smartsched:appearance"

const keyFor = (userId?: string | number | null) => `${KEY_PREFIX}${userId ?? "anon"}`

function read(userId?: string | number | null): AppearancePrefs {
  try {
    const raw = localStorage.getItem(keyFor(userId))
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<AppearancePrefs>) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

function apply(prefs: AppearancePrefs) {
  const root = document.documentElement
  if (prefs.motion === "reduced") root.dataset.motion = "reduced"
  else delete root.dataset.motion
  if (prefs.transparency === "reduced") root.dataset.transparency = "reduced"
  else delete root.dataset.transparency
}

/** Inline in <head> before paint: applies the last signed-in user's stored preferences. */
export const appearanceInitScript = `(function(){try{var u=localStorage.getItem(${JSON.stringify(LAST_USER_KEY)})||"anon";var p=JSON.parse(localStorage.getItem(${JSON.stringify(KEY_PREFIX)}+u)||"{}");var r=document.documentElement;if(p.motion==="reduced")r.dataset.motion="reduced";if(p.transparency==="reduced")r.dataset.transparency="reduced";}catch(e){}})();`

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  window.addEventListener("storage", onChange)
  return () => {
    window.removeEventListener(EVENT, onChange)
    window.removeEventListener("storage", onChange)
  }
}

/** Read and update the current user's appearance preferences; changes apply to <html> immediately. */
export function useAppearancePreferences(userId?: string | number | null) {
  const snapshot = React.useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(keyFor(userId)) ?? "",
    () => ""
  )
  const prefs = React.useMemo<AppearancePrefs>(() => {
    if (!snapshot) return DEFAULTS
    try {
      return { ...DEFAULTS, ...(JSON.parse(snapshot) as Partial<AppearancePrefs>) }
    } catch {
      return DEFAULTS
    }
  }, [snapshot])

  React.useEffect(() => {
    try {
      localStorage.setItem(LAST_USER_KEY, String(userId ?? "anon"))
    } catch {}
    apply(read(userId))
  }, [userId, snapshot])

  const update = React.useCallback(
    (patch: Partial<AppearancePrefs>) => {
      const next = { ...read(userId), ...patch }
      try {
        localStorage.setItem(keyFor(userId), JSON.stringify(next))
      } catch {}
      apply(next)
      window.dispatchEvent(new Event(EVENT))
    },
    [userId]
  )
  return { prefs, update }
}

function subscribeRoot(onChange: () => void) {
  const mo = new MutationObserver(onChange)
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-motion"] })
  return () => mo.disconnect()
}

/** motion/react follows the OS by default; this also honours the in-app "Reduce motion" switch. */
export function AppearanceMotionConfig({ children }: { children: React.ReactNode }) {
  const appReduced = React.useSyncExternalStore(
    subscribeRoot,
    () => document.documentElement.dataset.motion === "reduced",
    () => false
  )
  return (
    <MotionConfig reducedMotion={appReduced ? "always" : "user"} transition={springs.smooth}>
      {children}
    </MotionConfig>
  )
}

type Labels = {
  motion: string
  motionHint: string
  transparency: string
  transparencyHint: string
}
const DEFAULT_LABELS: Labels = {
  motion: "Reduce motion",
  motionHint: "Replaces sliding, scaling and springs with short fades.",
  transparency: "Reduce transparency",
  transparencyHint: "Makes glass surfaces opaque for better legibility.",
}

/** Two settings rows (label + hint left, switch right — Perplexity / Apple Settings grammar). */
export function AppearancePreferencesControl({ userId, labels }: { userId?: string | number | null; labels?: Partial<Labels> }) {
  const { prefs, update } = useAppearancePreferences(userId)
  const copy = { ...DEFAULT_LABELS, ...labels }
  const motionId = React.useId()
  const transparencyId = React.useId()
  const rows = [
    { id: motionId, label: copy.motion, hint: copy.motionHint, checked: prefs.motion === "reduced", set: (v: boolean) => update({ motion: v ? "reduced" : "system" }) },
    {
      id: transparencyId,
      label: copy.transparency,
      hint: copy.transparencyHint,
      checked: prefs.transparency === "reduced",
      set: (v: boolean) => update({ transparency: v ? "reduced" : "system" }),
    },
  ]
  return (
    <div data-slot="appearance-preferences" className="flex flex-col">
      {rows.map((row) => (
        <div key={row.id} className="flex items-center justify-between gap-6 py-3 [&:not(:last-child)]:hairline-b">
          <div className="flex min-w-0 flex-col gap-0.5">
            <label htmlFor={row.id} className="text-[13px] font-medium text-label-1">
              {row.label}
            </label>
            <p id={`${row.id}-hint`} className="text-[12px] leading-4 text-label-2">
              {row.hint}
            </p>
          </div>
          <Switch id={row.id} aria-describedby={`${row.id}-hint`} checked={row.checked} onCheckedChange={(v) => row.set(v)} />
        </div>
      ))}
    </div>
  )
}
