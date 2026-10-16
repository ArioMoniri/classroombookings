"use client";
/**
 * "Tercihlerim" (P19-T2): the academician's own wishes with their status (Bekliyor / Kabul edildi / Kabul
 * edilmedi), the coordinator's reason on a rejection, and "Geri çek" while a wish is still pending (the whole
 * submission goes; `DELETE /moderation/me/preferences/{id}`, 409 once decided). One card per submission.
 */
import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { PrefStatus } from "@/lib/api/moderation";
import { useMyPreferences, useWithdrawWish, wishError } from "@/lib/api/teacher-preferences";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { pairText } from "./moderation-model";
import { ResponsiveDialog } from "./responsive-dialog";
import { groupWishes, isKnownError, isRejectCode, type WishGroup } from "./wish-model";

export function WishStatusBadge({ status }: { status: PrefStatus }) {
  const { t } = useI18n();
  const Icon = status === "accepted" ? CheckCircle2 : status === "rejected" ? XCircle : Clock;
  return (
    <Badge tone={status === "accepted" ? "feasible" : status === "rejected" ? "infeasible" : "warning"} data-testid="wish-status" data-status={status}>
      <Icon aria-hidden />
      {t(`moderation.wish.status.${status}`)}
    </Badge>
  );
}

export function useDateText() {
  const { locale } = useI18n();
  // timestamps ("2026-10-16T04:31:58+00:00"), shown in the browser's time zone: "16 Eki 07:31"
  return (iso: string | null | undefined) => {
    const d = iso ? new Date(iso) : null;
    return d && !Number.isNaN(d.getTime()) ? new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(d) : "";
  };
}

export function MyWishes({ termId }: { termId: number | null }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const q = useMyPreferences(termId);
  const withdraw = useWithdrawWish();
  const [asking, setAsking] = useState<WishGroup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const date = useDateText();
  const groups = groupWishes(q.data?.items ?? []);
  const counts = q.data?.counts ?? { pending: 0, accepted: 0, rejected: 0 };

  const confirm = async () => {
    if (!asking) return;
    setError(null);
    try {
      await withdraw.mutateAsync(asking.items[0]!.id);
      toast.success(t("moderation.wish.withdrawn"));
      setAsking(null);
    } catch (e) {
      const err = wishError(e);
      setError(err && isKnownError(err.code) ? t(`moderation.wish.err.${err.code}` as MessageKey) : (err?.message ?? t("moderation.wish.err.generic")));
      void q.refetch();
    }
  };

  return (
    <section className="flex flex-col gap-2" aria-labelledby="my-wishes-title" data-testid="my-wishes">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <h2 id="my-wishes-title" className="type-title-3">{t("moderation.wish.mine.title")}</h2>
        {q.data ? <span className="type-footnote text-label-2" data-testid="my-wishes-counts">{t("moderation.wish.mine.counts", { pending: n(counts.pending), accepted: n(counts.accepted), rejected: n(counts.rejected) })}</span> : null}
      </div>
      <p className="type-footnote text-label-2">{t("moderation.wish.mine.lead")}</p>
      {q.isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : q.isError ? (
        <Alert tone="error" action={<Button size="sm" variant="ghost" onClick={() => void q.refetch()}>{t("common.retry")}</Button>}>{t("moderation.wish.mine.loadError")}</Alert>
      ) : groups.length === 0 ? (
        <div className="rounded-xl bg-fill-3 px-3 py-3" data-testid="my-wishes-empty">
          <p className="type-callout">{t("moderation.wish.mine.empty")}</p>
          <p className="type-footnote text-label-2">{t("moderation.wish.mine.emptyHint")}</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {groups.map((g) => {
            const head = g.items[0]!;
            const label = g.labels.slice(0, 3).join(", ") + (g.labels.length > 3 ? " …" : "");
            const decided = g.items.find((i) => i.status !== "pending");
            return (
              <li key={g.key} className="flex flex-col gap-1 rounded-xl bg-card p-3 edge-hairline" data-testid="my-wish" data-status={g.status}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 flex-1 type-headline">{label || pairText(head.kind_label, lang)}</span>
                  <WishStatusBadge status={g.status} />
                </div>
                <span className="type-footnote text-label-2">{pairText(head.kind_label, lang)}</span>
                {g.items.map((it) => (
                  <p key={it.id} className="type-callout">{pairText(it.text, lang)}</p>
                ))}
                {head.note ? <p className="type-footnote text-label-2">{t("moderation.wish.yourNote")}: “{head.note}”</p> : null}
                {g.status === "rejected" && decided ? (
                  <p className="rounded-md bg-status-infeasible px-2 py-1 type-callout text-status-infeasible-fg" data-testid="my-wish-reason">
                    <span className="font-semibold">{t("moderation.wish.reason")}: </span>
                    {isRejectCode(decided.reason_code) ? `${t(`moderation.review.codes.${decided.reason_code}`)}: ` : ""}
                    {decided.reason}
                  </p>
                ) : null}
                {g.status === "accepted" ? <p className="type-footnote text-status-feasible-fg">{t("moderation.wish.acceptedNote")}</p> : null}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="min-w-0 flex-1 type-caption text-label-3">
                    {[g.submittedAt ? t("moderation.wish.submittedAt", { date: date(g.submittedAt) }) : null, decided?.decided_at ? t("moderation.wish.decidedAt", { date: date(decided.decided_at) }) : null].filter(Boolean).join(" · ")}
                  </span>
                  {g.status === "pending" ? (
                    <Button size="sm" variant="outline" className="max-md:h-11" aria-label={t("moderation.wish.withdrawLabel", { label })} onClick={() => (setError(null), setAsking(g))} data-testid="wish-withdraw">
                      {t("moderation.wish.withdraw")}
                    </Button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <ResponsiveDialog
        open={asking !== null}
        onOpenChange={(o) => !o && setAsking(null)}
        alert
        title={t("moderation.wish.withdrawTitle")}
        description={asking ? t("moderation.wish.withdrawBody", { label: asking.labels.slice(0, 3).join(", ") }) : undefined}
        testId="wish-withdraw-dialog"
        footer={
          <>
            <Button variant="ghost" className="max-md:h-11" onClick={() => setAsking(null)}>{t("common.cancel")}</Button>
            <Button variant="destructive" className="max-md:h-11" onClick={() => void confirm()} disabled={withdraw.isPending} aria-busy={withdraw.isPending || undefined} data-testid="wish-withdraw-confirm">
              {withdraw.isPending ? t("busy.working") : t("moderation.wish.withdraw")}
            </Button>
          </>
        }
      >
        {error ? <Alert tone="error">{error}</Alert> : null}
      </ResponsiveDialog>
    </section>
  );
}
