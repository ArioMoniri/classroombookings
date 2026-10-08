"use client";
/**
 * Recurring preview (CRBS `preview_single_recurring`): one row per date with its state and the actions the
 * backend allows (book / do not book / replace). Holidays are listed as skipped so nobody wonders where
 * 23 Nisan went. Rows beyond `recur_max_instances` are marked "over the limit".
 */
import { CalendarOff, Check, GraduationCap, Repeat, User } from "lucide-react";
import type { Dispatch } from "react";
import type { InstanceAction } from "@/lib/api/crbs";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { Alert } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import type { PreviewAction, PreviewSummary } from "./recurring-preview";
import type { DateFormatter } from "./date-format";

const ACTION_KEYS: Record<InstanceAction, MessageKey> = {
  book: "crbs.recur.action.book",
  do_not_book: "crbs.recur.action.skip",
  replace: "crbs.recur.action.replace",
};

const STATUS: Record<string, { key: MessageKey; icon: typeof Check }> = {
  free: { key: "crbs.recur.status.free", icon: Check },
  booked: { key: "crbs.recur.status.booked", icon: User },
  timetable: { key: "crbs.recur.status.timetable", icon: GraduationCap },
  block: { key: "crbs.recur.status.block", icon: GraduationCap },
  holiday: { key: "crbs.recur.status.holiday", icon: CalendarOff },
};

export function RecurringPreviewTable({ summary, dispatch, fmt }: { summary: PreviewSummary; dispatch: Dispatch<PreviewAction>; fmt: DateFormatter }) {
  const t = useT();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="type-callout text-label-1" aria-live="polite" data-testid="recur-summary">
          {t("crbs.recur.summary", { create: summary.willCreate, skip: summary.skip + summary.cut, holidays: summary.holidays })}
        </p>
        <div className="flex gap-1">
          <Button variant="ghost" size="xs" onClick={() => dispatch({ type: "setAll", action: "book" })}>
            {t("crbs.recur.bookAll")}
          </Button>
          <Button variant="ghost" size="xs" onClick={() => dispatch({ type: "setAll", action: "do_not_book" })}>
            {t("crbs.recur.skipAll")}
          </Button>
        </div>
      </div>
      {summary.maxInstances !== null ? (
        <Alert tone={summary.cut ? "warning" : "info"}>{summary.cut ? t("crbs.recur.overLimit", { max: summary.maxInstances, cut: summary.cut }) : t("crbs.recur.limit", { max: summary.maxInstances })}</Alert>
      ) : null}
      <ol className="flex max-h-[42vh] flex-col overflow-auto rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)] scrollbar-thin" data-testid="recur-preview">
        {summary.rows.map((row) => {
          const st = STATUS[row.status] ?? STATUS.booked!;
          const Icon = row.kind === "instance" && row.status === "booked" && row.instance?.held?.series_id ? Repeat : st.icon;
          return (
            <li key={row.date} data-date={row.date} data-kind={row.kind} className={cn("flex items-center gap-3 px-3 py-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none", row.kind === "holiday" && "hatch-preoccupied")}>
              <div className="min-w-0 flex-1">
                <p className={cn("type-callout font-medium text-label-1", (row.action === "do_not_book" || row.kind === "holiday" || row.cut) && "text-label-2")}>
                  {fmt.weekday(row.date)}
                  {row.termWeek ? <span className="ml-2 type-footnote font-normal text-label-3">{t("crbs.recur.termWeek", { n: row.termWeek })}</span> : null}
                </p>
                <p className="flex items-center gap-1 type-footnote text-label-2">
                  <Icon className="size-3 shrink-0" aria-hidden />
                  <span>{t(st.key)}</span>
                  {row.heldLabel ? <span className="truncate">· {row.heldLabel}</span> : null}
                  {row.cut ? <span className="font-medium text-status-warning-fg">· {t("crbs.recur.cut")}</span> : null}
                </p>
              </div>
              {row.kind === "instance" && row.actions.length > 1 ? (
                <div role="radiogroup" aria-label={t("crbs.recur.actionFor", { date: fmt.short(row.date) })} className="flex shrink-0 gap-0.5 rounded-full bg-fill-2 p-[3px]">
                  {row.actions.map((a) => (
                    <button
                      key={a}
                      type="button"
                      role="radio"
                      aria-checked={row.action === a}
                      onClick={() => dispatch({ type: "set", date: row.date, action: a })}
                      className={cn(
                        "h-6 rounded-full px-2.5 type-caption text-label-2 outline-none focus-visible:outline-2 focus-visible:outline-(--focus)",
                        row.action === a && "bg-(--mat-thick-solid) text-label-1 shadow-[0_0_0_1px_var(--hairline),0_1px_2px_rgba(0,0,0,0.08)]",
                      )}
                    >
                      {t(ACTION_KEYS[a])}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="shrink-0 type-footnote text-label-3">{row.kind === "holiday" ? t("crbs.recur.skippedHoliday") : t("crbs.recur.action.skip")}</span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
