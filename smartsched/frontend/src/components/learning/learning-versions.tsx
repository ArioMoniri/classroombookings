"use client";
/**
 * AS-17 / RF-07 in the learning memory: "Öğrenmeyi yenile" (a new learning version from the term's current
 * evidence), the nightly switch, "Sürümler" with what each version added, dropped or changed and "Bu sürüme dön"
 * (the term then stays on it until the next manual refresh), and the calibration drafts ("Ayar önerileri") behind
 * "Gelişmiş". Nothing here applies a suggestion; a version only changes what is suggested.
 */
import { useRef, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/admin/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useCalibration, useLearningSettings, useLearningVersionActions, useLearningVersions, type LearningVersion } from "@/lib/api/learning-versions";
import { apiText } from "@/lib/api/seasons";
import { useI18n } from "@/lib/i18n/provider";
import { attributeLabel } from "./learning-habits";

export function LearningVersions({ termId }: { termId: number | null }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const q = useLearningVersions(termId);
  const settings = useLearningSettings();
  const act = useLearningVersionActions();
  const [revert, setRevert] = useState<LearningVersion | null>(null);
  const refreshRef = useRef<HTMLButtonElement>(null);
  const versions = q.data?.versions ?? [];
  const latest = versions[0]?.id;
  const pinned = q.data?.pinned_version_id ?? null;
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Istanbul" }) : "");

  const refresh = () => {
    if (termId === null) return;
    act.refresh.mutate(termId, {
      onSuccess: (out) => toast.success(out.version ? t("adaptive.learning.refreshed", { n: out.version.number }) : t("adaptive.learning.refreshedPlain")),
      onError: (e) => toast.error(apiText(e, locale)),
    });
  };
  const doRevert = () => {
    if (!revert) return;
    act.revert.mutate(revert.id, {
      onSuccess: (out) => {
        toast.success(out.identical ? t("adaptive.learning.revertedSame", { n: revert.number }) : t("adaptive.learning.reverted", { n: revert.number }));
        setRevert(null);
        refreshRef.current?.focus();
      },
      onError: (e) => toast.error(apiText(e, locale)),
    });
  };

  return (
    <section aria-labelledby="mem-versions" className="flex flex-col gap-3" data-testid="learning-versions">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="mem-versions" className="type-headline">{t("adaptive.learning.title")}</h3>
        <Button ref={refreshRef} onClick={refresh} disabled={termId === null || act.refresh.isPending} data-testid="learning-refresh">
          <BusyLabel busy={act.refresh.isPending} label={t("busy.working")}>{t("adaptive.learning.refresh")}</BusyLabel>
        </Button>
      </div>
      <p className="type-footnote text-label-2">{t("adaptive.learning.hint")}</p>
      {settings.data ? (
        <label className="flex min-h-11 items-center justify-between gap-4 type-callout">
          <span>
            {t("adaptive.learning.nightly")}
            <span className="block type-footnote text-label-2">{t("adaptive.learning.nightlyHint")}</span>
          </span>
          <Switch checked={settings.data.nightly_refresh} onCheckedChange={(v) => act.nightly.mutate(Boolean(v), { onError: (e) => toast.error(apiText(e, locale)) })} data-testid="learning-nightly" />
        </label>
      ) : null}
      {q.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : q.isError ? (
        <p role="alert" className="type-footnote text-label-2">{t("learning.list.error")}</p>
      ) : versions.length === 0 ? (
        <p className="type-footnote text-label-2" data-testid="versions-empty">{q.data?.needs?.[lang] || t("adaptive.learning.none")}</p>
      ) : (
        <ol className="flex flex-col" data-testid="versions-list">
          {versions.slice(0, 10).map((v) => {
            const c = v.diff?.counts ?? { new: 0, dropped: 0, changed: 0 };
            const current = pinned !== null ? v.id === pinned : v.id === latest;
            return (
              <li key={v.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-2 type-footnote" data-testid="version-row">
                <span className="font-semibold text-label-1">{t("adaptive.learning.version", { n: v.number })}</span>
                <span className="text-label-2">{v.trigger_label?.[lang] ?? v.trigger}</span>
                <span className="tabular-nums text-label-2">{when(v.created_at)}</span>
                <span className="text-label-2">{t("adaptive.learning.counts", { obs: n(v.observations), sugg: n(v.suggestible), new: n(c.new), dropped: n(c.dropped), changed: n(c.changed) })}</span>
                {current ? <Badge tone={pinned !== null ? "warning" : "feasible"}>{pinned !== null ? t("adaptive.learning.pinned") : t("adaptive.learning.current")}</Badge> : null}
                {!current ? (
                  <Button size="xs" variant="outline" className="ml-auto" onClick={() => setRevert(v)} data-testid="version-revert">
                    {t("adaptive.learning.revert")}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
      <CalibrationDrafts />
      <ConfirmDialog
        open={!!revert}
        onOpenChange={(o) => !o && setRevert(null)}
        title={t("adaptive.learning.revertTitle", { n: revert?.number ?? 0 })}
        description={t("adaptive.learning.revertBody")}
        confirmLabel={t("adaptive.learning.revert")}
        busy={act.revert.isPending}
        onConfirm={doRevert}
      />
    </section>
  );
}

function CalibrationDrafts() {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const q = useCalibration();
  const act = useLearningVersionActions();
  const proposals = q.data?.proposals ?? [];
  const applied = Object.entries(q.data?.applied ?? {});
  if (!q.data || (proposals.length === 0 && applied.length === 0)) return null;
  return (
    <details className="rounded-lg bg-fill-3 px-3 py-1" data-testid="calibration">
      <summary className="flex min-h-11 cursor-pointer items-center type-callout font-medium text-label-1">{t("adaptive.learning.calibration", { n: proposals.length })}</summary>
      <ul className="flex flex-col gap-2 pb-3">
        {proposals.map((p) => (
          <li key={`${p.attribute}-${p.band}`} className="flex flex-wrap items-center gap-2 type-footnote">
            <span className="min-w-0 flex-1 text-label-1">{p.explanation[lang]}</span>
            <Button size="xs" onClick={() => act.apply.mutate({ attribute: p.attribute, min: p.min_confidence }, { onSuccess: () => toast.success(t("adaptive.learning.applied")), onError: (e) => toast.error(apiText(e, locale)) })} data-testid="calibration-apply">
              {t("adaptive.learning.apply")}
            </Button>
          </li>
        ))}
        {applied.map(([attr, v]) => (
          <li key={attr} className="flex flex-wrap items-center gap-2 type-footnote text-label-2">
            <span className="min-w-0 flex-1">{t("adaptive.learning.appliedRow", { attr: attributeLabel(t, attr), v: n(v) })}</span>
            <Button size="xs" variant="ghost" onClick={() => act.apply.mutate({ attribute: attr, min: null }, { onSuccess: () => toast.success(t("adaptive.learning.cleared")), onError: (e) => toast.error(apiText(e, locale)) })}>
              {t("adaptive.learning.clear")}
            </Button>
          </li>
        ))}
      </ul>
    </details>
  );
}
