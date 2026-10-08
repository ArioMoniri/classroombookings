"use client";
/**
 * Phone list (all-classes.md §13): opaque inset-grouped cells (12 px radius), sticky glass group headers,
 * swipe right → Kilitle, swipe left → Açıkla · Takvimde (motion `drag="x"`, snaps with springs.snappy);
 * every swipe action is also in the card's ⋯ menu (keyboard and screen readers).
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { Ellipsis, Lock, LockOpen, MessageSquareText, CalendarDays } from "lucide-react";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import Link from "next/link";
import { memo, useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { ClassRow } from "@/lib/api/classes";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { dayName, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { groupKey } from "./classes-model";

const REVEAL = 120;

function calendarHref(r: ClassRow, runId: number | null): string {
  const p = r.placement;
  return `/timetable?lens=week${p ? `&subject=room:${p.room_ids[0]}&day=${p.day}&sel=${p.assignment_ids[0]}` : ""}${runId ? `&run=${runId}` : ""}`;
}

const Card = memo(function Card({ r, runId, selected, selectMode, onOpen, onToggle, onLock, onExplain, readOnly }: { r: ClassRow; runId: number | null; selected: boolean; selectMode: boolean; onOpen: () => void; onToggle: () => void; onLock: () => void; onExplain: () => void; readOnly: boolean }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const x = useMotionValue(0);
  const p = r.placement;
  const hard = r.issues.some((i) => i.severity === "hard");
  const snap = (to: number) => (reduce ? x.set(to) : void animate(x, to, springs.snappy));
  // the action underlay is only painted while the card is off its rest position (no coloured hairline at the rounded corners)
  const underlay = useTransform(x, (v) => (Math.abs(v) < 0.5 ? 0 : 1));
  return (
    <div className="relative overflow-hidden rounded-xl" data-testid="classes-row" data-class-id={r.id}>
      <motion.div aria-hidden style={{ opacity: underlay }} className="absolute inset-0 flex items-stretch justify-between">
        <button type="button" tabIndex={-1} onClick={() => { onLock(); snap(0); }} className="flex w-[120px] items-center justify-center gap-1.5 bg-[var(--status-locked-solid,#5856d6)] text-[13px] font-semibold text-white">
          {p?.locked ? <LockOpen className="size-4" /> : <Lock className="size-4" />}
          {p?.locked ? t("calendar.insp.unlock") : t("classes.mobile.lock")}
        </button>
        <span className="flex">
          <button type="button" tabIndex={-1} onClick={() => { onExplain(); snap(0); }} className="flex w-[60px] flex-col items-center justify-center gap-0.5 bg-fill-1 text-[11px] font-semibold"><MessageSquareText className="size-4" />{t("classes.mobile.explain")}</button>
          <Link tabIndex={-1} href={calendarHref(r, runId)} className="flex w-[60px] flex-col items-center justify-center gap-0.5 bg-tint text-[11px] font-semibold text-tint-foreground"><CalendarDays className="size-4" />{t("classes.mobile.calendar")}</Link>
        </span>
      </motion.div>
      <motion.div
        drag={readOnly || selectMode ? false : "x"}
        dragConstraints={{ left: -REVEAL, right: REVEAL }}
        dragElastic={0.08}
        dragMomentum={false}
        style={{ x, touchAction: "pan-y" }}
        onDragEnd={(_, info) => snap(info.offset.x > 64 ? REVEAL : info.offset.x < -64 ? -REVEAL : 0)}
        className={cn("cal-canvas relative flex min-h-[72px] items-stretch gap-3 rounded-xl bg-(--mat-thick-solid) px-3 py-2.5", selected && "bg-tint-soft")}
      >
        {selectMode ? (
          <motion.input initial={reduce ? false : { x: -24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={springs.smooth} type="checkbox" checked={selected} onChange={onToggle} aria-label={`${r.course_code} ${t("classes.col.select")}`} className="mt-1 size-5 accent-(--accent)" />
        ) : null}
        <span aria-hidden className="w-[3px] shrink-0 rounded-full" style={{ background: `var(--fac-${r.faculty_slot}-bar)` }} />
        <button type="button" onClick={selectMode ? onToggle : onOpen} className="flex min-w-0 flex-1 flex-col gap-0.5 text-left">
          <span className="flex items-center justify-between gap-2">
            <span className="text-[15px] font-semibold">{r.course_code}{r.section ? ` §${r.section}` : ""}</span>
            {r.issues.length ? <span className={cn("text-[12px] font-medium tabular-nums", hard ? "text-status-infeasible-fg" : "text-status-warning-fg")}>{hard ? "▲" : "•"} {r.issues.length}</span> : null}
          </span>
          <span className="truncate text-[13px] text-label-2">{[r.program_name, r.class_years[0] ? (lang === "tr" ? `${r.class_years[0]}. sınıf` : `year ${r.class_years[0]}`) : null].filter(Boolean).join(" · ")}</span>
          {p ? (
            <span className="truncate text-[13px] tabular-nums">{dayName(p.day, locale, "short")} {periodRangeLabel(p.start_period, p.end_period)} · <span className="font-semibold">{p.room_codes.join(" + ")}</span> · {r.enrolment ?? "—"}/{p.capacity ?? "—"}</span>
          ) : r.placement_status === "unplaced" ? (
            <span className="truncate text-[13px] text-status-warning-fg">{t("classes.status.unplaced")}{r.definitive.room_codes.length || r.req.room_text ? ` · ${t("calendar.insp.requested")}: ${r.definitive.room_codes.join(" + ") || r.req.room_text}` : ""}</span>
          ) : (
            <span className="text-[13px] text-label-2">{t(`classes.status.${r.placement_status}`)}</span>
          )}
          {p?.locked || r.changed.length ? <span className="text-[12px] text-label-2">{[p?.locked ? t("calendar.state.locked") : null, r.changed.length ? t("classes.col.changed") : null].filter(Boolean).join(" · ")}</span> : null}
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("classes.mobile.actions", { code: r.course_code })} />}><Ellipsis /></DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {!readOnly && p ? <DropdownMenuItem onClick={onLock}>{p.locked ? t("calendar.insp.unlock") : t("classes.mobile.lock")}</DropdownMenuItem> : null}
            <DropdownMenuItem onClick={onExplain}>{t("calendar.insp.explain")}</DropdownMenuItem>
            <DropdownMenuItem render={<Link href={calendarHref(r, runId)} />}>{t("calendar.insp.openCalendar")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </motion.div>
    </div>
  );
});

export function ClassCards({ rows, group, runId, selection, selectMode, onToggle, onOpen, onLock, onExplain, readOnly }: { rows: ClassRow[]; group: string | null; runId: number | null; selection: ReadonlySet<number>; selectMode: boolean; onToggle: (id: number) => void; onOpen: (r: ClassRow) => void; onLock: (r: ClassRow) => void; onExplain: (r: ClassRow) => void; readOnly: boolean }) {
  const { t, locale } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const items = useMemo(() => {
    const out: ({ type: "h"; key: string; label: string; n: number } | { type: "r"; r: ClassRow })[] = [];
    let last = "";
    const counts = new Map<string, number>();
    if (group) for (const r of rows) counts.set(groupKey(r, group).key, (counts.get(groupKey(r, group).key) ?? 0) + 1);
    // same group order as the table (stable: the view's sort survives inside each group)
    const ordered = group ? rows.map((r, i) => ({ r, i, o: groupKey(r, group).order })).sort((a, b) => a.o.localeCompare(b.o, "tr") || a.i - b.i).map((x) => x.r) : rows;
    for (const r of ordered) {
      if (group) {
        const g = groupKey(r, group);
        if (g.key !== last) {
          last = g.key;
          out.push({ type: "h", key: g.key, label: g.label, n: counts.get(g.key) ?? 0 });
        }
      }
      out.push({ type: "r", r });
    }
    return out;
  }, [rows, group]);
  const heads = useMemo(() => items.map((it, i) => (it.type === "h" ? i : -1)).filter((i) => i >= 0), [items]);
  const v = useVirtualizer({
    count: items.length,
    getScrollElement: () => ref.current,
    estimateSize: (i) => (items[i].type === "h" ? 40 : 96),
    overscan: 6,
    rangeExtractor: (range) => {
      const prev = [...heads].reverse().find((i) => i <= range.startIndex) ?? -1;
      const out = new Set<number>(prev >= 0 ? [prev] : []);
      for (let i = range.startIndex; i <= range.endIndex; i++) out.add(i);
      return [...out].sort((a, b) => a - b);
    },
  });
  const firstVisible = v.range?.startIndex ?? 0;
  const activeHead = [...heads].reverse().find((i) => i <= firstVisible) ?? -1;
  return (
    <div ref={ref} className="min-h-0 flex-1 overflow-auto px-3 pb-24" data-testid="classes-cards">
      <div style={{ height: v.getTotalSize(), position: "relative" }}>
        {v.getVirtualItems().map((vi) => {
          const it = items[vi.index];
          const sticky = it.type === "h" && vi.index === activeHead;
          return (
            <div key={vi.key} ref={v.measureElement} data-index={vi.index} className={cn("inset-x-0", sticky ? "sticky top-0 z-10" : "absolute")} style={sticky ? { height: vi.size } : { transform: `translateY(${vi.start}px)` }}>
              {it.type === "h" ? (
                <p className="glass-thick rounded-lg px-3 py-2 text-[13px] font-semibold">{it.label === "—" ? t(group === "faculty" ? "classes.group.noFaculty" : "classes.group.none") : it.label} · {it.n.toLocaleString(locale)}</p>
              ) : (
                <div className="py-1">
                  <Card r={it.r} runId={runId} selected={selection.has(it.r.id)} selectMode={selectMode} onOpen={() => onOpen(it.r)} onToggle={() => onToggle(it.r.id)} onLock={() => onLock(it.r)} onExplain={() => onExplain(it.r)} readOnly={readOnly} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
