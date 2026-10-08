"use client";

import { motion, useReducedMotion } from "motion/react";
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  /** shown as the native tooltip (e.g. why an option is disabled) */
  title?: string;
  testId?: string;
}

/**
 * Accessible segmented control (`role="radiogroup"`, roving tabindex, arrow keys) with a sliding
 * indicator (`--spring-drop`-like spring, removed under reduced motion). Pattern: beUI motion tabs,
 * re-implemented.
 */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  labelledBy,
  describedBy,
  size = "md",
  className,
  testId,
}: {
  value: T | null;
  options: readonly SegmentOption<T>[];
  onChange: (v: T) => void;
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  size?: "sm" | "md";
  className?: string;
  testId?: string;
}) {
  const reduce = useReducedMotion();
  const group = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const enabled = options.map((o, i) => (o.disabled ? -1 : i)).filter((i) => i >= 0);
  const current = options.findIndex((o) => o.value === value);
  const focusIndex = current >= 0 ? current : (enabled[0] ?? 0);

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const dir = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const pos = enabled.indexOf(i);
    const next = enabled[(pos + dir + enabled.length) % enabled.length];
    if (next === undefined) return;
    refs.current[next]?.focus();
    onChange(options[next].value);
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      data-testid={testId}
      className={cn("relative inline-flex max-w-full flex-wrap items-stretch rounded-lg border bg-muted/40 p-0.5", className)}
    >
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={o.disabled}
            title={o.title}
            tabIndex={i === focusIndex ? 0 : -1}
            data-testid={o.testId}
            onKeyDown={(e) => onKey(e, i)}
            onClick={() => onChange(o.value)}
            className={cn(
              "relative z-0 min-w-0 flex-1 rounded-md px-2.5 text-center leading-tight outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-45 pointer-coarse:min-h-11",
              size === "sm" ? "min-h-7 py-1 text-xs" : "min-h-8 py-1.5 text-sm",
              on ? "font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {on ? (
              <motion.span
                layoutId={reduce ? undefined : `seg-${group}`}
                aria-hidden
                className="absolute inset-0 -z-10 rounded-md bg-primary"
                transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 40 }}
              />
            ) : null}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
