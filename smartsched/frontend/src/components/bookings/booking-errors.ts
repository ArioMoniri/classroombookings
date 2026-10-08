/**
 * Booking refusals in the user's language. The backend answers with a stable `code` (and, for conflicts,
 * the holder of the slot: `conflict.kind` = timetable | block | booking + `label`), so the message is built
 * here from the code instead of showing the English `message`.
 */
import type { CrbsError } from "@/lib/api/crbs";
import type { MessageKey, Vars } from "@/lib/i18n";

type T = (key: MessageKey, vars?: Vars) => string;

const CODE_KEYS: Record<string, MessageKey> = {
  room_not_found: "crbs.errors.room_not_found",
  room_not_bookable: "crbs.errors.room_not_bookable",
  "book_single.create": "crbs.errors.no_single",
  "book_recur.create": "crbs.errors.no_recur",
  set_user: "crbs.errors.set_user",
  set_department: "crbs.errors.set_department",
  holiday: "crbs.errors.holiday",
  no_week: "crbs.errors.no_week",
  date_range: "crbs.errors.date_range",
  calendar: "crbs.errors.calendar",
  range_min: "crbs.errors.range_min",
  range_max: "crbs.errors.range_max",
  max_active_bookings: "crbs.errors.max_active_bookings",
  must_select_fewer: "crbs.errors.must_select_fewer",
  already_cancelled: "crbs.errors.already_cancelled",
  not_cancelable: "crbs.errors.not_cancelable",
  not_editable: "crbs.errors.not_editable",
  cancelled: "crbs.errors.cancelled",
  scope: "crbs.errors.scope",
  none_created: "crbs.errors.none_created",
  no_recurring_dates: "crbs.errors.no_recurring_dates",
  recurring_dates: "crbs.errors.recurring_dates",
  slots_unavailable: "crbs.errors.slots_unavailable",
  none_selected: "crbs.errors.none_selected",
  user: "crbs.errors.user",
  department: "crbs.errors.department",
  not_found: "crbs.errors.not_found",
  maintenance: "crbs.errors.maintenance",
  validation: "crbs.errors.validation",
};

export interface ErrorContext {
  /** room id → display name ("A 101") */
  roomName?: (id: number) => string | undefined;
  /** "2026-02-16" → "16.02.2026" */
  formatDate?: (day: string) => string;
}

function periods(start: number, end: number): string {
  return start === end ? `P${start}` : `P${start}–P${end}`;
}

export function bookingErrorMessage(err: CrbsError, t: T, ctx: ErrorContext = {}): string {
  const date = (d: unknown) => (typeof d === "string" ? (ctx.formatDate ? ctx.formatDate(d) : d) : "");
  if (err.code === "conflict" && err.conflict) {
    const c = err.conflict;
    const vars = {
      room: ctx.roomName?.(c.room_id) ?? "",
      date: date(c.date),
      periods: periods(c.start_period, c.end_period),
      label: c.label ?? "",
    };
    if (c.kind === "timetable") return t("crbs.errors.conflict_timetable", vars);
    if (c.kind === "block") return t("crbs.errors.conflict_block", vars);
    return t("crbs.errors.conflict_booking", vars);
  }
  if (err.code === "conflict") return t("crbs.errors.conflict_race");
  if (err.code && err.code.startsWith("edit_")) return t("crbs.errors.edit_field");
  if (err.status === 503) return t("crbs.errors.maintenance_with", { message: err.message });
  const key = err.code ? CODE_KEYS[err.code] : undefined;
  if (key) {
    return t(key, {
      limit: String(err.data.limit ?? ""),
      remaining: String(err.data.remaining ?? ""),
      min: date(err.data.min_date),
      max: date(err.data.max_date),
      message: err.message,
    });
  }
  if (err.status === 0) return t("crbs.errors.offline");
  if (err.status === 403) return t("crbs.errors.forbidden");
  if (err.status === 404) return t("crbs.errors.not_found");
  return t("crbs.errors.generic", { message: err.message });
}
