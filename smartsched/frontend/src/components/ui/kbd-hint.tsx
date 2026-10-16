"use client"
// SmartSched Liquid Glass v2 — KbdHint. Original work. Keycaps for shortcut hints.
// References: Raycast / Linear / Perplexity shortcut chips (Mobbin, docs/design/v2/references.md).
// "mod" renders ⌘ on Apple platforms and Ctrl elsewhere; server render assumes non-Apple and the
// client snapshot corrects it without a hydration mismatch (useSyncExternalStore).
// Accessible name (T-R1-07, R1-A-10): the key names of the platform ("Ctrl + K", "Cmd + K"), language-neutral
// key words rather than an English sentence ("Command or Control" leaked into the Turkish search trigger's name).
// A caller that needs a fuller name sets its own aria-label on the control and hides the kbd (top-bar.tsx).
import * as React from "react"
import { cn } from "cn"

const subscribe = () => () => {}
const isApple = () => /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent)

function usePlatformMod() {
  return React.useSyncExternalStore(subscribe, isApple, () => false)
}

const SYMBOLS: Record<string, { apple: string; other: string; appleLabel: string; label: string }> = {
  mod: { apple: "⌘", other: "Ctrl", appleLabel: "Cmd", label: "Ctrl" },
  shift: { apple: "⇧", other: "Shift", appleLabel: "Shift", label: "Shift" },
  alt: { apple: "⌥", other: "Alt", appleLabel: "Option", label: "Alt" },
  enter: { apple: "↩", other: "Enter", appleLabel: "Enter", label: "Enter" },
  esc: { apple: "esc", other: "Esc", appleLabel: "Esc", label: "Esc" },
}

/** The modifier's key word for the current platform ("Ctrl" / "Cmd"), for names such as "Komut paleti (Ctrl+K)". */
export function modKeyLabel(apple: boolean): string {
  return apple ? SYMBOLS.mod!.appleLabel : SYMBOLS.mod!.label
}

type KbdHintProps = React.ComponentProps<"kbd"> & {
  /** e.g. ["mod","K"] or ["G","D"] (a sequence when `sequence` is true) */
  keys: string[]
  sequence?: boolean
  /** word between keys of a sequence (localise: "sonra" in tr) */
  thenLabel?: string
  size?: "sm" | "md"
}

function KbdHint({ keys, sequence = false, thenLabel = "then", size = "sm", className, ...props }: KbdHintProps) {
  const apple = usePlatformMod()
  const cap = size === "sm" ? "h-[18px] min-w-[18px] px-1 type-caption" : "h-[22px] min-w-[22px] px-1.5 type-footnote"
  return (
    <kbd
      data-slot="kbd"
      aria-label={keys.map((k) => { const sym = SYMBOLS[k.toLowerCase()]; return sym ? (apple ? sym.appleLabel : sym.label) : k.toUpperCase() }).join(sequence ? ` ${thenLabel} ` : " + ")}
      className={cn("inline-flex items-center gap-0.5 font-sans font-medium not-italic text-label-2", className)}
      {...props}
    >
      {keys.map((k, i) => {
        const sym = SYMBOLS[k.toLowerCase()]
        return (
          <React.Fragment key={`${k}-${i}`}>
            {sequence && i > 0 ? <span aria-hidden className="px-0.5 text-2xs text-label-3">{thenLabel}</span> : null}
            <span
              aria-hidden
              className={cn(
                "inline-flex items-center justify-center rounded-[5px] bg-(--mat-thick) leading-none shadow-[inset_0_-1px_0_0_var(--hairline-strong),0_0_0_1px_var(--hairline)]",
                cap
              )}
            >
              {sym ? (apple ? sym.apple : sym.other) : k.toUpperCase()}
            </span>
          </React.Fragment>
        )
      })}
    </kbd>
  )
}

export { KbdHint, usePlatformMod }
