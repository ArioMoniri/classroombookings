"use client";
// Source: https://beui.dev (components/charts/status-bar/legend.tsx) via shadcn registry @beui/status-bar — https://github.com/starc007/ui-components
// Licence: MIT, Copyright (c) 2026 Saurabh Chauhan (full text: src/components/ui/LICENSES/beui-MIT.txt)
// Modified: yes — import paths re-pointed to src/components/ui/beui/*
import type { ComponentProps } from "react";
import { cn } from "@/components/ui/beui/lib/utils";
import { useStatusBar } from "./context";

export interface StatusBarLegendProps extends ComponentProps<"ul"> {
  showCounts?: boolean;
}

export function StatusBarLegend({
  className,
  showCounts = false,
  children,
  ...props
}: StatusBarLegendProps) {
  const { statuses, rows } = useStatusBar();
  return (
    <ul
      aria-label="Status legend"
      {...props}
      data-slot="status-bar-legend"
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground",
        className,
      )}
    >
      {children ??
        statuses.map((status) => (
          <li key={status.id} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="h-3 w-1.5 rounded-full"
              style={{ backgroundColor: status.color }}
            />
            <span>{status.label}</span>
            {showCounts ? (
              <span className="tabular-nums">
                ({rows.filter((row) => row.status.id === status.id).length})
              </span>
            ) : null}
          </li>
        ))}
    </ul>
  );
}
