"use client";
/** HX-02: the label of a shortcut row ("Salon ayır: A 204 · yarın · 10:00") and the rule for showing it at all. */
import { usePermissions } from "@/lib/api/shell-extra";
import { intlLocale, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { canOpenFeature, featureById, featureTitle } from "./feature-links";
import type { Intent } from "./intents";

const pad = (n: number) => String(n).padStart(2, "0");

export function dayLabel(date: string, locale: Locale, t: (k: "helper.shortcut.today" | "helper.shortcut.tomorrow") => string, now = new Date()): string {
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const tomorrow = `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
  if (date === today) return t("helper.shortcut.today");
  if (date === tomorrow) return t("helper.shortcut.tomorrow");
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "long", weekday: "long" }).format(new Date(y!, m! - 1, d!));
}

export function useShortcutLabel(intent: Intent | null): string | null {
  const { t, locale } = useI18n();
  if (!intent) return null;
  const a = intent.args;
  const day = typeof a.date === "string" && a.date ? dayLabel(a.date, locale, t) : null;
  const when = intent.hints?.time ?? (intent.hints?.period ? t("helper.shortcut.period", { n: intent.hints.period }) : null);
  const parts = (xs: (string | number | null | undefined)[]) => xs.filter((x) => x !== null && x !== undefined && x !== "").join(" · ");
  switch (intent.action) {
    case "create_booking":
      return t("helper.shortcut.book", { what: parts([a.room as string, day, when]) });
    case "find_free_rooms": {
      const range = a.start ? (a.end ? `${a.start}–${a.end}` : String(a.start)) : when;
      const what = parts([day, range, a.headcount ? t("glass.palette.seats", { n: Number(a.headcount) }) : null, a.text as string | undefined, a.building ? t("helper.shortcut.building", { b: String(a.building) }) : null]);
      return what ? t("helper.shortcut.find", { what }) : t("helper.shortcut.findPlain");
    }
    case "room_day_schedule":
      return t("helper.shortcut.roomDay", { what: parts([a.room as string, day]) });
    case "my_bookings":
      return a.days === 7 ? t("helper.shortcut.myBookingsWeek") : t("helper.shortcut.myBookings");
    case "cancel_my_booking":
      return t("helper.shortcut.cancel");
    case "my_requests_status":
      return t("helper.shortcut.myRequests");
    case "approvals_inbox":
      return t("helper.shortcut.approvals");
    case "my_ai_usage":
      return t("helper.shortcut.usage");
    case "undo_last_helper_action":
      return t("helper.shortcut.undo");
    case "open_feature":
      return featureTitle(String(a.feature_id), locale);
    default:
      return null;
  }
}

/** A shortcut shows only when the person may run its action (`GET /helper/actions`) and open its page. */
export function useIntentAllowed(): (intent: Intent | null, actions: ReadonlySet<string> | null) => boolean {
  const { can } = usePermissions();
  return (intent, actions) => {
    if (!intent) return false;
    if (intent.action === "open_feature") {
      const e = featureById(String(intent.args.feature_id));
      return !!e && canOpenFeature(e, can);
    }
    return !actions || actions.has(intent.action);
  };
}
