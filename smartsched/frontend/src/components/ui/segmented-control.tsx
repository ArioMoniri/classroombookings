"use client"
// SmartSched SegmentedControl — the one segmented control (design-system overhaul 2026-10-15; review §2
// "Segmented control"). Replaces SegmentedGlass (beUI Tabs), studio/segmented.tsx and the hand-rolled
// tab/radio rows. Original work; references: Apple Weather forecast scrubber (Mobbin A15) and Arcade
// inspector (H19) — a small track with a lit thumb, one height per row; Linear's view switcher.
//
// Layout: `inline-grid; grid-auto-flow: column; grid-auto-columns: 1fr; white-space: nowrap;
// min-width: max-content; padding: 3px` — segments share one width and never wrap. Height = --control-h-*.
// When the container is narrower than the control's natural width it falls back to a NativeSelect
// (CSS container query on the wrapper; the threshold is the measured natural width). The wrapper has no explicit
// width: `contain-intrinsic-inline-size: natural` sizes it in content-sized parents and `min-width:0` lets grid /
// flex parents shrink it (an explicit px width counted as min-content and pushed the track over its neighbours).
//
// Motion (motion_designer pattern 2, motion.md §3): the thumb is ONE absolutely positioned element whose
// resting place is pure CSS (translateX(index × 100%) inside equal columns), so it can never rest outside the
// track (the dark "16 px above the track" bug came from layout projection at rest). Changing the value
// transitions `transform` only, on the --spring-glass-morph linear() curve (CSS mirror of springs.glassMorph,
// ≤ 300 ms); a new target mid-flight re-targets from the current position (interruptible). Reduced motion:
// the global rule zeroes the duration (the thumb jumps; the label weight/colour change carries the state).
// Touch: segments are 30 / 38 px tall on coarse pointers (track − 6 px); each gets a 44 × 44 hit area through ::after
// (ui/hit-area.ts, MOBILE.md M-02). The select fallback is a NativeSelect, so it has 16 px text on phones.
// Purpose sentence: "When the user picks a segment, the thumb travels to it so they see which view is now on."
import * as React from "react"
import { cn } from "cn"

import { coarseHitArea } from "@/components/ui/hit-area"
import { NativeSelect } from "@/components/ui/native-select"

export type SegmentedOption<V extends string = string> = {
  value: V
  label: React.ReactNode
  icon?: React.ReactNode
  /** id of the panel this segment shows (tablist semantics) */
  controls?: string
  disabled?: boolean
  /** plain-text label for the select fallback and the accessible name when `label` is not a string */
  text?: string
  /** forwarded to the segment button */
  testId?: string
  /** native tooltip (e.g. why an option is disabled) */
  title?: string
}

export type SegmentedControlProps<V extends string> = {
  options: readonly SegmentedOption<V>[]
  /** controlled value; `null` = controlled with nothing selected (no thumb) */
  value?: V | null
  defaultValue?: V
  onValueChange?: (value: V) => void
  size?: "sm" | "md" | "lg"
  /** stretch to the container width (mobile, sheets) */
  fill?: boolean
  /** tablist (default; segments switch panels or views) or radiogroup (segments set a value in a form) */
  semantics?: "tablist" | "radiogroup"
  /** fall back to a select when the container is too narrow (default true) */
  collapse?: boolean
  className?: string
  "aria-label"?: string
  "aria-labelledby"?: string
  "aria-describedby"?: string
  "data-testid"?: string
}

const heights = {
  sm: "h-(--control-h-sm) type-footnote font-medium",
  md: "h-(--control-h-md) type-callout font-medium",
  lg: "h-(--control-h-lg) type-body font-medium",
} as const

/** Shared track and thumb look (ui/tabs' default variant uses the same classes). */
export const segmentedTrack =
  "relative isolate inline-grid min-w-max grid-flow-col auto-cols-fr items-stretch rounded-full bg-fill-2 p-[3px] whitespace-nowrap shadow-[inset_0_0_0_1px_var(--hairline)]"
export const segmentedThumb =
  "pointer-events-none absolute inset-y-[3px] left-[3px] -z-10 rounded-full bg-(--mat-thick-solid) shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline),0_1px_3px_0_rgba(0,0,0,0.12)] transition-transform duration-(--spring-glass-morph-ms) ease-(--spring-glass-morph)"
export const segmentedItem =
  "relative inline-flex min-w-0 items-center justify-center gap-1.5 rounded-full px-3 text-label-2 transition-colors duration-(--dur-fast) hover:text-label-1 focus-visible:outline-2 focus-visible:-outline-offset-1 focus-visible:outline-(--focus) disabled:pointer-events-none disabled:opacity-45 aria-checked:text-label-1 aria-selected:text-label-1 [&_svg]:size-3.5 [&_svg]:shrink-0 [&_svg]:stroke-[1.75] " + coarseHitArea

function textOf(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (Array.isArray(node)) return node.map(textOf).join("")
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return textOf(node.props.children)
  return ""
}

export function SegmentedControl<V extends string>({
  options,
  value,
  defaultValue,
  onValueChange,
  size = "md",
  fill = false,
  semantics = "tablist",
  collapse = true,
  className,
  "aria-label": ariaLabel,
  "aria-labelledby": labelledBy,
  "aria-describedby": describedBy,
  "data-testid": testId,
}: SegmentedControlProps<V>) {
  const [internal, setInternal] = React.useState<V | undefined>(defaultValue ?? options[0]?.value)
  const current = value === undefined ? internal : (value ?? undefined)
  const id = React.useId().replace(/[^a-zA-Z0-9_-]/g, "")
  const trackRef = React.useRef<HTMLDivElement>(null)
  const labels = options.map((o) => o.text ?? textOf(o.label))
  // SSR / first paint: a generous estimate (7.6 px per character at 13 px + padding); then the real width.
  const estimate = Math.ceil(
    6 + options.length * (24 + Math.max(...labels.map((l) => l.length), 1) * (size === "sm" ? 7 : 7.6) + (options.some((o) => o.icon) ? 20 : 0)),
  )
  const [natural, setNatural] = React.useState(estimate)
  const labelKey = labels.join("\u0001")
  React.useLayoutEffect(() => {
    const el = trackRef.current
    if (!el) return
    // measure the max-content width once per label set (synchronous, before paint). The track may already be
    // hidden by the select fallback because the first-paint estimate was wider than the container (seven short
    // day names on a phone): show it for the measurement, or it would stay a select for good.
    const prev = el.style.width
    const prevDisplay = el.style.display
    el.style.display = "inline-grid"
    el.style.width = "max-content"
    // offsetParent null: the whole control is not rendered (a hidden panel); keep the estimate
    const w = el.offsetParent === null ? 0 : Math.ceil(el.getBoundingClientRect().width)
    el.style.width = prev
    el.style.display = prevDisplay
    if (w > 0) setNatural(w)
  }, [labelKey, size])

  const select = (v: V) => {
    if (value === undefined) setInternal(v)
    onValueChange?.(v)
  }
  const enabled = options.filter((o) => !o.disabled)
  const index = options.findIndex((o) => o.value === current)
  const focusValue = index >= 0 ? current : enabled[0]?.value

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return
    const i = enabled.findIndex((o) => o.value === current)
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl"
    const fwd = event.key === "ArrowDown" || event.key === (rtl ? "ArrowLeft" : "ArrowRight")
    const target = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : (i + (fwd ? 1 : -1) + enabled.length) % enabled.length
    const next = enabled[target]
    if (!next) return
    event.preventDefault()
    select(next.value)
    event.currentTarget.querySelector<HTMLElement>(`[data-value="${CSS.escape(next.value)}"]`)?.focus()
  }

  const isTabs = semantics === "tablist"
  const name = `seg${id}`
  return (
    <div
      data-slot="segmented-control"
      data-seg={name}
      className={cn("min-w-0 max-w-full shrink", fill && "w-full", className)}
      style={{
        "--seg-w": `${natural}px`,
        containerType: collapse ? "inline-size" : undefined,
        containerName: collapse ? name : undefined,
        // size containment hides the track from intrinsic sizing; this gives content-sized parents the natural width
        // back, while min-width:0 still lets grid / flex parents shrink it (then the select fallback engages)
        containIntrinsicInlineSize: collapse ? `${natural}px` : undefined,
      } as React.CSSProperties}
    >
      <div
        ref={trackRef}
        role={isTabs ? "tablist" : "radiogroup"}
        aria-label={ariaLabel}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        data-part="track"
        data-testid={testId}
        onKeyDown={onKeyDown}
        className={cn(segmentedTrack, heights[size], fill && "w-full")}
      >
        <span
          aria-hidden
          data-slot="segmented-thumb"
          className={cn(segmentedThumb, index < 0 && "hidden")}
          style={{ width: `calc((100% - 6px) / ${options.length})`, transform: `translateX(${Math.max(0, index) * 100}%)` }}
        />
        {options.map((o) => {
          const on = o.value === current
          return (
            <button
              key={o.value}
              type="button"
              role={isTabs ? "tab" : "radio"}
              aria-selected={isTabs ? on : undefined}
              aria-checked={isTabs ? undefined : on}
              aria-controls={o.controls}
              aria-label={typeof o.label === "string" ? undefined : o.text}
              tabIndex={o.value === focusValue ? 0 : -1}
              title={o.title}
              disabled={o.disabled}
              data-value={o.value}
              data-state={on ? "active" : "inactive"}
              data-testid={o.testId}
              onClick={() => select(o.value)}
              className={segmentedItem}
            >
              {o.icon}
              {typeof o.label === "string" ? <span className="truncate">{o.label}</span> : o.label}
            </button>
          )
        })}
      </div>
      {collapse ? (
        <>
          <NativeSelect
            aria-label={ariaLabel}
            aria-labelledby={labelledBy}
            value={current ?? ""}
            onChange={(e) => select(e.target.value as V)}
            size={size === "lg" ? "lg" : size}
            className="hidden"
          >
            {current === undefined ? <option value="" disabled>—</option> : null}
            {options.map((o, i) => (
              <option key={o.value} value={o.value} disabled={o.disabled}>
                {labels[i]}
              </option>
            ))}
          </NativeSelect>
          <style>{`@container ${name} (max-width: ${natural - 1}px){[data-seg="${name}"]>[data-part="track"]{display:none}[data-seg="${name}"]>[data-slot="native-select"]{display:inline-flex}}`}</style>
        </>
      ) : null}
    </div>
  )
}
