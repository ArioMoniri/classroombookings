import { AlertTriangle, Ban, CheckCircle2, Lock, Monitor, Stethoscope, XOctagon, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusKind = "feasible" | "infeasible" | "warning" | "locked" | "preoccupied" | "tip" | "pclab";

export const STATUS_ICON: Record<StatusKind, LucideIcon> = {
  feasible: CheckCircle2,
  infeasible: XOctagon,
  warning: AlertTriangle,
  locked: Lock,
  preoccupied: Ban,
  tip: Stethoscope,
  pclab: Monitor,
};

export const STATUS_CLASS: Record<StatusKind, string> = {
  feasible: "bg-status-feasible text-status-feasible-fg border-status-feasible-border",
  infeasible: "bg-status-infeasible text-status-infeasible-fg border-status-infeasible-border",
  warning: "bg-status-warning text-status-warning-fg border-status-warning-border",
  locked: "bg-status-locked text-status-locked-fg border-status-locked-border",
  preoccupied: "hatch-preoccupied text-status-preoccupied-fg border-status-preoccupied-border",
  tip: "bg-status-tip text-status-tip-fg border-status-tip-border",
  pclab: "bg-status-pclab text-status-pclab-fg border-status-pclab-border",
};

/** Colour is never the only cue: icon + text label always. */
export function StatusBadge({ kind, label, className }: { kind: StatusKind; label: string; className?: string }) {
  const Icon = STATUS_ICON[kind];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", STATUS_CLASS[kind], className)}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}
