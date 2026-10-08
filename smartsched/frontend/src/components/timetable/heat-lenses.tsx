"use client";
/**
 * Ay (Month) and Dönem (Term) heat lenses (calendar.md §6.5, §6.6; wireframe calendar-term-heat.svg).
 * Opaque heat cells at 40 % strength with label-1 text only, explicit numbers (never colour alone),
 * one shared tooltip element, plain DOM (≤ 112 cells, or 4 × 98 when split by building).
 * Metric change = 180 ms background-colour cross-fade, no stagger (motion.md §3.2).
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { memo, useMemo, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Button } from "@/components/ui/button";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { dateOf, monthGrid, parseIso, weekDayOf, weekTypeKey } from "./model/dates";
import { countStep, heatStep, weeklyMean, type HeatMetric, type HeatValue } from "./model/heat";
import type { CalendarModel } from "./model/index-model";

const DAYS = [1, 2, 3, 4, 5, 6, 7];

export interface HeatLensProps {
  model: CalendarModel;
  heat: Map<string, HeatValue>;
  metric: HeatMetric;
  onMetric: (m: HeatMetric) => void;
  unplacedByDay: Map<string, number>;
  todayIso: string;
  onPick: (week: number, day: number) => void;
  compareOn: boolean;
}

function valueOf(h: HeatValue | undefined, metric: HeatMetric, unplaced: number): number {
  if (!h) return 0;
  if (metric === "occupancy") return h.occupancy;
  if (metric === "conflicts") return h.conflicts;
  if (metric === "changes") return h.changes;
  return unplaced;
}

function useMax(model: CalendarModel, heat: Map<string, HeatValue>, metric: HeatMetric, unplaced: Map<string, number>) {
  return useMemo(() => {
    let m = 0;
    for (const w of model.weeks) for (const d of DAYS) m = Math.max(m, valueOf(heat.get(`${w}:${d}`), metric, unplaced.get(`${w}:${d}`) ?? 0));
    return m;
  }, [model.weeks, heat, metric, unplaced]);
}

function MetricSwitch({ metric, onMetric, compareOn }: { metric: HeatMetric; onMetric: (m: HeatMetric) => void; compareOn: boolean }) {
  const { t } = useI18n();
  const options: { value: HeatMetric; label: string; disabled?: boolean }[] = [
    { value: "occupancy", label: t("calendar.heat.occupancy") },
    { value: "conflicts", label: t("calendar.heat.conflicts") },
    { value: "unplaced", label: t("calendar.heat.unplaced") },
    { value: "changes", label: t("calendar.heat.changes"), disabled: !compareOn },
  ];
  return <SegmentedGlass size="sm" aria-label={t("calendar.heat.metric")} options={options} value={metric} onValueChange={onMetric} />;
}

function cellText(metric: HeatMetric, v: number, t: ReturnType<typeof useI18n>["t"]): string {
  return metric === "occupancy" ? t("calendar.heat.cellShort", { p: Math.round(v * 100) }) : String(v);
}

/* ------------------------------------------------------------------ Term */

function TermHeatImpl(p: HeatLensProps & { onBrush: (weeks: [number, number] | null) => void; brush: [number, number] | null; currentWeek: number }) {
  const { t, locale } = useI18n();
  const [split, setSplit] = useState(false);
  const [asTable, setAsTable] = useState(false);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const [brushStart, setBrushStart] = useState<number | null>(null);
  const max = useMax(p.model, p.heat, p.metric, p.unplacedByDay);
  const step = (v: number) => (p.metric === "occupancy" ? heatStep(v) : countStep(v, max));
  const weeks = p.model.weeks;
  const weekInfo = new Map(p.model.index.weeks.map((w) => [w.index, w]));
  const buildings = p.model.buildings;

  const label = (w: number, d: number, v: HeatValue | undefined) => {
    const date = dateOf(p.model.index.weeks, w, d);
    const occ = v?.occupied ?? 0;
    const blk = v?.blocked ?? 0;
    return `${t("calendar.heat.cell", { w, date: date ? formatDate(date, locale, { day: "numeric", month: "long" }) : "", p: Math.round((v?.occupancy ?? 0) * 100), occ: occ + blk, cap: v?.capacity ?? 0, c: v?.conflicts ?? 0 })} · ${t("calendar.heat.split2", { a: Math.round((occ / Math.max(1, v?.capacity ?? 1)) * 100), b: Math.round((blk / Math.max(1, v?.capacity ?? 1)) * 100) })}`;
  };

  const onCellDown = (e: ReactPointerEvent<HTMLButtonElement>, w: number) => {
    if (e.shiftKey) {
      e.preventDefault();
      setBrushStart(w);
      p.onBrush([w, w]);
    }
  };

  const grid = (bld: string | null, cellW: number, cellH: number) => (
    <div role="grid" aria-label={bld ? t("calendar.buildingBand", { b: bld, n: p.model.rooms.filter((r) => r.building === bld).length }) : t("calendar.lens.term")} className="inline-grid gap-[3px]" style={{ gridTemplateColumns: `${bld ? "" : "88px "}repeat(7, ${cellW}px)${bld ? "" : " 120px"}` }} onPointerUp={() => setBrushStart(null)}>
      <div role="row" className="contents">
        {bld ? null : <span />}
        {DAYS.map((d) => (
          <span key={d} role="columnheader" className="text-center text-[11px] font-semibold text-label-2">{dayName(d, locale, "short")}</span>
        ))}
        {bld ? null : <span />}
      </div>
      {weeks.map((w) => {
        const info = weekInfo.get(w);
        const kind = weekTypeKey(info?.kind ?? "LECTURE");
        const brushed = p.brush && w >= p.brush[0] && w <= p.brush[1];
        const mean = weeklyMean(p.heat, w);
        return (
          <div key={w} role="row" className={cn("contents")}>
            {bld ? null : (
              <span role="rowheader" className={cn("flex items-center gap-1.5 pr-1 text-[12px] whitespace-nowrap", w === p.currentWeek && "font-semibold")}>
                <span className="font-semibold">{t("calendar.nav.weekShort", { n: w })}</span>
                <span className="text-label-2">{info?.start_date ? formatDate(info.start_date, locale) : ""}</span>
                {kind !== "lecture" ? <span className="rounded-full bg-fill-2 px-1.5 text-[10px] text-label-2">{t(`calendar.weekType.${kind}`)}</span> : null}
              </span>
            )}
            {DAYS.map((d) => {
              const v = p.heat.get(`${w}:${d}`);
              const raw = bld ? (v?.byBuilding[bld] ?? 0) : valueOf(v, p.metric, p.unplacedByDay.get(`${w}:${d}`) ?? 0);
              const metric = bld ? "occupancy" : p.metric;
              const s = metric === "occupancy" ? heatStep(raw) : step(raw);
              return (
                <button
                  key={d}
                  type="button"
                  role="gridcell"
                  className={cn("cal-heat flex items-center justify-center rounded-[6px] text-[11px] font-semibold tabular-nums outline-offset-1", brushed && "outline-2 outline-(--accent)", w === p.currentWeek && !bld && "ring-1 ring-(--hairline-strong)")}
                  data-step={s}
                  data-holiday={kind === "holiday" ? "true" : undefined}
                  style={{ width: cellW, height: cellH }}
                  aria-label={label(w, d, v)}
                  onPointerDown={(e) => onCellDown(e, w)}
                  onPointerEnter={(e) => {
                    if (brushStart !== null) p.onBrush([Math.min(brushStart, w), Math.max(brushStart, w)]);
                    const r = e.currentTarget.getBoundingClientRect();
                    setTip({ x: r.left + r.width / 2, y: r.top, text: label(w, d, v) });
                  }}
                  onPointerLeave={() => setTip(null)}
                  onClick={(e) => {
                    if (!e.shiftKey) p.onPick(w, d);
                  }}
                >
                  {cellW >= 36 ? cellText(metric, raw, t) : null}
                </button>
              );
            })}
            {bld ? null : (
              <span className="flex items-center gap-2 pl-2" aria-hidden>
                <span className="h-2 w-16 origin-left rounded-full bg-[var(--seq-3)]" style={{ transform: `scaleX(${Math.min(1, mean)})` }} />
                <span className="text-[11px] tabular-nums">{t("calendar.heat.cellShort", { p: Math.round(mean * 100) })}</span>
              </span>
            )}
          </div>
        );
      })}
      {bld ? null : (
        <div role="row" className="contents">
          <span className="text-[11px] text-label-2">{t("calendar.heat.dayAvg")}</span>
          {DAYS.map((d) => {
            const avg = weeks.reduce((s, w) => s + (p.heat.get(`${w}:${d}`)?.occupancy ?? 0), 0) / Math.max(1, weeks.length);
            return <span key={d} className="text-center text-[11px] font-semibold tabular-nums">{t("calendar.heat.cellShort", { p: Math.round(avg * 100) })}</span>;
          })}
          <span />
        </div>
      )}
    </div>
  );

  return (
    <div className="cal-canvas h-full overflow-auto px-4 py-4 sm:px-6" data-testid="term-heat">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <p className="mr-auto text-[12px] text-label-2">{t("calendar.heat.definition")}</p>
        <MetricSwitch metric={p.metric} onMetric={p.onMetric} compareOn={p.compareOn} />
        <label className="flex items-center gap-2 text-[12px] text-label-1"><Switch checked={split} onCheckedChange={setSplit} />{t("calendar.heat.split")}</label>
        <label className="flex items-center gap-2 text-[12px] text-label-1"><Switch checked={asTable} onCheckedChange={setAsTable} />{t("calendar.heat.asTable")}</label>
      </div>
      {asTable ? (
        <table className="w-full max-w-4xl text-[12px] tabular-nums">
          <caption className="sr-only">{t("calendar.lens.term")}</caption>
          <thead>
            <tr className="text-left text-label-2"><th className="py-1 pr-2 font-semibold">{t("calendar.scrubber")}</th>{DAYS.map((d) => <th key={d} className="px-2 font-semibold">{dayName(d, locale, "short")}</th>)}</tr>
          </thead>
          <tbody>
            {weeks.map((w) => (
              <tr key={w} className="hairline-b">
                <th scope="row" className="py-1 pr-2 text-left font-semibold">{t("calendar.nav.weekShort", { n: w })}</th>
                {DAYS.map((d) => {
                  const v = p.heat.get(`${w}:${d}`);
                  return <td key={d} className="px-2">{cellText(p.metric, valueOf(v, p.metric, p.unplacedByDay.get(`${w}:${d}`) ?? 0), t)}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      ) : split ? (
        <div className="flex flex-wrap gap-8">
          {grid(null, 40, 32)}
          {buildings.map((b) => (
            <div key={b}>
              <p className="mb-1 text-[12px] font-semibold">{t("calendar.buildingBand", { b, n: p.model.rooms.filter((r) => r.building === b).length })}</p>
              {grid(b, 22, 32)}
            </div>
          ))}
        </div>
      ) : (
        grid(null, 40, 32)
      )}
      <p className="mt-4 text-[11px] text-label-2">{t("calendar.heat.drill")}</p>
      <HeatLegend metric={p.metric} max={max} />
      {tip ? (
        <div role="tooltip" className="glass-thick pointer-events-none fixed z-50 max-w-[320px] -translate-x-1/2 -translate-y-full rounded-lg px-2.5 py-1.5 text-[12px] text-label-1" style={{ left: tip.x, top: tip.y - 6 }}>
          {tip.text}
        </div>
      ) : null}
    </div>
  );
}

function HeatLegend({ metric, max }: { metric: HeatMetric; max: number }) {
  const { t } = useI18n();
  const labels = metric === "occupancy" ? ["%0", "1–25", "26–50", "51–75", "76–90", "91–100"] : ["0", ...[1, 2, 3, 4, 5].map((i) => `≤ ${Math.ceil((max * i) / 5)}`)];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] text-label-2" aria-label={t("calendar.heat.legend")}>
      {labels.map((l, i) => (
        <span key={l + i} className="flex items-center gap-1">
          <span className="cal-heat inline-block size-3.5 rounded-[4px] shadow-[inset_0_0_0_1px_var(--hairline)]" data-step={i} />
          {l}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ Month */

function MonthHeatImpl(p: HeatLensProps & { month: string; onMonth: (m: string) => void }) {
  const { t, locale } = useI18n();
  const [y, m] = p.month.split("-").map(Number);
  const cells = useMemo(() => monthGrid(y, m), [y, m]);
  const max = useMax(p.model, p.heat, p.metric, p.unplacedByDay);
  const title = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(parseIso(`${p.month}-01`));
  const shift = (n: number) => {
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    p.onMonth(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  };
  const weekRows: string[][] = [];
  for (let i = 0; i < cells.length; i += 7) weekRows.push(cells.slice(i, i + 7));
  return (
    <div className="cal-canvas flex h-full flex-col overflow-auto px-4 py-4 sm:px-6" data-testid="month-heat">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.prev")} onClick={() => shift(-1)}><ChevronLeft /></Button>
        <h2 className="type-title-3 min-w-40 capitalize">{title}</h2>
        <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.next")} onClick={() => shift(1)}><ChevronRight /></Button>
        <div className="ml-auto"><MetricSwitch metric={p.metric} onMetric={p.onMetric} compareOn={p.compareOn} /></div>
      </div>
      <div role="grid" aria-label={title} className="grid min-h-0 flex-1 gap-1" style={{ gridTemplateColumns: "40px repeat(7, minmax(0, 1fr))", gridAutoRows: "minmax(88px, 1fr)" }}>
        <div role="row" className="contents">
          <span />
          {DAYS.map((d) => <span key={d} role="columnheader" className="self-end pb-1 text-[11px] font-semibold text-label-2">{dayName(d, locale, "short")}</span>)}
        </div>
        {weekRows.map((row) => {
          const wd = row.map((iso) => weekDayOf(p.model.index.weeks, iso));
          const w = wd.find((x) => x)?.week;
          return (
            <div key={row[0]} role="row" className="contents">
              <span role="rowheader" className="pt-1 text-[11px] font-semibold text-label-2">{w ? t("calendar.nav.weekShort", { n: w }) : ""}</span>
              {row.map((iso, i) => {
                const pos = wd[i];
                const inTerm = !!pos && p.model.weeks.includes(pos.week);
                const v = pos ? p.heat.get(`${pos.week}:${pos.day}`) : undefined;
                const raw = valueOf(v, p.metric, pos ? p.unplacedByDay.get(`${pos.week}:${pos.day}`) ?? 0 : 0);
                const s = !inTerm ? 0 : p.metric === "occupancy" ? heatStep(raw) : countStep(raw, max);
                const outMonth = Number(iso.slice(5, 7)) !== m;
                const today = iso === p.todayIso;
                const kind = pos ? weekTypeKey(p.model.index.weeks.find((x) => x.index === pos.week)?.kind ?? "LECTURE") : "lecture";
                return (
                  <button
                    key={iso}
                    type="button"
                    role="gridcell"
                    aria-current={today ? "date" : undefined}
                    aria-label={inTerm && pos ? `${formatDate(iso, locale, { day: "numeric", month: "long" })}, ${t("calendar.heat.cell", { w: pos.week, date: "", p: Math.round((v?.occupancy ?? 0) * 100), occ: (v?.occupied ?? 0) + (v?.blocked ?? 0), cap: v?.capacity ?? 0, c: v?.conflicts ?? 0 })}` : `${formatDate(iso, locale, { day: "numeric", month: "long" })}, ${t("calendar.heat.outOfTerm")}`}
                    disabled={!inTerm}
                    className={cn("cal-heat relative flex flex-col items-start justify-between rounded-[8px] p-2 text-left", outMonth && "opacity-60")}
                    data-step={s}
                    data-out={!inTerm ? "true" : undefined}
                    data-holiday={kind === "holiday" ? "true" : undefined}
                    onClick={() => pos && p.onPick(pos.week, pos.day)}
                  >
                    <span className={cn("flex size-6 items-center justify-center rounded-full text-[12px] font-semibold tabular-nums", today && "bg-tint text-tint-foreground")}>{Number(iso.slice(8))}</span>
                    {inTerm ? (
                      <span className="flex w-full flex-col gap-0.5">
                        {kind === "final" ? <span className="text-[11px]">{t("calendar.weekType.final")}</span> : null}
                        {kind === "holiday" ? <span className="text-[11px]">{t("calendar.weekType.holiday")}</span> : null}
                        {v?.conflicts ? <span className="text-[11px]">▲ {t("calendar.heat.conflictCount", { n: v.conflicts })}</span> : null}
                        <span className="text-[20px] leading-6 font-semibold tabular-nums">{cellText(p.metric, raw, t)}</span>
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
      <HeatLegend metric={p.metric} max={max} />
    </div>
  );
}

export const TermHeat = memo(TermHeatImpl);
export const MonthHeat = memo(MonthHeatImpl);
