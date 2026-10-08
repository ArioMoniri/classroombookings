"use client"
// Source: https://beautifului.dev — "Chat Composer" (registry item https://www.beautifului.dev/r/chat-composer.json,
// components/primitives/ChatComposer.tsx), composer section only. Licence: MIT, Copyright (c) 2026 Shane Levine
// (full text: src/components/ui/LICENSES/beautifului-MIT.txt).
// Modified: yes — extracted the composer from the scripted demo panel (no fake replies/timers); input is an
// auto-growing textarea (Enter sends, Shift+Enter breaks a line, IME-safe); adds busy/stop state, leading
// slot (attach), suggestion chips, localisable labels; tokens re-mapped to Liquid Glass. Kept: the field
// block that focuses on click, and the send button that turns from muted to ink when there is text.
import * as React from "react"
import { ArrowUpIcon, SquareIcon } from "lucide-react"
import { cn } from "cn"

import { Chip } from "@/components/ui/chip"

type PromptComposerProps = {
  onSend: (text: string) => void
  /** while true the send button becomes a stop button */
  busy?: boolean
  onStop?: () => void
  placeholder?: string
  /** accessible label of the field */
  label?: string
  sendLabel?: string
  stopLabel?: string
  suggestions?: string[]
  onSuggestion?: (text: string) => void
  /** e.g. an attach button */
  leading?: React.ReactNode
  disabled?: boolean
  className?: string
  maxRows?: number
}

function PromptComposer({
  onSend,
  busy = false,
  onStop,
  placeholder = "Ask or describe a change…",
  label = "Prompt",
  sendLabel = "Send",
  stopLabel = "Stop",
  suggestions,
  onSuggestion,
  leading,
  disabled = false,
  className,
  maxRows = 6,
}: PromptComposerProps) {
  const [draft, setDraft] = React.useState("")
  const ref = React.useRef<HTMLTextAreaElement>(null)
  const canSend = draft.trim().length > 0 && !disabled && !busy

  const send = () => {
    if (!canSend) return
    onSend(draft.trim())
    setDraft("")
  }

  return (
    <div data-slot="prompt-composer" className={cn("flex flex-col gap-2", className)}>
      {suggestions?.length ? (
        <div className="flex flex-wrap gap-1.5" role="list" aria-label="Suggestions">
          {suggestions.map((s) => (
            <span role="listitem" key={s}>
              <Chip size="sm" onClick={() => (onSuggestion ? onSuggestion(s) : setDraft(s))}>
                {s}
              </Chip>
            </span>
          ))}
        </div>
      ) : null}
      <div
        role="presentation"
        onClick={() => ref.current?.focus()}
        className="glass-thick flex cursor-text flex-col gap-2 rounded-[20px] p-2.5 transition-[box-shadow] duration-150 focus-within:shadow-[var(--glass-edge),0_0_0_3px_color-mix(in_oklab,var(--focus)_22%,transparent)]"
      >
        <textarea
          ref={ref}
          value={draft}
          rows={1}
          disabled={disabled}
          aria-label={label}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              send()
            }
          }}
          style={{ maxHeight: `${maxRows * 20 + 8}px` }}
          className="field-sizing-content min-h-5 w-full resize-none bg-transparent px-1 text-[14px] leading-5 text-label-1 outline-none placeholder:text-label-3 disabled:opacity-50"
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">{leading}</div>
          {busy ? (
            <button
              type="button"
              aria-label={stopLabel}
              onClick={onStop}
              className="flex size-8 items-center justify-center rounded-full bg-label-1 text-(--scene) outline-none transition-transform duration-(--dur-fast) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) active:scale-95"
            >
              <SquareIcon className="size-3 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              aria-label={sendLabel}
              disabled={!canSend}
              onClick={send}
              className={cn(
                "flex size-8 items-center justify-center rounded-full outline-none transition-[background-color,color,transform] duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) enabled:active:scale-95",
                canSend ? "bg-tint text-tint-foreground" : "bg-fill-1 text-label-3"
              )}
            >
              <ArrowUpIcon className="size-4 stroke-[2.4]" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export { PromptComposer, type PromptComposerProps }
