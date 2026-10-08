"use client"
// SmartSched Liquid Glass v2 — EmptyState. Original work.
// References (docs/design/v2/references.md): Linear "Projects" and Superlist empty lists — left-aligned,
// one sentence, one primary action; Apple Notes empty folders — quiet, no mascot.
// Illustrations are the SmartSched Lottie set (docs/lottie, AGPL-3.0 like the repo) copied to
// src/assets/lottie. They play once (frames 0 → poster frame) on lottie-react and rest there; under
// prefers-reduced-motion the static poster PNG is shown instead and nothing animates.
import * as React from "react"
import dynamic from "next/dynamic"
import Image, { type StaticImageData } from "next/image"
import { useTheme } from "next-themes"
import { useReducedMotion } from "motion/react"
import { cn } from "cn"

import heroSolverLight from "@/assets/lottie/hero-solver-light-poster.png"
import heroSolverDark from "@/assets/lottie/hero-solver-dark-poster.png"
import nlToRulesLight from "@/assets/lottie/nl-to-rules-light-poster.png"
import nlToRulesDark from "@/assets/lottie/nl-to-rules-dark-poster.png"
import fileToRulesLight from "@/assets/lottie/file-to-rules-light-poster.png"
import fileToRulesDark from "@/assets/lottie/file-to-rules-dark-poster.png"
import precheckFixLight from "@/assets/lottie/precheck-fix-light-poster.png"
import precheckFixDark from "@/assets/lottie/precheck-fix-dark-poster.png"

type LottiePlayerProps = {
  src: object
  autoplay?: boolean
  loop?: boolean
  /** play [from, to] once and hold the last frame — we stop on the poster frame */
  segment?: readonly [number, number]
  className?: string
}
/* LottieLight: the smallest lottie-react build (svg renderer, no expression engine) — our files use no
   expressions. Client-only: lottie-web touches `document` at import time. */
const Lottie = dynamic<LottiePlayerProps>(
  () => import("lottie-react").then((m) => m.LottieLight as unknown as React.ComponentType<LottiePlayerProps>),
  { ssr: false, loading: () => null }
)

export type EmptyStateAnimation = "hero-solver" | "nl-to-rules" | "file-to-rules" | "precheck-fix"
type Theme = "light" | "dark"

type LottieJson = { layers: { nm?: string }[]; w: number; h: number; [key: string]: unknown }

/* Each JSON is loaded on demand (code-split), never in the initial bundle. */
const LOADERS: Record<`${EmptyStateAnimation}-${Theme}`, () => Promise<unknown>> = {
  "hero-solver-light": () => import("@/assets/lottie/hero-solver-light.json"),
  "hero-solver-dark": () => import("@/assets/lottie/hero-solver-dark.json"),
  "nl-to-rules-light": () => import("@/assets/lottie/nl-to-rules-light.json"),
  "nl-to-rules-dark": () => import("@/assets/lottie/nl-to-rules-dark.json"),
  "file-to-rules-light": () => import("@/assets/lottie/file-to-rules-light.json"),
  "file-to-rules-dark": () => import("@/assets/lottie/file-to-rules-dark.json"),
  "precheck-fix-light": () => import("@/assets/lottie/precheck-fix-light.json"),
  "precheck-fix-dark": () => import("@/assets/lottie/precheck-fix-dark.json"),
}

const POSTERS: Record<`${EmptyStateAnimation}-${Theme}`, StaticImageData> = {
  "hero-solver-light": heroSolverLight,
  "hero-solver-dark": heroSolverDark,
  "nl-to-rules-light": nlToRulesLight,
  "nl-to-rules-dark": nlToRulesDark,
  "file-to-rules-light": fileToRulesLight,
  "file-to-rules-dark": fileToRulesDark,
  "precheck-fix-light": precheckFixLight,
  "precheck-fix-dark": precheckFixDark,
}

/** Poster frames from docs/lottie/README.md — the animation comes to rest here. */
const POSTER_FRAME: Record<EmptyStateAnimation, number> = {
  "hero-solver": 140,
  "nl-to-rules": 125,
  "file-to-rules": 128,
  "precheck-fix": 96,
}

const subscribe = () => () => undefined
function useHydrated() {
  return React.useSyncExternalStore(subscribe, () => true, () => false)
}

function LottieIllustration({ name, label }: { name: EmptyStateAnimation; label: string }) {
  const { resolvedTheme } = useTheme()
  const hydrated = useHydrated()
  const reduce = useReducedMotion()
  const theme: Theme = resolvedTheme === "dark" ? "dark" : "light"
  const key = `${name}-${theme}` as const
  const [loaded, setLoaded] = React.useState<{ key: string; data: LottieJson } | null>(null)
  const poster = POSTERS[key]

  React.useEffect(() => {
    if (!hydrated || reduce) return
    let cancelled = false
    LOADERS[key]().then((mod) => {
      if (cancelled) return
      const json = ((mod as { default?: LottieJson }).default ?? mod) as LottieJson
      // The source files carry an opaque page-colour background layer; on glass we drop it.
      const data = { ...json, layers: json.layers.filter((layer) => layer.nm !== "background") }
      setLoaded({ key, data })
    })
    return () => {
      cancelled = true
    }
  }, [hydrated, reduce, key])

  const frame = "relative aspect-video w-full max-w-[320px] overflow-hidden rounded-2xl"
  if (!hydrated) return <div className={frame} aria-hidden />
  const data = loaded?.key === key ? loaded.data : null

  if (reduce || !data) {
    return (
      <div className={cn(frame, "glass-edge")}>
        <Image src={poster} alt={label} fill sizes="320px" className="object-cover" priority={false} />
      </div>
    )
  }
  return (
    <div className={frame} role="img" aria-label={label}>
      <Lottie src={data} autoplay loop={false} segment={[0, POSTER_FRAME[name]]} className="size-full" />
    </div>
  )
}

type EmptyStateProps = Omit<React.ComponentProps<"section">, "title"> & {
  title: React.ReactNode
  description?: React.ReactNode
  /** primary action first, at most one secondary (anti-pattern A6: no button rows) */
  actions?: React.ReactNode
  /** one of the SmartSched Lottie illustrations */
  animation?: EmptyStateAnimation
  /** accessible description of the illustration (required when `animation` is set) */
  animationLabel?: string
  /** small icon instead of an illustration (lucide, 20 px) */
  icon?: React.ReactNode
  /** start = left-aligned (default, reads as part of the page); center only for full-bleed canvases */
  align?: "start" | "center"
  size?: "sm" | "md"
}

function EmptyState({
  title,
  description,
  actions,
  animation,
  animationLabel,
  icon,
  align = "start",
  size = "md",
  className,
  ...props
}: EmptyStateProps) {
  const headingId = React.useId()
  return (
    <section
      aria-labelledby={headingId}
      data-slot="empty-state"
      className={cn(
        "flex flex-col gap-4",
        align === "center" ? "items-center text-center" : "items-start text-left",
        size === "sm" ? "py-6" : "py-10",
        className
      )}
      {...props}
    >
      {animation ? <LottieIllustration name={animation} label={animationLabel ?? ""} /> : null}
      {!animation && icon ? (
        <div aria-hidden className="flex size-10 items-center justify-center rounded-xl bg-fill-2 text-label-2 [&_svg]:size-5 [&_svg]:stroke-[1.75]">
          {icon}
        </div>
      ) : null}
      <div className={cn("flex max-w-[52ch] flex-col gap-1", align === "center" && "items-center")}>
        <h2 id={headingId} className={cn("text-label-1", size === "sm" ? "type-headline" : "type-title-3")}>
          {title}
        </h2>
        {description ? <p className="text-[13px] leading-[19px] text-label-2">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </section>
  )
}

export { EmptyState, type EmptyStateProps }
