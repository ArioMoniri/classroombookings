"use client";
/**
 * Inset translucent sidebar (calendar.md §5.2): term + run, mini-month (term week numbers, today circle,
 * selected week row, one heat dot per day), filters as quiet sections with counts and reset (Wix #25),
 * the unplaced tray, compare, and a legend drawn with real chips. Chrome material (rule G1).
 */
import { ChevronLeft, ChevronRight, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { forwardRef, useMemo, useState } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n/provider";
import { dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { ScheduleRun, Term } from "@/lib/api/schemas";
import { chipVars } from "./event-chip";
import { monthGrid, weekDayOf } from "./model/dates";
import { CAPACITY_BUCKETS, EMPTY_FILTERS, activeFilterCount, type CalendarFilters, type StatusFilter } from "./model/filters";
import type { HeatValue } from "./model/heat";
import type { CalendarModel } from "./model/index-model";
import { harmonised } from "./model/harmonise";
import { runOptionLabel } from "./model/run-label";
import { BareButton } from "@/components/shell/bare-button";
import { Input } from "@/components/ui/input";

export interface CalendarSidebarProps {
  model: CalendarModel;
  term: Term | undefined;
  runs: ScheduleRun[];
  runId: number;
  onRun: (id: number) => void;
  week: number;
  day: number;
  onPickDate: (week: number, day: number) => void;
  heat: Map<string, HeatValue>;
  todayIso: string;
  filters: CalendarFilters;
  onFilters: (f: CalendarFilters) => void;
  counts: { slots: Map<number, number>; buildings: Map<string, number>; conflicts: number; warnings: number; locked: number };
  compare: number | null;
  onCompare: (id: number | null) => void;
  ghosts: boolean;
  onGhosts: (v: boolean) => void;
  className?: string;
  /** the run shown: its API count of unplaced classes is the one the sidebar titles with (round-1 R1-S-16) */
  run?: ScheduleRun;
  /** Enter in the search: focus the first matching chip (round-1 R1-S-26) */
  onSearchEnter?: () => void;
  /** set when the sidebar floats over the board (narrow windows): a close button, and Esc closes it */
  onClose?: () => void;
  /** the phone sheet (round-3 R3-M-05): no mini month (the day strip and the week swipe do that), 44 px rows and
   *  chips, a 16 px search, no glass card of its own */
  compact?: boolean;
  style?: React.CSSProperties;
}

function Section({ title, onReset, children, count, compact }: { title: string; onReset?: () => void; children: React.ReactNode; count?: number; compact?: boolean }) {
  const { t } = useI18n();
  return (
    <section className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-1">
        <h3 className="type-caption font-semibold text-label-3">{title}{count ? ` · ${count}` : ""}</h3>
        {onReset ? (
          <BareButton onClick={onReset} className={cn("flex items-center gap-1 rounded-full px-1.5 type-caption text-label-2 hover:text-label-1", compact && "min-h-11 px-3")} aria-label={`${t("calendar.sidebar.reset")} ${title}`}>
            <RotateCcw className="size-3" aria-hidden />
          </BareButton>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function MiniMonth({ model, week, day, heat, todayIso, onPick }: { model: CalendarModel; week: number; day: number; heat: Map<string, HeatValue>; todayIso: string; onPick: (w: number, d: number) => void }) {
  const { t, locale } = useI18n();
  const start = model.index.weeks.find((w) => w.index === week)?.start_date ?? model.index.weeks[0]?.start_date ?? todayIso;
  const [month, setMonth] = useState(start.slice(0, 7));
  const [y, m] = month.split("-").map(Number);
  const cells = useMemo(() => monthGrid(y, m), [y, m]);
  const title = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, 1)));
  const shift = (n: number) => {
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    setMonth(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  };
  const rows: string[][] = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
  return (
    <div className="px-1">
      <div className="mb-1 flex items-center justify-between">
        <span className="type-callout font-semibold capitalize">{title}</span>
        <span className="flex">
          <Button variant="ghost" size="icon-xs" aria-label={t("calendar.nav.prev")} onClick={() => shift(-1)}><ChevronLeft /></Button>
          <Button variant="ghost" size="icon-xs" aria-label={t("calendar.nav.next")} onClick={() => shift(1)}><ChevronRight /></Button>
        </span>
      </div>
      <table className="w-full table-fixed text-center type-caption tabular-nums" role="grid" aria-label={t("calendar.sidebar.miniMonth")}>
        <thead>
          <tr className="text-label-3">
            <th className="w-6 font-medium" aria-label={t("calendar.scrubber")}>{locale === "tr" ? "H" : "W"}</th>
            {[1, 2, 3, 4, 5, 6, 7].map((d) => <th key={d} className="font-medium">{dayName(d, locale, "short").slice(0, 2)}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const wk = r.map((iso) => weekDayOf(model.index.weeks, iso)).find((x) => x)?.week ?? null;
            const selected = wk === week;
            const exam = model.index.weeks.find((w) => w.index === wk)?.kind === "EXAM";
            return (
              <tr key={r[0]} className={cn(selected && "bg-tint-soft")}>
                <td className="text-2xs pointer-coarse:type-caption text-label-3">{wk ?? ""}{exam ? <span className="block text-2xs pointer-coarse:type-caption leading-none">S</span> : null}</td>
                {r.map((iso) => {
                  const pos = weekDayOf(model.index.weeks, iso);
                  const inTerm = !!pos && model.weeks.includes(pos.week);
                  const h = pos ? heat.get(`${pos.week}:${pos.day}`) : undefined;
                  const occ = h?.occupancy ?? 0;
                  const dot = !inTerm || occ <= 0 ? 0 : occ < 0.4 ? 1 : occ <= 0.75 ? 2 : 3;
                  const isToday = iso === todayIso;
                  const isSel = pos && pos.week === week && pos.day === day;
                  return (
                    <td key={iso} className="p-0">
                      <BareButton
                        disabled={!inTerm}
                        onClick={() => pos && onPick(pos.week, pos.day)}
                        aria-current={isToday ? "date" : undefined}
                        aria-pressed={!!isSel}
                        aria-label={`${iso}${inTerm ? `, ${t("calendar.sidebar.heatDot", { p: Math.round(occ * 100), c: h?.conflicts ?? 0 })}` : ""}`}
                        className={cn("relative mx-auto flex size-7 flex-col items-center justify-center rounded-full", Number(iso.slice(5, 7)) !== m && "text-label-3", !inTerm && "text-label-3", isToday && "bg-tint font-semibold text-tint-foreground", isSel && !isToday && "edge-tint")}
                        title={inTerm ? t("calendar.sidebar.heatDot", { p: Math.round(occ * 100), c: h?.conflicts ?? 0 }) : undefined}
                      >
                        {Number(iso.slice(8))}
                        {dot ? <span aria-hidden className={cn("absolute bottom-0.5 rounded-full", isToday ? "bg-tint-foreground" : "bg-label-3")} style={{ width: dot + 1, height: dot + 1 }} /> : null}
                      </BareButton>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The run's own unplaced count: the backend's truth first, then `stats.unplaced`, then total − placed. */
export function unplacedCount(run: ScheduleRun | undefined): number | null {
  if (!run) return null;
  const stats = (run.stats_detail ?? run.stats) as Record<string, unknown>;
  const truth = stats.truth && typeof stats.truth === "object" ? (stats.truth as Record<string, unknown>) : null;
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const fromTruth = num(truth?.unplaced);
  if (fromTruth !== null) return fromTruth;
  const direct = num(run.stats.unplaced);
  if (direct !== null) return direct;
  const placed = num(run.stats.placed);
  const total = num(run.stats.events_total);
  return placed !== null && total !== null ? Math.max(0, total - placed) : null;
}

export const CalendarSidebar = forwardRef<HTMLInputElement, CalendarSidebarProps>(function CalendarSidebar(p, searchRef) {
  const { t, locale } = useI18n();
  const f = p.filters;
  const set = (patch: Partial<CalendarFilters>) => p.onFilters({ ...f, ...patch });
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const tags = useMemo(() => [...new Set(p.model.rooms.flatMap((r) => r.tags))].sort(), [p.model.rooms]);
  const faculties = p.model.index.faculties.filter((x) => (p.counts.slots.get(x.slot) ?? 0) > 0);
  const slots = [...new Set(faculties.map((x) => x.slot))];
  const statusOpts: { v: StatusFilter; label: string; n: number }[] = [
    { v: "conflict", label: t("calendar.state.conflict"), n: p.counts.conflicts },
    { v: "warning", label: t("calendar.state.warning"), n: p.counts.warnings },
    { v: "locked", label: t("calendar.state.locked"), n: p.counts.locked },
  ];
  const capIdx = Math.max(0, CAPACITY_BUCKETS.findIndex((c) => c === f.minCap));
  const mixedKinds = new Set(p.runs.map((r) => r.kind)).size > 1;
  // one unplaced count, the API's (`stats.unplaced`, the run report's number); the list may hold more rows (R1-S-16)
  const apiUnplaced = unplacedCount(p.run);
  const runLabels = new Map(p.runs.map((r) => [r.id, runOptionLabel(r, t, mixedKinds)]));
  const c = p.compact === true;
  return (
    <aside
      aria-label={t("calendar.sidebar.label")}
      className={cn(c ? "flex min-h-0 flex-col gap-5 overflow-y-auto px-4 pt-2 pb-4 text-label-1 [&_[data-slot=chip]>button]:min-h-11 [&_[data-slot=chip]>button]:px-3.5 [&_[data-slot=chip]>button]:type-callout" : "glass-chrome flex min-h-0 flex-col gap-4 overflow-y-auto rounded-2xl p-3 text-label-1", p.className)}
      data-glass={c ? undefined : "chrome"}
      data-compact={c ? "true" : undefined}
      style={p.style}
      data-testid="calendar-sidebar"
    >
      <div className="flex flex-col gap-1.5 px-1">
        <div className="flex items-start justify-between gap-2">
          <p className="type-headline" data-testid="sidebar-term">{p.term?.name ?? ""}</p>
          {p.onClose ? (
            <IconButton size={c ? "lg" : "sm"} variant="ghost" label={t("calendar.sidebar.close")} onClick={p.onClose} data-testid="sidebar-close">
              <X aria-hidden />
            </IconButton>
          ) : null}
        </div>
        <label className="flex flex-col gap-0.5 type-caption font-semibold text-label-3">
          {t("calendar.sidebar.run")}
          {/* short option text (weeks as ranges, kind only when both kinds are listed); the full text is the tooltip */}
          <select className="h-8 w-full min-w-0 truncate rounded-lg bg-fill-2 px-2 type-callout font-medium text-label-1 pointer-coarse:h-11 max-md:pointer-coarse:text-base" value={p.runId} title={runLabels.get(p.runId)?.full} onChange={(e) => p.onRun(Number(e.target.value))} data-testid="run-picker">
            {p.runs.map((r) => (
              <option key={r.id} value={r.id} title={runLabels.get(r.id)?.full}>
                {runLabels.get(r.id)?.short}
              </option>
            ))}
          </select>
        </label>
      </div>
      {c ? null : <MiniMonth model={p.model} week={p.week} day={p.day} heat={p.heat} todayIso={p.todayIso} onPick={p.onPickDate} />}
      <Input
        ref={searchRef}
        value={f.query}
        onChange={(e) => set({ query: e.target.value })}
        placeholder={t("calendar.sidebar.search")}
        aria-label={t("calendar.sidebar.search")}
        onKeyDown={(e) => {
          if (e.key === "Enter" && f.query.trim()) {
            e.preventDefault();
            p.onSearchEnter?.();
          }
        }}
        data-testid="calendar-search"
        className={c ? "min-h-11 text-base" : undefined}
        enterKeyHint={c ? "search" : undefined}
      />
      <Section compact={c} title={t("calendar.sidebar.buildings")} onReset={f.buildings.length ? () => set({ buildings: [] }) : undefined}>
        <div className="flex flex-wrap gap-1 px-1">
          {p.model.buildings.map((b) => (
            <Chip key={b} size="sm" selected={f.buildings.includes(b)} onSelectedChange={() => set({ buildings: toggle(f.buildings, b) })}>
              {b} <span className="text-label-3 tabular-nums">{p.model.rooms.filter((r) => r.building === b).length}</span>
            </Chip>
          ))}
        </div>
      </Section>
      <Section compact={c} title={t("calendar.sidebar.faculties")} onReset={f.slots.length ? () => set({ slots: [] }) : undefined}>
        <ul className="flex flex-col" title={t("calendar.sidebar.isolateHint")}>
          {slots.map((slot) => {
            const names = faculties.filter((x) => x.slot === slot).map((x) => x.name);
            const on = f.slots.length === 0 || f.slots.includes(slot);
            return (
              <li key={slot}>
                <BareButton
                  aria-pressed={f.slots.includes(slot)}
                  onClick={(e) => set({ slots: e.altKey ? (f.slots.length === 1 && f.slots[0] === slot ? [] : [slot]) : toggle(f.slots, slot) })}
                  className={cn("flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left type-footnote hover:bg-fill-2", c && "min-h-11 type-callout", !on && "opacity-50")}
                >
                  <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: `var(--fac-${slot}-bar)` }} />
                  <span className="min-w-0 flex-1 truncate" title={names.join(", ")}>{names[0]}{names.length > 1 ? ` +${names.length - 1}` : ""}</span>
                  <span className="type-caption text-label-3 tabular-nums">{p.counts.slots.get(slot) ?? 0}</span>
                </BareButton>
              </li>
            );
          })}
        </ul>
      </Section>
      {tags.length ? (
        <Section compact={c} title={t("calendar.sidebar.tags")} onReset={f.tags.length ? () => set({ tags: [] }) : undefined}>
          <div className="flex flex-wrap gap-1 px-1">
            {tags.map((tg) => <Chip key={tg} size="sm" selected={f.tags.includes(tg)} onSelectedChange={() => set({ tags: toggle(f.tags, tg) })}>{tg}</Chip>)}
          </div>
        </Section>
      ) : null}
      <Section compact={c} title={t("calendar.sidebar.status")} onReset={f.status.length ? () => set({ status: [] }) : undefined}>
        <div className="flex flex-wrap gap-1 px-1">
          {statusOpts.filter((s) => s.n > 0 || f.status.includes(s.v)).map((s) => (
            <Chip key={s.v} size="sm" selected={f.status.includes(s.v)} onSelectedChange={() => set({ status: toggle(f.status, s.v) })}>
              {s.label} <span className="text-label-3 tabular-nums">{s.n}</span>
            </Chip>
          ))}
        </div>
      </Section>
      <Section compact={c} title={`${t("calendar.sidebar.capacity")} ${f.minCap || ""}`} onReset={f.minCap ? () => set({ minCap: 0 }) : undefined}>
        {/* a <label>: on the phone sheet the row is the slider's 44 px target (M-02 measures the label box) */}
        <label className={cn("block px-2", c && "flex min-h-11 items-center")}>
          <Slider min={0} max={CAPACITY_BUCKETS.length} step={1} value={[f.minCap ? capIdx + 1 : 0]} onValueChange={(v) => {
            const i = Array.isArray(v) ? v[0] : v;
            set({ minCap: i ? CAPACITY_BUCKETS[i - 1] : 0 });
          }} aria-label={t("calendar.sidebar.capacity")} className={c ? "w-full" : undefined} />
        </label>
      </Section>
      {p.model.unplaced.length || apiUnplaced ? (
        <Section compact={c} title={t("calendar.sidebar.unplaced", { n: apiUnplaced ?? p.model.unplaced.length })}>
          {apiUnplaced !== null && p.model.unplaced.length > apiUnplaced ? (
            // the index also lists requests the solver never saw (left out, no time): say so instead of a second count
            <p className="px-1 type-caption text-label-3" data-testid="unplaced-extra">{t("calendar.sidebar.unplacedExtra", { n: p.model.unplaced.length - apiUnplaced })}</p>
          ) : null}
          <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto px-1">
            {p.model.unplaced.slice(0, 60).map((u) => (
              <li key={u.mr}>
                <Link href={`/classes?view=unplaced&id=${u.mr}`} className={cn("cal-unplaced flex flex-col px-2 py-1 type-footnote hover:bg-fill-2", c && "min-h-11 justify-center")} style={{ ...chipVars(u.slot), color: "var(--chip-ink)" }}>
                  <span className="font-semibold">{u.label}</span>
                  <span className="truncate type-caption opacity-80">{u.size} · {u.room_text ?? ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section compact={c} title={t("calendar.sidebar.compare")}>
        <div className="flex flex-col gap-2 px-1">
          <select className="h-8 rounded-lg bg-fill-2 px-2 type-callout pointer-coarse:h-11 max-md:pointer-coarse:text-base" value={p.compare ?? ""} onChange={(e) => p.onCompare(e.target.value ? Number(e.target.value) : null)} aria-label={t("calendar.compare.pick")}>
            <option value="">{t("calendar.sidebar.compareNone")}</option>
            {p.runs.filter((r) => r.id !== p.runId && r.kind === p.model.index.run.kind).map((r) => <option key={r.id} value={r.id}>{t("glass.shell.runShort", { id: r.id })}</option>)}
          </select>
          {p.compare !== null ? (
            <label className={cn("flex items-center gap-2 type-footnote", c && "min-h-11 type-callout")}><Switch checked={p.ghosts} onCheckedChange={p.onGhosts} />{t("calendar.sidebar.ghosts")}</label>
          ) : null}
        </div>
      </Section>
      <Section compact={c} title={t("calendar.sidebar.legend")}>
        <ul className="flex flex-col gap-1.5 px-1 type-footnote">
          {[
            { label: t("calendar.state.placed"), attrs: {} },
            { label: t("calendar.state.locked"), attrs: { "data-locked": "true" } },
            { label: t("calendar.state.conflict"), attrs: { "data-conflict": "true" } },
            { label: t("calendar.state.selected"), attrs: { "data-selected": "true" } },
          ].map((x) => (
            <li key={x.label} className="flex items-center gap-2">
              <span className="cal-chip" style={{ ...chipVars(1), position: "relative", width: 44, height: 18 }} {...x.attrs} aria-hidden />
              {x.label}
            </li>
          ))}
          <li className="flex items-center gap-2"><span className="cal-block" style={{ position: "relative", width: 44, height: 18 }} aria-hidden />{t("calendar.state.preoccupied")}</li>
          <li className="flex items-center gap-2"><span className="cal-chip cal-booking" style={{ position: "relative", width: 44, height: 18 }} aria-hidden />{t("calendar.state.booking")}</li>
          <li className="flex items-center gap-2"><span className="cal-ghost" style={{ position: "relative", width: 44, height: 18 }} aria-hidden />{harmonised(t, locale, "calendar.state.ghost", { run: p.compare ?? "…" })}</li>
        </ul>
      </Section>
      {activeFilterCount(f) ? (
        <Button variant="ghost" size="sm" className={c ? "min-h-11" : undefined} onClick={() => p.onFilters(EMPTY_FILTERS)}>{t("calendar.empty.clearFilters")}</Button>
      ) : null}
    </aside>
  );
});
