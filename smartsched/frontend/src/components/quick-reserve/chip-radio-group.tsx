"use client";
/**
 * W3-SLOT (quick-reserve.md §10): a roving-tabindex radiogroup of chips with disabled-with-reason items. Tab enters on
 * the selected item; ←/→ (↑/↓ too) move and select, Home/End jump; disabled items stay reachable (`aria-disabled`) and
 * say why in their accessible name, but are never selected. 44 px on coarse pointers; the row scrolls on its own
 * (never the page) on phones and wraps on wider screens. No motion on select (a frequent action, motion.md §2).
 */
import { Check } from "lucide-react";
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ChipItem<V extends string> {
  value: V;
  label: ReactNode;
  /** second line (time under a period name) */
  sub?: ReactNode;
  /** the full accessible name (defaults to the visible text) */
  name?: string;
  disabled?: boolean;
  testId?: string;
}

export function ChipRadioGroup<V extends string>({
  label,
  items,
  value,
  onChange,
  onCommit,
  className,
  testId,
}: {
  label: string;
  items: readonly ChipItem<V>[];
  value: V | null;
  onChange: (v: V) => void;
  /** Enter on an item (after selecting it) */
  onCommit?: (v: V) => void;
  className?: string;
  testId?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const stop = items.some((i) => i.value === value) ? value : (items.find((i) => !i.disabled)?.value ?? items[0]?.value);
  const focusAt = (i: number) => {
    const el = ref.current?.querySelectorAll<HTMLButtonElement>("[role=radio]")[i];
    el?.focus();
    el?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    const item = items[i];
    if (item && !item.disabled) onChange(item.value);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const last = items.length - 1;
    const next = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: last }[e.key];
    if (next !== undefined) {
      e.preventDefault();
      focusAt(next > last ? 0 : next < 0 ? last : next);
    } else if (e.key === "Enter" && onCommit && !items[i]?.disabled) {
      e.preventDefault();
      onChange(items[i]!.value);
      onCommit(items[i]!.value);
    }
  };
  return (
    <div
      ref={ref}
      role="radiogroup"
      aria-label={label}
      data-testid={testId}
      className={cn("-mx-1 flex gap-2 overflow-x-auto overscroll-x-contain px-1 py-1 scrollbar-thin sm:flex-wrap sm:overflow-visible", className)}
    >
      {items.map((item, i) => {
        const checked = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            role="radio"
            aria-checked={checked}
            aria-disabled={item.disabled || undefined}
            aria-label={item.name}
            tabIndex={item.value === stop ? 0 : -1}
            onClick={() => !item.disabled && onChange(item.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            data-testid={item.testId}
            data-checked={checked || undefined}
            className={cn(
              "relative inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1 text-left whitespace-nowrap select-none outline-hidden pointer-coarse:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-(--focus)",
              checked ? "bg-tint-soft font-semibold text-tint-text inset-ring-2 inset-ring-(--accent)" : "bg-fill-2 text-label-1 inset-ring inset-ring-(--hairline) hover:bg-fill-1",
              item.disabled && "cursor-not-allowed bg-fill-3 text-label-3 hover:bg-fill-3",
            )}
          >
            {checked ? <Check className="size-3.5 shrink-0 stroke-[2.5]" aria-hidden /> : null}
            <span className="flex flex-col leading-tight">
              <span className="type-callout">{item.label}</span>
              {item.sub ? <span className={cn("type-caption tabular-nums", checked ? "text-tint-text" : "text-label-2", item.disabled && "text-label-3")}>{item.sub}</span> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}
