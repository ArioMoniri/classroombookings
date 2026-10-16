"use client";
/**
 * /bookings/conflicts — the published runs with open conflicts (planning.edit). One run opens its resolver directly.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { CheckCircle2 } from "lucide-react";
import { Alert, Loading, NoAccess, PageTitle } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useConflictSummary } from "@/lib/api/booking-conflicts";
import { usePermissions } from "@/lib/api/shell-extra";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { bannerText } from "./conflict-banner";

export function ConflictsIndex() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { can, me } = usePermissions();
  const planner = can("planning.edit");
  const q = useConflictSummary(planner);
  const runs = (q.data?.runs ?? []).filter((r) => r.open > 0);
  const only = runs.length === 1 ? runs[0]!.run_id : null;
  useEffect(() => {
    if (only) router.replace(`/bookings/conflicts/${only}`);
  }, [only, router]);
  if (!me) return <Loading />;
  if (!planner) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("resolver.noAccess")} />;
  return (
    <div className="flex max-w-3xl flex-col gap-4" data-testid="conflicts-index">
      <PageTitle title={t("resolver.title")} subtitle={t("resolver.indexLead")} />
      {q.isLoading || only ? <Loading /> : null}
      {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
      {q.isSuccess && !runs.length ? (
        <Card className="items-start gap-2 px-4 py-6">
          <p className="flex items-center gap-2 type-headline text-label-1">
            <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden />
            {t("resolver.emptyTitle")}
          </p>
          <p className="type-callout text-label-2">{t("resolver.indexEmpty")}</p>
        </Card>
      ) : null}
      {runs.length > 1 ? (
        <ul className="flex flex-col gap-2">
          {runs.map((r) => (
            <li key={r.run_id}>
              <Card className="flex-row flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="type-headline text-label-1">{r.label || `#${r.run_id}`}</p>
                  <p className="type-callout text-label-2">{bannerText(locale === "tr" ? r.message_tr : r.message_en)}</p>
                </div>
                <Button size="sm" render={<Link href={`/bookings/conflicts/${r.run_id}`} />} nativeButton={false}>
                  {t("resolver.resolve")}
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
