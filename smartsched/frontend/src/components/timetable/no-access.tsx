"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useI18n } from "@/lib/i18n/provider";

/**
 * /timetable for someone whose role lacks planning access (GET /runs or the run index answered 403).
 * Never the planner empty state ("no timetable yet" + Generate / Import): that told a Teacher the
 * timetable did not exist (persona test U-02).
 */
export function TimetableNoAccess() {
  const { t } = useI18n();
  return (
    <EmptyState
      data-testid="timetable-no-access"
      icon={<Lock aria-hidden />}
      title={t("calendar.empty.noAccessTitle")}
      description={t("calendar.empty.noAccessBody")}
      actions={
        <Link href="/bookings" className={buttonVariants({ variant: "default" })}>
          {t("calendar.empty.toBookings")}
        </Link>
      }
    />
  );
}
