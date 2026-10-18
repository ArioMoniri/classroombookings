"use client";
/**
 * E2EB-F03 (fix-j-2026-10-18): on an empty install there is no term to book in. Find-room and Hızlı rezervasyon say
 * so and name the one next step instead of showing a form whose "Ara" / "Rezerve et" can never work: people who can
 * set up the data get "Dosyalardan kur" (/onboarding), everyone else is told who can.
 */
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";

export function NoBookingTerm({ testId = "no-booking-term" }: { testId?: string }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  const canSetUp = can("planning.edit");
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl bg-fill-3 px-4 py-5" data-testid={testId}>
      <h2 className="type-headline text-label-1">{t("quickReserve.noTermCard.title")}</h2>
      <p className="type-callout text-label-2">{canSetUp ? t("quickReserve.noTermCard.setup") : t("quickReserve.noTermCard.ask")}</p>
      {canSetUp ? (
        <Button nativeButton={false} render={<Link href="/onboarding" />} className="pointer-coarse:min-h-11" data-testid={`${testId}-setup`}>
          {t("quickReserve.noTermCard.action")} <ArrowRight aria-hidden />
        </Button>
      ) : null}
    </div>
  );
}
