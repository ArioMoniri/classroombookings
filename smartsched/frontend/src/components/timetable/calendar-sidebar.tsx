"use client";
/**
 * Inset translucent sidebar (calendar.md §5.2): term + run, mini-month (term week numbers, today circle,
 * selected week row, one heat dot per day), filters as quiet sections with counts and reset (Wix #25),
 * the unplaced tray, compare, and a legend drawn with real chips. Chrome material (rule G1).
 */
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import Link from "next/link";
import { forwardRef, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
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
}

function Section({ title, onReset, children, count }: { title: string; onReset?: () => void; children: React.ReactNode; count?: number }) {
  const { t } = useI18n();
  return (
    <section className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-[11px] font-semibold text-label-3">{title}{count ? ` · ${count}` : ""}</h3>
        {onReset ? (
          <button type="button" onClick={onReset} className="flex items-center gap-1 rounded-full px-1.5 text-[11px] text-label-2 hover:text-label-1" aria-label={`${t("calendar.sidebar.reset")} ${title}`}>
            <RotateCcw className="size-3" aria-hidden />
          </button>
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
        <span className="text-[13px] font-semibold capitalize">{title}</span>
        <span className="flex">
          <Button variant="ghost" size="icon-xs" aria-label={t("calendar.nav.prev")} onClick={() => shift(-1)}><ChevronLeft /></Button>
          <Button variant="ghost" size="icon-xs" aria-label={t("calendar.nav.next")} onClick={() => shift(1)}><ChevronRight /></Button>
        </span>
      </div>
      <table className="w-full table-fixed text-center text-[11px] tabular-nums" role="grid" aria-label={t("calendar.sidebar.miniMonth")}>
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
                <td className="text-[10px] text-label-3">{wk ?? ""}{exam ? <span className="block text-[8px] leading-none">S</span> : null}</td>
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
                      <button
                        type="button"
                        disabled={!inTerm}
                        onClick={() => pos && onPick(pos.week, pos.day)}
                        aria-current={isToday ? "date" : undefined}
                        aria-pressed={!!isSel}
                        aria-label={`${iso}${inTerm ? `, ${t("calendar.sidebar.heatDot", { p: Math.round(occ * 100), c: h?.conflicts ?? 0 })}` : ""}`}
                        className={cn("relative mx-auto flex size-7 flex-col items-center justify-center rounded-full", Number(iso.slice(5, 7)) !== m && "text-label-4", !inTerm && "text-label-4", isToday && "bg-tint font-semibold text-tint-foreground", isSel && !isToday && "shadow-[inset_0_0_0_1.5px_var(--accent)]")}
                        title={inTerm ? t("calendar.sidebar.heatDot", { p: Math.round(occ * 100), c: h?.conflicts ?? 0 }) : undefined}
                      >
                        {Number(iso.slice(8))}
                        {dot ? <span aria-hidden className={cn("absolute bottom-0.5 rounded-full", isToday ? "bg-tint-foreground" : "bg-label-3")} style={{ width: dot + 1, height: dot + 1 }} /> : null}
                      </button>
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

export const CalendarSidebar = forwardRef<HTMLInputElement, CalendarSidebarProps>(function CalendarSidebar(p, searchRef) {
  const { t } = useI18n();
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
  return (
    <aside aria-label={t("calendar.sidebar.label")} className={cn("glass-chrome flex min-h-0 flex-col gap-4 overflow-y-auto rounded-2xl p-3 text-label-1", p.className)} data-glass="chrome" data-testid="calendar-sidebar">
      <div className="flex flex-col gap-1.5 px-1">
        <p className="type-headline">{p.term?.name ?? ""}</p>
        <label className="flex flex-col gap-0.5 text-[11px] font-semibold text-label-3">
          {t("calendar.sidebar.run")}
          <select className="h-8 rounded-lg bg-fill-2 px-2 text-[13px] font-medium text-label-1" value={p.runId} onChange={(e) => p.onRun(Number(e.target.value))} data-testid="run-picker">
            {p.runs.map((r) => (
              <option key={r.id} value={r.id}>
                #{r.id} · {r.kind === "EXAM" ? t("classes.kind.exams") : t("classes.kind.meetings")} · {t(`runs.status.${r.status}`)}{r.horizon === "WEEK" && r.horizon_params.weeks.length ? ` · ${t("calendar.nav.weekShort", { n: r.horizon_params.weeks.join(",") })}` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <MiniMonth model={p.model} week={p.week} day={p.day} heat={p.heat} todayIso={p.todayIso} onPick={p.onPickDate} />
      <input
        ref={searchRef}
        value={f.query}
        onChange={(e) => set({ query: e.target.value })}
        placeholder={t("calendar.sidebar.search")}
        aria-label={t("calendar.sidebar.search")}
        className="h-8 rounded-lg bg-fill-2 px-2.5 text-[13px] outline-none focus-visible:outline-2 focus-visible:outline-(--focus)"
        data-testid="calendar-search"
      />
      <Section title={t("calendar.sidebar.buildings")} onReset={f.buildings.length ? () => set({ buildings: [] }) : undefined}>
        <div className="flex flex-wrap gap-1 px-1">
          {p.model.buildings.map((b) => (
            <Chip key={b} size="sm" selected={f.buildings.includes(b)} onSelectedChange={() => set({ buildings: toggle(f.buildings, b) })}>
              {b} <span className="text-label-3 tabular-nums">{p.model.rooms.filter((r) => r.building === b).length}</span>
            </Chip>
          ))}
        </div>
      </Section>
      <Section title={t("calendar.sidebar.faculties")} onReset={f.slots.length ? () => set({ slots: [] }) : undefined}>
        <ul className="flex flex-col" title={t("calendar.sidebar.isolateHint")}>
          {slots.map((slot) => {
            const names = faculties.filter((x) => x.slot === slot).map((x) => x.name);
            const on = f.slots.length === 0 || f.slots.includes(slot);
            return (
              <li key={slot}>
                <button
                  type="button"
                  aria-pressed={f.slots.includes(slot)}
                  onClick={(e) => set({ slots: e.altKey ? (f.slots.length === 1 && f.slots[0] === slot ? [] : [slot]) : toggle(f.slots, slot) })}
                  className={cn("flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-[12px] hover:bg-fill-2", !on && "opacity-50")}
                >
                  <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: `var(--fac-${slot}-bar)` }} />
                  <span className="min-w-0 flex-1 truncate" title={names.join(", ")}>{names[0]}{names.length > 1 ? ` +${names.length - 1}` : ""}</span>
                  <span className="text-[11px] text-label-3 tabular-nums">{p.counts.slots.get(slot) ?? 0}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </Section>
      {tags.length ? (
        <Section title={t("calendar.sidebar.tags")} onReset={f.tags.length ? () => set({ tags: [] }) : undefined}>
          <div className="flex flex-wrap gap-1 px-1">
            {tags.map((tg) => <Chip key={tg} size="sm" selected={f.tags.includes(tg)} onSelectedChange={() => set({ tags: toggle(f.tags, tg) })}>{tg}</Chip>)}
          </div>
        </Section>
      ) : null}
      <Section title={t("calendar.sidebar.status")} onReset={f.status.length ? () => set({ status: [] }) : undefined}>
        <div className="flex flex-wrap gap-1 px-1">
          {statusOpts.filter((s) => s.n > 0 || f.status.includes(s.v)).map((s) => (
            <Chip key={s.v} size="sm" selected={f.status.includes(s.v)} onSelectedChange={() => set({ status: toggle(f.status, s.v) })}>
              {s.label} <span className="text-label-3 tabular-nums">{s.n}</span>
            </Chip>
          ))}
        </div>
      </Section>
      <Section title={`${t("calendar.sidebar.capacity")} ${f.minCap || ""}`} onReset={f.minCap ? () => set({ minCap: 0 }) : undefined}>
        <div className="px-2">
          <Slider min={0} max={CAPACITY_BUCKETS.length} step={1} value={[f.minCap ? capIdx + 1 : 0]} onValueChange={(v) => {
            const i = Array.isArray(v) ? v[0] : v;
            set({ minCap: i ? CAPACITY_BUCKETS[i - 1] : 0 });
          }} aria-label={t("calendar.sidebar.capacity")} />
        </div>
      </Section>
      {p.model.unplaced.length ? (
        <Section title={t("calendar.sidebar.unplaced", { n: p.model.unplaced.length })}>
          <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto px-1">
            {p.model.unplaced.slice(0, 60).map((u) => (
              <li key={u.mr}>
                <Link href={`/classes?view=unplaced&id=${u.mr}`} className="cal-unplaced flex flex-col px-2 py-1 text-[12px] hover:bg-fill-2" style={{ ...chipVars(u.slot), color: "var(--chip-ink)" }}>
                  <span className="font-semibold">{u.label}</span>
                  <span className="truncate text-[11px] opacity-80">{u.size} · {u.room_text ?? ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section title={t("calendar.sidebar.compare")}>
        <div className="flex flex-col gap-2 px-1">
          <select className="h-8 rounded-lg bg-fill-2 px-2 text-[13px]" value={p.compare ?? ""} onChange={(e) => p.onCompare(e.target.value ? Number(e.target.value) : null)} aria-label={t("calendar.compare.pick")}>
            <option value="">{t("calendar.sidebar.compareNone")}</option>
            {p.runs.filter((r) => r.id !== p.runId && r.kind === p.model.index.run.kind).map((r) => <option key={r.id} value={r.id}>Run #{r.id}</option>)}
          </select>
          {p.compare !== null ? (
            <label className="flex items-center gap-2 text-[12px]"><Switch checked={p.ghosts} onCheckedChange={p.onGhosts} />{t("calendar.sidebar.ghosts")}</label>
          ) : null}
        </div>
      </Section>
      <Section title={t("calendar.sidebar.legend")}>
        <ul className="flex flex-col gap-1.5 px-1 text-[12px]">
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
          <li className="flex items-center gap-2"><span className="cal-ghost" style={{ position: "relative", width: 44, height: 18 }} aria-hidden />{t("calendar.state.ghost", { run: p.compare ?? "…" })}</li>
        </ul>
      </Section>
      {activeFilterCount(f) ? (
        <Button variant="ghost" size="sm" onClick={() => p.onFilters(EMPTY_FILTERS)}>{t("calendar.empty.clearFilters")}</Button>
      ) : null}
    </aside>
  );
});
