"use client";
/**
 * HX-04 (helper.md §4.2, §8, §12): the card frame. A `--fill-3` well with a hairline edge (no glass on glass), 16 px
 * padding, 12 px gap; the title is the group's label; actions wrap and are 44 px tall on touch (48 px for the primary
 * on phones). Risk accent: R2 shows the "Etkilenenler" line, R3 hand-overs a warning strip (rendered by the cards).
 */
import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function HelperCardFrame({
  title,
  children,
  actions,
  testId,
  className,
  tone = "default",
}: {
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  testId: string;
  className?: string;
  tone?: "default" | "done" | "muted";
}) {
  const id = useId();
  return (
    <div
      role="group"
      aria-labelledby={title ? id : undefined}
      data-testid={testId}
      data-tone={tone}
      className={cn("helper-card flex min-w-0 flex-col gap-3 rounded-(--radius-md) bg-fill-3 p-4 edge-hairline forced-colors:border forced-colors:border-[CanvasText]", tone === "muted" && "opacity-80", className)}
    >
      {title ? (
        <p id={id} className="type-headline text-label-1">
          {title}
        </p>
      ) : null}
      {children}
      {actions ? <div className="flex flex-wrap items-center gap-2 max-sm:flex-col max-sm:items-stretch">{actions}</div> : null}
    </div>
  );
}

/** One label / value line (preview rows, facts). */
export function CardLine({ label, value, tone }: { label: ReactNode; value: ReactNode; tone?: "ok" | "warn" | "bad" | "info" }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 type-callout">
      <dt className="text-label-2">{label}</dt>
      <dd className={cn("min-w-0 text-right font-medium text-label-1", tone === "warn" && "text-status-warning-fg", tone === "bad" && "text-status-infeasible-fg", tone === "ok" && "text-status-feasible-fg")}>{value}</dd>
    </div>
  );
}
