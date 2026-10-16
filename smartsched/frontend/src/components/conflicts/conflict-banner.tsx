"use client";
/**
 * "Yayınlanan programla çakışan 12 rezervasyon (2 seri) · Çöz" — shown to planners (`planning.edit`) on the bookings
 * grid and the timetable while a published run has open conflicts (`GET /bookings/conflicts/summary`). Nothing for
 * anyone else: the summary is never fetched without the permission.
 */
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { useConflictSummary } from "@/lib/api/booking-conflicts";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

/** The backend's banner sentence without its trailing "· Çöz" (the button says it). */
export function bannerText(message: string): string {
  return message.replace(/\s*·\s*(Çöz|Resolve)\s*$/u, "");
}

export function ConflictBanner({ className }: { className?: string }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const hydrated = useHydrated();
  const planner = hydrated && can("planning.edit");
  const q = useConflictSummary(planner);
  const runs = (q.data?.runs ?? []).filter((r) => r.open > 0);
  if (!planner || !runs.length) return null;
  return (
    <div className={cn("flex flex-col gap-2 print:hidden", className)} data-testid="conflict-banner">
      {runs.map((r) => (
        <Alert
          key={r.run_id}
          tone="warning"
          action={
            <Button size="sm" variant="outline" render={<Link href={`/bookings/conflicts/${r.run_id}`} />} nativeButton={false} data-testid={`conflict-banner-open-${r.run_id}`}>
              {t("resolver.resolve")}
            </Button>
          }
        >
          {bannerText(locale === "tr" ? r.message_tr : r.message_en) || t("resolver.bannerFallback", { n: r.open })}
          {r.label ? <span className="block type-footnote opacity-80">{r.label}</span> : null}
        </Alert>
      ))}
    </div>
  );
}
