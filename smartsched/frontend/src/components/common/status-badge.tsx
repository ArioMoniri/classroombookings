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

/** Quiet translucent tints (liquid-glass.md §5.3); the hatch stays for "preoccupied". */
export const STATUS_CLASS: Record<StatusKind, string> = {
  feasible: "bg-status-feasible text-status-feasible-fg",
  infeasible: "bg-status-infeasible text-status-infeasible-fg",
  warning: "bg-status-warning text-status-warning-fg",
  locked: "bg-status-locked text-status-locked-fg",
  preoccupied: "hatch-preoccupied text-status-preoccupied-fg",
  tip: "bg-status-tip text-status-tip-fg",
  pclab: "bg-status-pclab text-status-pclab-fg",
};

/** Colour is never the only cue (G4): glyph + word, always. `variant="plain"` = glyph + word without a tint. */
export function StatusBadge({ kind, label, className, variant = "tint" }: { kind: StatusKind; label: string; className?: string; variant?: "tint" | "plain" }) {
  const Icon = STATUS_ICON[kind];
  if (variant === "plain") {
    return (
      <span className={cn("inline-flex items-center gap-1 text-[12px] font-medium whitespace-nowrap", STATUS_CLASS[kind].split(" ").filter((c) => c.startsWith("text-")).join(" "), className)}>
        <Icon className="size-3.5 stroke-[2]" aria-hidden />
        {label}
      </span>
    );
  }
  return (
    <span className={cn("inline-flex h-5 items-center gap-1 rounded-full px-2 text-[11px] font-medium whitespace-nowrap", STATUS_CLASS[kind], className)}>
      <Icon className="size-3 stroke-[2]" aria-hidden />
      {label}
    </span>
  );
}
