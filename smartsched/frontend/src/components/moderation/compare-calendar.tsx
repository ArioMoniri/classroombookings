"use client";
/**
 * The optional calendar compare mode of the re-solve preview (motion.md §3.9 "Takvimde göster"): a week grid of
 * the changed classes only. Ghosts (dashed) sit at the old cells, moved chips at the new cells with an accent
 * ring, newly placed chips carry a "Yeni" tag. "Önce · Sonra" flips the chips between their cells: at most 12
 * moved chips travel (FLIP via `layoutId`), the rest swap instantly. `j`/`k` step through the changes with one
 * focus overlay (`layoutId="diff-focus"`). Unchanged classes are not drawn at all (never 1,300 layers).
 *
 * Reduced motion: no travel, the overlay jumps. Reduced transparency: ghosts are an opaque fill with a dashed
 * border instead of 40 % opacity. Every state is also text (cell caption "↗ Sal P4 · A 306'dan", live region).
 */
import { motion, LayoutGroup } from "motion/react";
import { useMemo, useState, type KeyboardEvent } from "react";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { DiffOut, Place } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce, useReducedTransparency } from "@/lib/motion";
import { dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { MAX_ANIMATED_MOVES, placeText } from "./moderation-model";

interface Chip {
  id: number;
  label: string;
  from: Place | null;
  to: Place | null;
  kind: "moved" | "new";
}

export function compareChips(d: DiffOut): Chip[] {
  return [
    ...d.moved.map<Chip>((m) => ({ id: m.request_id, label: m.label, from: m.from, to: m.to, kind: "moved" })),
    ...d.newly_placed.map<Chip>((m) => ({ id: m.request_id, label: m.label, from: null, to: m.to, kind: "new" })),
  ];
}

/** the grid's days and periods: just the span the changes touch (Mon–Fri at least) */
export function gridSpan(chips: readonly Chip[]): { days: number[]; first: number; last: number } {
  const places = chips.flatMap((c) => [c.from, c.to]).filter((p): p is Place => p !== null);
  const maxDay = Math.max(5, ...places.map((p) => p.day));
  const first = places.length ? Math.min(...places.map((p) => p.start_period)) : 1;
  const last = places.length ? Math.max(...places.map((p) => p.end_period)) : 10;
  return { days: Array.from({ length: maxDay }, (_, i) => i + 1), first, last };
}

export function CompareCalendar({ diff }: { diff: DiffOut }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const solid = useReducedTransparency();
  const chips = useMemo(() => compareChips(diff), [diff]);
  const span = useMemo(() => gridSpan(chips), [chips]);
  const [side, setSide] = useState<"before" | "after">("after");
  const [focus, setFocus] = useState(0);
  const travel = useMemo(() => new Set(chips.filter((c) => c.kind === "moved").slice(0, MAX_ANIMATED_MOVES).map((c) => c.id)), [chips]);
  const periods = Array.from({ length: span.last - span.first + 1 }, (_, i) => span.first + i);
  const focused = chips[Math.min(focus, chips.length - 1)];

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "j" || e.key === "ArrowRight") setFocus((f) => Math.min(chips.length - 1, f + 1));
    else if (e.key === "k" || e.key === "ArrowLeft") setFocus((f) => Math.max(0, f - 1));
    else return;
    e.preventDefault();
  };

  const placeOf = (c: Chip): Place | null => (side === "before" ? c.from : c.to);

  return (
    <section className="flex flex-col gap-2" aria-label={t("moderation.preview.calendar")} data-testid="compare-calendar">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl<"before" | "after">
          aria-label={t("moderation.preview.side")}
          size="sm"
          value={side}
          onValueChange={setSide}
          options={[
            { value: "before", label: t("moderation.preview.before") },
            { value: "after", label: t("moderation.preview.after") },
          ]}
        />
        <span className="type-footnote text-label-2 tabular-nums" aria-live="polite">
          {chips.length ? t("moderation.preview.step", { i: Math.min(focus, chips.length - 1) + 1, n: chips.length }) : t("moderation.preview.nothingMoved")}
          {focused ? ` · ${focused.label}: ${placeText(focused.from, lang)} → ${placeText(focused.to, lang)}` : ""}
        </span>
      </div>
      <div tabIndex={0} onKeyDown={onKey} aria-keyshortcuts="j k" className="overflow-auto rounded-xl border border-hairline bg-card outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-diff="on">
        <LayoutGroup id="compare">
          <div className="grid min-w-max" style={{ gridTemplateColumns: `3.5rem repeat(${span.days.length}, minmax(9rem,1fr))`, gridTemplateRows: `2rem repeat(${periods.length}, 2.75rem)` }}>
            <div />
            {span.days.map((d) => (
              <div key={d} className="sticky top-0 border-b border-hairline px-2 py-1 type-caption font-semibold text-label-2">{dayName(d, locale, "short")}</div>
            ))}
            {periods.map((p, row) => (
              <div key={p} className="border-r border-hairline px-1 type-caption text-label-3 tabular-nums" style={{ gridRow: row + 2, gridColumn: 1 }}>P{p}</div>
            ))}
            {/* ghosts at the old cells (moved chips only) */}
            {side === "after"
              ? chips.filter((c) => c.from && c.kind === "moved").map((c) => (
                  <motion.div
                    key={`ghost-${c.id}`}
                    aria-hidden
                    className={cn("pointer-events-none m-0.5 rounded-md border border-dashed border-label-3 px-1.5 py-0.5 type-caption text-label-2", solid ? "bg-fill-3" : "opacity-40")}
                    style={{ gridColumn: c.from!.day + 1, gridRow: `${c.from!.start_period - span.first + 2} / span ${c.from!.end_period - c.from!.start_period + 1}` }}
                    initial={reduce ? false : { opacity: 0 }}
                    animate={{ opacity: solid ? 1 : 0.4 }}
                    transition={reduce ? { duration: 0 } : tween.fadeIn}
                  >
                    {c.label}
                  </motion.div>
                ))
              : null}
            {chips.map((c, i) => {
              const p = placeOf(c);
              if (!p) return null;
              const animate = !reduce && travel.has(c.id);
              const isFocus = focused?.id === c.id;
              return (
                <motion.div
                  key={`chip-${c.id}-${animate ? "t" : side}`}
                  layoutId={animate ? `cmp-${c.id}` : undefined}
                  layout={animate ? "position" : false}
                  transition={springs.smooth}
                  onClick={() => setFocus(i)}
                  data-testid="compare-chip"
                  data-kind={c.kind}
                  className={cn("relative m-0.5 flex min-w-0 flex-col rounded-md bg-tint-soft px-1.5 py-0.5 type-caption text-label-1", c.kind === "moved" && side === "after" && "ring-2 ring-(--accent)")}
                  style={{ gridColumn: p.day + 1, gridRow: `${p.start_period - span.first + 2} / span ${p.end_period - p.start_period + 1}` }}
                >
                  {isFocus ? <motion.span layoutId="diff-focus" aria-hidden className="pointer-events-none absolute -inset-0.5 rounded-lg outline-2 outline-solid outline-(--focus)" transition={reduce ? { duration: 0 } : springs.snappy} /> : null}
                  <span className="truncate font-semibold">{c.label}</span>
                  <span className="truncate text-label-2">
                    {c.kind === "new" ? t("moderation.preview.newTag") : side === "after" && c.from ? `↗ ${placeText(c.from, lang)}` : p.rooms.join(" + ")}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </LayoutGroup>
      </div>
      {chips.length > MAX_ANIMATED_MOVES ? <p className="type-caption text-label-3">{t("moderation.preview.capNote", { n: MAX_ANIMATED_MOVES })}</p> : null}
    </section>
  );
}
