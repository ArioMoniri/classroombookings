/**
 * W3-SLOT quick reserve (docs/design/v3/quick-reserve.md): pure, unit-tested pieces behind /reserve.
 * Step 1 "Ne zaman?" = a day chip + a slot in the administrator's unit (periods, or 15/30/60-minute blocks mapped onto
 * the periods) + a length; step 2 "Nerede?" = POST /rooms/find for exactly that span, ranked; step 3 books it.
 */
import type { DateInfo, Grid, GridPeriod } from "@/lib/api/crbs";
import type { FindQuery, FindRow } from "@/lib/api/wave1";
import { isSelectable } from "@/components/bookings/grid-model";
import { blockStarts, coverPeriods, lengthOptions, minutes, periodVisible, type SlotDisplay } from "@/components/bookings/slot-display";

export interface DayChip {
  date: string;
  kind: "today" | "tomorrow" | "day";
  closed: boolean;
  holiday: string | null;
  reason: string | null;
}

/** ISO weekdays (1 = Monday) the schedule has periods on, from the periods' `days`; null when unknown. */
export function schoolWeekdays(periods: readonly Pick<GridPeriod, "days">[]): ReadonlySet<number> | null {
  const days = new Set(periods.flatMap((p) => p.days ?? []));
  return days.size ? days : null;
}

/** Today, tomorrow and the next school days from `today` (`count` chips). A closed weekday stays, disabled with its
 *  reason (it explains the week); a closed weekend day, and any day the schedule has no periods on, is left out. */
export function dayChips(dates: readonly DateInfo[], today: string, count = 7, school: ReadonlySet<number> | null = null): DayChip[] {
  const out: DayChip[] = [];
  const tomorrow = addDay(today, 1);
  for (const d of [...dates].filter((x) => x.date >= today).sort((a, b) => a.date.localeCompare(b.date))) {
    const weekend = d.weekday === 6 || d.weekday === 7;
    if (!d.open && weekend && !d.holiday) continue;
    if (school && !school.has(d.weekday)) continue;
    out.push({ date: d.date, kind: d.date === today ? "today" : d.date === tomorrow ? "tomorrow" : "day", closed: !d.open || !!d.holiday, holiday: d.holiday ?? null, reason: d.reason ?? null });
    if (out.length >= count) break;
  }
  return out;
}

export function addDay(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export interface SlotOption {
  /** stable key: p<period id> or b<HH:MM> */
  key: string;
  /** the period the slot starts in */
  periodId: number;
  /** HH:MM the slot starts */
  time: string;
  /** no room in the grid is free then (only claimed when the grid holds every room) */
  full: boolean;
}

export interface Now {
  date: string;
  time: string;
}

/**
 * The day's slot choices in the administrator's unit: visible periods (or block starts inside them) that have not
 * started yet. `allRooms`: the grid lists every room the user may book, so "no free room" can be said ("Dolu").
 */
export function slotOptions(grid: Grid, sd: SlotDisplay, now: Now | undefined, allRooms: boolean): SlotOption[] {
  const weekday = grid.dates.find((d) => d.date === grid.date)?.weekday;
  const visible = grid.periods.filter((p) => periodVisible(p, sd) && (!weekday || !p.days?.length || p.days.includes(weekday)));
  const isToday = !!now && now.date === grid.date;
  const pastOk = (periodId: number) => grid.slots.some((s) => s.period_id === periodId && s.date === grid.date && s.past && isSelectable(s));
  const freeIn = (periodId: number) => grid.slots.some((s) => s.period_id === periodId && s.date === grid.date && isSelectable(s));
  const started = (time: string, periodId: number) => isToday && minutes(time) < minutes(now!.time) && !pastOk(periodId);
  const raw = sd.unit === "blocks" ? blockStarts(visible, sd).map((b) => ({ key: `b${b.time}`, periodId: b.periodId, time: b.time })) : [...visible].sort((a, b) => minutes(a.time_start) - minutes(b.time_start)).map((p) => ({ key: `p${p.id}`, periodId: p.id, time: p.time_start.slice(0, 5) }));
  return raw.filter((o) => !started(o.time, o.periodId)).map((o) => ({ ...o, full: allRooms && !freeIn(o.periodId) }));
}

export function defaultSlot(options: readonly SlotOption[]): SlotOption | null {
  return options.find((o) => !o.full) ?? null;
}

function consecutive(periods: readonly GridPeriod[], startId: number): GridPeriod[] {
  const sorted = [...periods].sort((a, b) => minutes(a.time_start) - minutes(b.time_start));
  const i = sorted.findIndex((p) => p.id === startId);
  if (i < 0) return [];
  const out = [sorted[i]!];
  for (let k = i + 1; k < sorted.length; k++) {
    if (minutes(sorted[k]!.time_start) - minutes(out[out.length - 1]!.time_end) > 20) break;
    out.push(sorted[k]!);
  }
  return out;
}

/** The whole periods a choice of `length` units covers (bookings stay per period), or null when it does not fit. */
export function spanFor(visible: readonly GridPeriod[], slot: SlotOption, length: number, sd: SlotDisplay): GridPeriod[] | null {
  if (sd.unit === "blocks") return coverPeriods(visible, slot.time, length * sd.block_minutes);
  const run = consecutive(visible, slot.periodId);
  return run.length >= length ? run.slice(0, length) : null;
}

/** Lengths (in the unit) offered for a start: the administrator's range, cut to what still fits that day. */
export function lengthChoices(visible: readonly GridPeriod[], slot: SlotOption, sd: SlotDisplay): number[] {
  return lengthOptions(sd, 64).filter((n) => spanFor(visible, slot, n, sd) !== null);
}

/** POST /rooms/find for one date and exactly the span (grid period numbers), bookable rooms only, no alternatives. */
export function findQuery(q: { date: string; termId?: number; span: readonly GridPeriod[]; headcount: number; features: readonly number[] }): FindQuery {
  const first = q.span[0]!;
  const last = q.span[q.span.length - 1]!;
  return {
    term_id: q.termId,
    date: q.date,
    start: first.start_period,
    duration_periods: last.end_period - first.start_period + 1,
    headcount: q.headcount,
    features: q.features.map((field) => ({ field })),
    include_busy: false,
    include_requestable: true,
    flex: { periods: 0 },
    limit: 60,
  };
}

export type RoomAction = "book" | "request" | "mine";

export function roomAction(r: FindRow): RoomAction {
  if (r.status === "mine_pending") return "mine";
  return r.action === "request" ? "request" : "book";
}

const ACTION_RANK: Record<RoomAction, number> = { book: 0, request: 1, mine: 2 };

/**
 * The short ranked list (quick-reserve.md §4.3): rows one can book or request (and the caller's own waiting request,
 * marked), server fit score first, then rooms used in the last 60 days, direct before "Talep", smaller room, code.
 */
export function rankRooms(rows: readonly FindRow[], recent: ReadonlySet<number>): FindRow[] {
  return rows
    .filter((r) => r.status === "mine_pending" || r.action === "book" || r.action === "request")
    .map((r, i) => ({ r, i }))
    .sort((a, b) => {
      const s = (b.r.fit?.score ?? 0) - (a.r.fit?.score ?? 0);
      if (Math.abs(s) > 1e-9) return s;
      const rec = Number(recent.has(b.r.room_id)) - Number(recent.has(a.r.room_id));
      if (rec) return rec;
      const act = ACTION_RANK[roomAction(a.r)] - ACTION_RANK[roomAction(b.r)];
      if (act) return act;
      const cap = (a.r.capacity ?? 9999) - (b.r.capacity ?? 9999);
      if (cap) return cap;
      return a.r.code.localeCompare(b.r.code, "tr") || a.i - b.i;
    })
    .map((x) => x.r);
}

/** Monday–Friday on or after `iso` (a weekday's day grid lists the schedule's periods with their `days`). */
export function nextWeekday(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}
