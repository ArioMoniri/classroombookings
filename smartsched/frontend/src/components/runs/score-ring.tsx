"use client";

import { AlertTriangle, CheckCircle2, XOctagon } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

/** Hard-score proof badge: ring (lg) or pill (sm). Colour + icon + text, never colour alone. */
/** ``partial``: a best-effort run (FEASIBLE_PARTIAL) — amber ring filled to placed/total with "placed / total" in
 * the centre; never the green 100/100 of a complete timetable. */
export function ScoreRing({ value, label, size = "lg", className, partial }: { value: number | null; label: string; size?: "sm" | "lg"; className?: string; partial?: { placed: number; total: number } | null }) {
  const reduce = useReducedMotion();
  const feasible = value !== null && value >= 100;
  const Icon = partial ? AlertTriangle : feasible ? CheckCircle2 : XOctagon;
  if (partial && size !== "sm") {
    const r = 48;
    const c = 2 * Math.PI * r;
    const pct = partial.total > 0 ? partial.placed / partial.total : 0;
    return (
      <div className={cn("flex flex-col items-center", className)} role="img" aria-label={`${label}: ${partial.placed} / ${partial.total}`} data-testid="score-ring-partial">
        <div className="relative size-28">
          <svg viewBox="0 0 112 112" className="size-28 -rotate-90">
            <circle cx="56" cy="56" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="8" />
            <motion.circle cx="56" cy="56" r={r} fill="none" stroke="var(--status-warning-solid)" strokeWidth="8" strokeLinecap="round" strokeDasharray={c} initial={reduce ? false : { strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - pct) }} transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-bold tracking-[-0.01em] tabular-nums">{partial.placed}</span>
            <span className="text-[11px] text-muted-foreground tabular-nums">/ {partial.total}</span>
          </div>
        </div>
        <span className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-status-warning-fg">
          <Icon className="size-4" aria-hidden />
          {label}
        </span>
      </div>
    );
  }
  if (size === "sm") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-xs font-semibold",
          value === null ? "border-border text-muted-foreground" : feasible ? "border-status-feasible-border bg-status-feasible text-status-feasible-fg" : "border-status-infeasible-border bg-status-infeasible text-status-infeasible-fg",
          className,
        )}
        aria-label={`${label} ${value ?? "—"}/100`}
      >
        {value !== null ? <Icon className="size-3.5" aria-hidden /> : null}
        {value ?? "—"}/100
      </span>
    );
  }
  const r = 48;
  const c = 2 * Math.PI * r;
  const pct = (value ?? 0) / 100;
  const stroke = value === null ? "var(--border-strong)" : feasible ? "var(--status-feasible-solid)" : "var(--status-infeasible-solid)";
  return (
    <div className={cn("flex flex-col items-center", className)} role="img" aria-label={`${label}: ${value ?? "—"} / 100`}>
      <div className="relative size-28">
        <svg viewBox="0 0 112 112" className="size-28 -rotate-90">
          <circle cx="56" cy="56" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="8" />
          <motion.circle
            cx="56"
            cy="56"
            r={r}
            fill="none"
            stroke={stroke}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={c}
            initial={reduce ? false : { strokeDashoffset: c }}
            animate={{ strokeDashoffset: c * (1 - pct) }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-4xl font-bold tracking-[-0.01em]">{value ?? "—"}</span>
          <span className="text-[11px] text-muted-foreground">/ 100</span>
        </div>
      </div>
      <span className={cn("mt-2 inline-flex items-center gap-1 text-sm font-medium", value === null ? "text-muted-foreground" : feasible ? "text-status-feasible-fg" : "text-status-infeasible-fg")}>
        {value !== null ? <Icon className="size-4" aria-hidden /> : null}
        {label}
      </span>
    </div>
  );
}
