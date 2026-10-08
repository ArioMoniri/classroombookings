"use client"
// Source: https://beautifului.dev — "Diff Table" (registry item https://www.beautifului.dev/r/diff-table.json,
// components/primitives/DiffTable.tsx). Licence: MIT, Copyright (c) 2026 Shane Levine
// (full text: src/components/ui/LICENSES/beautifului-MIT.txt).
// Modified: yes — the scripted demo (useStage timers, ice-cream rows) is removed; rows, columns and copy are
// props; each changed row has a real checkbox control (upstream toggled an aria-selected <tr>); foundation.css
// tokens (--ink, --red-tint, --green-tint, shadow-card) are re-mapped to Liquid Glass tokens; the footer
// uses our Button. Kept: the row-level include/exclude grammar, the tinted removal/addition rows, the
// IncludedMark, and the summary footer that follows the selection.
import * as React from "react"
import { CheckIcon } from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"

export type DiffChange = "removed" | "added" | "unchanged"

export type DiffTableRow = {
  key: string
  change: DiffChange
  /** one node per column */
  cells: React.ReactNode[]
  /** accessible name of the change, e.g. "Remove MAT101 from A-201" */
  label: string
}

export type DiffTableLabels = {
  hint: string
  summary: (removals: number, additions: number) => string
  apply: (count: number) => string
  applied: (count: number) => string
}

const DEFAULT_LABELS: DiffTableLabels = {
  hint: "Click a changed row to include or exclude it",
  summary: (r, a) => `${r} ${r === 1 ? "removal" : "removals"} · ${a} ${a === 1 ? "addition" : "additions"}`,
  apply: (n) => `Apply ${n} ${n === 1 ? "change" : "changes"}`,
  applied: (n) => `${n} ${n === 1 ? "change" : "changes"} applied`,
}

function IncludedMark({ included, tone }: { included: boolean; tone: "red" | "green" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-[18px] shrink-0 items-center justify-center rounded-[5px] transition-[background-color,color,transform] duration-150",
        included
          ? tone === "red"
            ? "bg-status-infeasible-solid text-white"
            : "bg-status-feasible-solid text-white dark:text-[#111114]"
          : "scale-[0.92] bg-fill-3 text-label-3 shadow-[inset_0_0_0_1px_var(--hairline-strong)]"
      )}
    >
      {included ? <CheckIcon className="size-[11px] stroke-[3]" /> : null}
    </span>
  )
}

type DiffTableProps = {
  title: React.ReactNode
  columns: { key: string; label: React.ReactNode; width?: string }[]
  rows: DiffTableRow[]
  /** controlled inclusion map (key → included); defaults to every change included */
  included?: Record<string, boolean>
  onIncludedChange?: (next: Record<string, boolean>) => void
  onApply?: (includedKeys: string[]) => void
  applied?: boolean
  labels?: Partial<DiffTableLabels>
  className?: string
}

function DiffTable({ title, columns, rows, included, onIncludedChange, onApply, applied = false, labels, className }: DiffTableProps) {
  const copy = { ...DEFAULT_LABELS, ...labels }
  const [internal, setInternal] = React.useState<Record<string, boolean>>(() =>
    Object.fromEntries(rows.filter((r) => r.change !== "unchanged").map((r) => [r.key, true]))
  )
  const state = included ?? internal
  const isIncluded = (key: string) => state[key] ?? true
  const toggle = (key: string) => {
    if (applied) return
    const next = { ...state, [key]: !isIncluded(key) }
    if (!included) setInternal(next)
    onIncludedChange?.(next)
  }
  const removals = rows.filter((r) => r.change === "removed" && isIncluded(r.key)).length
  const additions = rows.filter((r) => r.change === "added" && isIncluded(r.key)).length
  const total = removals + additions

  return (
    <div data-slot="diff-table" className={cn("glass-regular w-full overflow-hidden rounded-2xl", className)}>
      <div className="flex min-h-10 items-center justify-between gap-3 px-4 hairline-b">
        <span className="text-[13px] font-semibold text-label-1">{title}</span>
        {!applied ? <span className="text-[11.5px] text-label-3">{copy.hint}</span> : null}
      </div>
      <table className="w-full table-fixed border-collapse text-left">
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={c.width ? { width: c.width } : undefined} />
          ))}
          <col style={{ width: 40 }} />
        </colgroup>
        <thead>
          <tr className="hairline-b">
            {columns.map((c) => (
              <th key={c.key} scope="col" className="h-8 px-4 text-[12px] font-medium text-label-3">
                {c.label}
              </th>
            ))}
            <th scope="col" className="sr-only">
              Include
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const changed = row.change !== "unchanged"
            const on = changed && isIncluded(row.key)
            const removed = row.change === "removed"
            const tone = removed ? "red" : "green"
            return (
              <tr
                key={row.key}
                onClick={changed && !applied ? () => toggle(row.key) : undefined}
                className={cn(
                  "transition-[background-color,opacity] duration-150 [&>td]:shadow-[inset_0_-1px_0_0_var(--hairline)] last:[&>td]:shadow-none",
                  changed && !applied && "cursor-pointer hover:brightness-[0.985] dark:hover:brightness-110",
                  on && removed && "bg-status-infeasible",
                  on && !removed && "bg-status-feasible",
                  changed && !on && "opacity-60"
                )}
              >
                {row.cells.map((cell, i) => (
                  <td
                    key={i}
                    className={cn(
                      "h-10 truncate px-4 text-[13px] transition-colors duration-200",
                      i === 0 ? "font-medium" : "text-label-2",
                      on && removed && "text-status-infeasible-fg",
                      on && removed && i === row.cells.length - 1 && "line-through decoration-[color-mix(in_oklab,var(--status-infeasible-fg)_50%,transparent)]",
                      on && !removed && "text-status-feasible-fg"
                    )}
                  >
                    {cell}
                  </td>
                ))}
                <td className="h-10 pr-3">
                  {changed ? (
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={on}
                      aria-label={row.label}
                      disabled={applied}
                      onClick={(event) => {
                        event.stopPropagation()
                        toggle(row.key)
                      }}
                      className="flex rounded-[6px] outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)"
                    >
                      <IncludedMark included={on} tone={tone} />
                    </button>
                  ) : null}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="flex min-h-12 items-center justify-between gap-3 bg-fill-3 px-4 hairline-t">
        {applied ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-status-feasible py-1 pr-2.5 pl-1 text-[12.5px] font-medium text-status-feasible-fg animate-in fade-in zoom-in-95 duration-200">
            <span className="flex size-[18px] items-center justify-center rounded-full bg-status-feasible-solid text-white dark:text-[#111114]">
              <CheckIcon className="size-[11px] stroke-[3]" />
            </span>
            {copy.applied(total)}
          </span>
        ) : (
          <>
            <span className="text-[12px] text-label-2 tabular-nums" aria-live="polite">
              {copy.summary(removals, additions)}
            </span>
            <Button size="sm" disabled={total === 0} onClick={() => onApply?.(rows.filter((r) => r.change !== "unchanged" && isIncluded(r.key)).map((r) => r.key))}>
              {copy.apply(total)}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

export { DiffTable }
