/**
 * Recurring booking preview (CRBS `SingleAgent::preview_single_recurring`): every date of the series with
 * the action the user picked (book / do not book / replace), holidays shown as skipped rows, and the
 * `recur_max_instances` limit applied the way the backend applies it (the first N booked instances in date
 * order are created, the rest are skipped with `recur_max_instances`).
 */
import type { InstanceAction, RecurInstance, RecurPlan } from "@/lib/api/crbs";

export interface HolidayDay {
  date: string;
  name: string;
}

export interface PreviewState {
  plan: RecurPlan | null;
  choices: Record<string, InstanceAction>;
  holidays: HolidayDay[];
  /** dates whose availability changed on the last re-check, so the user's choice fell back to the default (T-R2-09) */
  reset: string[];
}

export type PreviewAction =
  | { type: "load"; plan: RecurPlan; holidays?: HolidayDay[] }
  | { type: "set"; date: string; action: InstanceAction }
  | { type: "setAll"; action: "book" | "do_not_book" }
  | { type: "reset" };

export const initialPreview: PreviewState = { plan: null, choices: {}, holidays: [], reset: [] };

/** The backend default: book what is free, leave the rest. */
export function defaultAction(inst: RecurInstance): InstanceAction {
  return inst.status === "free" && inst.actions.includes("book") ? "book" : "do_not_book";
}

export function previewReducer(state: PreviewState, action: PreviewAction): PreviewState {
  switch (action.type) {
    case "load": {
      // A re-check ("Yeniden denetle") keeps the user's book / skip / replace choice for every date still in the
      // plan; only a date whose availability changed (the kept action is no longer offered) falls back to the
      // default and is listed in `reset` so the table can say so. R2-M-01: the old load rebuilt every choice from
      // the defaults and the submit body silently carried them.
      const choices: Record<string, InstanceAction> = {};
      const reset: string[] = [];
      for (const inst of action.plan.instances) {
        const kept = state.plan ? state.choices[inst.date] : undefined;
        if (kept && inst.actions.includes(kept)) {
          choices[inst.date] = kept;
          continue;
        }
        choices[inst.date] = defaultAction(inst);
        if (kept && kept !== choices[inst.date]) reset.push(inst.date);
      }
      return { plan: action.plan, choices, holidays: action.holidays ?? [], reset };
    }
    case "set": {
      const inst = state.plan?.instances.find((i) => i.date === action.date);
      if (!inst || !inst.actions.includes(action.action)) return state;
      return { ...state, choices: { ...state.choices, [action.date]: action.action } };
    }
    case "setAll": {
      if (!state.plan) return state;
      const choices = { ...state.choices };
      for (const inst of state.plan.instances) {
        // "book all" only touches free dates; taken dates keep their explicit choice (replace is deliberate)
        if (action.action === "book" && inst.actions.includes("book")) choices[inst.date] = "book";
        if (action.action === "do_not_book") choices[inst.date] = "do_not_book";
      }
      return { ...state, choices };
    }
    case "reset":
      return initialPreview;
  }
}

export type RowKind = "instance" | "holiday";

export interface PreviewRow {
  kind: RowKind;
  date: string;
  termWeek: number | null;
  /** free | booked | timetable | block | holiday */
  status: string;
  action: InstanceAction | null;
  actions: InstanceAction[];
  /** label of what holds the slot (course code, holiday name, the other booking's user) */
  heldLabel: string | null;
  /** chosen to book/replace but beyond `recur_max_instances`: the backend will skip it */
  cut: boolean;
  /** the last re-check found this date changed and dropped the user's choice (T-R2-09) */
  reset: boolean;
  instance: RecurInstance | null;
}

export interface PreviewSummary {
  rows: PreviewRow[];
  book: number;
  replace: number;
  skip: number;
  holidays: number;
  /** instances that will actually be created */
  willCreate: number;
  /** chosen but cut by the limit */
  cut: number;
  maxInstances: number | null;
}

export function summarise(state: PreviewState): PreviewSummary {
  const plan = state.plan;
  const max = plan?.max_instances ?? null;
  const rows: PreviewRow[] = [];
  const resetDates = new Set(state.reset);
  let taken = 0;
  for (const inst of plan?.instances ?? []) {
    const action = state.choices[inst.date] ?? defaultAction(inst);
    const wants = action === "book" || action === "replace";
    const cut = wants && max !== null && taken >= max;
    if (wants && !cut) taken++;
    rows.push({
      kind: "instance",
      date: inst.date,
      termWeek: inst.term_week ?? null,
      status: inst.status,
      action,
      actions: inst.actions,
      heldLabel: inst.held?.label ?? inst.booking?.user_name ?? null,
      cut,
      reset: resetDates.has(inst.date),
      instance: inst,
    });
  }
  const instanceDates = new Set(rows.map((r) => r.date));
  for (const h of state.holidays) {
    if (instanceDates.has(h.date)) continue;
    rows.push({ kind: "holiday", date: h.date, termWeek: null, status: "holiday", action: null, actions: [], heldLabel: h.name, cut: false, reset: false, instance: null });
  }
  rows.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const inst = rows.filter((r) => r.kind === "instance");
  const book = inst.filter((r) => r.action === "book").length;
  const replace = inst.filter((r) => r.action === "replace").length;
  const cut = inst.filter((r) => r.cut).length;
  return {
    rows,
    book,
    replace,
    skip: inst.filter((r) => r.action === "do_not_book").length,
    holidays: rows.length - inst.length,
    willCreate: book + replace - cut,
    cut,
    maxInstances: max,
  };
}

/** Body for `POST /bookings/recurring`: every instance with its explicit action. */
export function instancesPayload(state: PreviewState): { date: string; action: InstanceAction }[] {
  return (state.plan?.instances ?? []).map((i) => ({ date: i.date, action: state.choices[i.date] ?? defaultAction(i) }));
}

/**
 * Holiday dates that a weekly series on `weekday` would have hit between `from` and `to` (from the
 * `/bookings/dates` picker data), so the preview can show them as skipped instead of silently missing.
 */
export function holidaysOnWeekday(
  dates: readonly { date: string; weekday: number; holiday?: string | null }[],
  weekday: number,
  from: string,
  to: string,
): HolidayDay[] {
  return dates.filter((d) => d.weekday === weekday && d.holiday && d.date >= from && d.date <= to).map((d) => ({ date: d.date, name: d.holiday as string }));
}
