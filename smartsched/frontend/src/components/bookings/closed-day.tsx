"use client";
/**
 * HX12B-F01 / PER-F11: a day with no bookable periods (a weekend, a closed weekday) says so in one sentence and
 * offers the next open day, on every viewport — never a blank grid.
 */
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { useI18n } from "@/lib/i18n/provider";
import type { Grid } from "@/lib/api/crbs";

/** The grid shows one day that has no period at all. */
export function isClosedDay(g: Grid | undefined): boolean {
  return !!g && g.display === "day" && g.periods.length === 0;
}

export function ClosedDayNotice({ next, long, onGo }: { next: string | null; long: (day: string) => string; onGo: (day: string) => void }) {
  const { t } = useI18n();
  return (
    <Alert
      tone="neutral"
      data-testid="grid-closed-day"
      title={t("reserve.free.closedDay")}
      action={
        next ? (
          <Button size="sm" className="pointer-coarse:min-h-11" onClick={() => onGo(next)} data-testid="grid-closed-day-next">
            {t("reserve.free.goNext", { date: long(next) })}
          </Button>
        ) : null
      }
    />
  );
}
