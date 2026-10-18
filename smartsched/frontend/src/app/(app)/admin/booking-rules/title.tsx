"use client";
import { PageTitle } from "@/components/admin/kit";
import { useI18n } from "@/lib/i18n/provider";

export function BookingRulesTitle() {
  const { t } = useI18n();
  return <PageTitle title={t("policies.title")} subtitle={t("policies.pageSubtitle")} />;
}
