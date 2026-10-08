"use client"
// Source: https://beautifului.dev — "Task Rows" (registry item https://www.beautifului.dev/r/task-rows.json,
// components/primitives/TaskRows.tsx). Licence: MIT, Copyright (c) 2026 Shane Levine
// (full text: src/components/ui/LICENSES/beautifului-MIT.txt).
// Modified: yes — the scripted tick sequence is removed; each row's status is a prop
// ("pending" | "running" | "done" | "failed") driven by real progress (e.g. solver / import jobs); failed
// rows get a real retry button; labels are localisable; foundation.css tokens re-mapped to Liquid Glass;
// detail stagger shortened to ≤ 240 ms. Kept: spinner ring with step number, status badge, pill,
// capsule ↔ list variants, and the expandable detail grammar (grid-template-rows 0fr → 1fr).
import * as React from "react"
import { CheckIcon, ChevronDownIcon, RotateCwIcon, XIcon } from "lucide-react"
import { cn } from "cn"

export type TaskStatus = "pending" | "running" | "done" | "failed"
export type TaskDetail = { label: React.ReactNode; meta?: React.ReactNode }
export type TaskRow = {
  key: string
  label: React.ReactNode
  meta?: React.ReactNode
  status: TaskStatus
  /** number shown inside the ring while pending/running */
  step?: number
  details?: TaskDetail[]
}
export type TaskRowsLabels = { completed: string; failed: string; retry: string; running: string; pending: string }
const DEFAULT_LABELS: TaskRowsLabels = { completed: "Completed", failed: "Failed", retry: "Retry", running: "Running", pending: "Pending" }

function SpinnerRing({ active, children }: { active?: boolean; children?: React.ReactNode }) {
  const size = 24
  const stroke = 2
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  return (
    <span className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden className={cn("absolute inset-0", active && "animate-spin [animation-duration:1.1s]")}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--hairline-strong)" strokeWidth={stroke} />
        {active ? (
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${c * 0.28} ${c * 0.72}`} />
        ) : null}
      </svg>
      <span className="relative text-[10.5px] font-semibold text-label-1 tabular-nums">{children}</span>
    </span>
  )
}

function StatusBadge({ tone }: { tone: "red" | "green" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-[22px] shrink-0 items-center justify-center rounded-full animate-in zoom-in-50 fade-in duration-200",
        tone === "red" ? "bg-status-infeasible-solid text-white" : "bg-status-feasible-solid text-white dark:text-[#111114]"
      )}
    >
      {tone === "red" ? <XIcon className="size-3 stroke-[3.5]" /> : <CheckIcon className="size-[13px] stroke-[3.5]" />}
    </span>
  )
}

type TaskRowsProps = {
  rows: TaskRow[]
  variant?: "capsules" | "list"
  labels?: Partial<TaskRowsLabels>
  className?: string
  /** rows open by default */
  defaultOpen?: string[]
  onToggleRow?: (key: string, open: boolean) => void
  onRetry?: (key: string) => void
}

function TaskRows({ rows, variant = "capsules", labels, className, defaultOpen = [], onToggleRow, onRetry }: TaskRowsProps) {
  const copy = { ...DEFAULT_LABELS, ...labels }
  const [open, setOpen] = React.useState<Record<string, boolean>>(() => Object.fromEntries(defaultOpen.map((k) => [k, true])))
  const list = variant === "list"
  return (
    <ul
      data-slot="task-rows"
      className={cn("flex w-full flex-col", list ? "glass-regular gap-0 overflow-hidden rounded-2xl" : "gap-2", className)}
    >
      {rows.map((row) => {
        const isOpen = !!open[row.key]
        const hasDetails = !!row.details?.length
        const detailsId = `task-${row.key}-details`
        return (
          <li
            key={row.key}
            className={cn(
              "overflow-hidden transition-[border-radius,background-color] duration-300",
              list ? "[&:not(:last-child)]:hairline-b" : cn("glass-regular", isOpen ? "rounded-2xl" : "rounded-[22px]")
            )}
          >
            <div className="flex h-11 w-full items-center gap-2.5 px-2.5">
              <span className="flex size-6 shrink-0 items-center justify-center">
                {row.status === "done" ? (
                  <StatusBadge tone="green" />
                ) : row.status === "failed" ? (
                  <StatusBadge tone="red" />
                ) : (
                  <SpinnerRing active={row.status === "running"}>{row.step}</SpinnerRing>
                )}
              </span>
              <button
                type="button"
                aria-expanded={hasDetails ? isOpen : undefined}
                aria-controls={hasDetails ? detailsId : undefined}
                disabled={!hasDetails}
                onClick={() => {
                  setOpen((cur) => ({ ...cur, [row.key]: !isOpen }))
                  onToggleRow?.(row.key, !isOpen)
                }}
                className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg text-left outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) disabled:cursor-default"
              >
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-label-1">{row.label}</span>
                {row.meta ? <span className="text-[12.5px] text-label-2 tabular-nums">{row.meta}</span> : null}
                <span className="sr-only">
                  {row.status === "done" ? copy.completed : row.status === "failed" ? copy.failed : row.status === "running" ? copy.running : copy.pending}
                </span>
                {row.status === "done" ? (
                  <span aria-hidden className="inline-flex h-[22px] items-center rounded-full bg-status-feasible px-2 text-[11.5px] font-medium text-status-feasible-fg">
                    {copy.completed}
                  </span>
                ) : null}
                {hasDetails ? (
                  <ChevronDownIcon aria-hidden className={cn("size-[15px] shrink-0 text-label-3 transition-transform duration-300", isOpen && "rotate-180")} />
                ) : null}
              </button>
              {row.status === "failed" ? (
                <button
                  type="button"
                  onClick={() => onRetry?.(row.key)}
                  className="inline-flex h-[22px] items-center gap-1.5 rounded-full bg-status-infeasible px-2 text-[11.5px] font-medium text-status-infeasible-fg outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)"
                >
                  {copy.failed} · {copy.retry}
                  <RotateCwIcon aria-hidden className="size-3 stroke-[2.5]" />
                </button>
              ) : null}
            </div>
            {hasDetails ? (
              <div
                id={detailsId}
                className="grid transition-[grid-template-rows,opacity] duration-300 ease-(--ease-out)"
                style={{ gridTemplateRows: isOpen ? "1fr" : "0fr", opacity: isOpen ? 1 : 0 }}
                inert={!isOpen}
                aria-hidden={!isOpen || undefined}
              >
                <div className="overflow-hidden">
                  <div className="mb-2.5 grid grid-cols-[24px_1fr] gap-2.5 px-2.5">
                    <span aria-hidden className="mx-auto h-full w-px bg-hairline-strong" />
                    <ul className="flex flex-col gap-1.5">
                      {row.details!.map((d, j) => (
                        <li
                          key={j}
                          className="flex items-center justify-between gap-3 animate-in fade-in slide-in-from-bottom-1 duration-200"
                          style={{ animationDelay: `${Math.min(j * 40, 120)}ms`, animationFillMode: "both" }}
                        >
                          <span className="text-[12px] text-label-2">{d.label}</span>
                          {d.meta ? <span className="font-mono text-[11.5px] text-label-3 tabular-nums">{d.meta}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

export { TaskRows }
