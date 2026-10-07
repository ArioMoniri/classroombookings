"use client";

import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { animate, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

export interface StatTileProps {
  label: string;
  value: number | string;
  format?: (n: number) => string;
  delta?: { value: number; goodDirection: "up" | "down"; label: string };
  footnote?: string;
  href: string;
  ariaLabel?: string;
  tone?: "default" | "feasible" | "infeasible" | "warning";
}

function TickerValue({ value, format }: { value: number; format: (n: number) => string }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduce) {
      el.textContent = format(value);
      return;
    }
    const controls = animate(0, value, { duration: 0.24, ease: "easeOut", onUpdate: (v) => (el.textContent = format(v)) });
    return () => controls.stop();
  }, [value, format, reduce]);
  return <span ref={ref}>{format(value)}</span>;
}

export function StatTile({ label, value, format = (n) => String(Math.round(n)), delta, footnote, href, ariaLabel, tone = "default" }: StatTileProps) {
  const DeltaIcon = delta ? (delta.value > 0 ? ArrowUp : delta.value < 0 ? ArrowDown : Minus) : null;
  const good = delta ? (delta.value === 0 ? null : (delta.value > 0) === (delta.goodDirection === "up")) : null;
  return (
    <Link
      href={href}
      aria-label={ariaLabel ?? `${label}: ${value}`}
      className={cn(
        "flex min-h-[140px] flex-col justify-between rounded-xl border bg-card p-4 outline-none transition-shadow hover:shadow-elev-1 focus-visible:ring-2 focus-visible:ring-ring",
        tone === "feasible" && "border-status-feasible-border",
        tone === "infeasible" && "border-status-infeasible-border",
        tone === "warning" && "border-status-warning-border",
      )}
    >
      <p className="text-xs font-medium uppercase tracking-[0.02em] text-muted-foreground">{label}</p>
      <p className="text-3xl font-bold tabular-nums tracking-[-0.01em]">{typeof value === "number" ? <TickerValue value={value} format={format} /> : value}</p>
      <div className="flex items-center gap-2 text-xs">
        {delta && DeltaIcon ? (
          <span className={cn("inline-flex items-center gap-0.5 font-medium", good === null ? "text-subtle-foreground" : good ? "text-status-feasible-fg" : "text-status-infeasible-fg")}>
            <DeltaIcon className="size-3" aria-hidden /> {delta.label}
          </span>
        ) : null}
        {footnote ? <span className="truncate text-subtle-foreground">{footnote}</span> : null}
      </div>
    </Link>
  );
}
