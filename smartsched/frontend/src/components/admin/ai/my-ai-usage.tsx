"use client";
/**
 * Profil › Yapay zekâ kullanımım (`GET /ai/me/usage`): the user's own tokens today / this month against their limit,
 * the reset date, the split by feature; and {@link AiUsageBanner}, the near / at-limit banner for any AI surface
 * (chat panel, rules from text, upload): `role="status"` near the threshold, `role="alert"` at the limit. A user
 * without any AI use or limit sees nothing (the section stays hidden instead of a block of zeros).
 */
import { Alert } from "@/components/admin/kit";
import { Card } from "@/components/ui/card";
import { useMyAiUsage } from "@/lib/api/ai-admin";
import { useI18n } from "@/lib/i18n/provider";
import { AiNotice, Meter, Tokens, useAiLabels } from "./ai-kit";
import { compactTokens, meterState, pctText, resetDate } from "./ai-model";

export function MyAiUsage() {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const q = useMyAiUsage();
  const d = q.data;
  if (!d) return null;
  if (!d.month_tokens && !d.daily_limit && !d.monthly_limit) return null;
  return (
    <Card className="gap-3 px-4 py-4" data-testid="my-ai-usage">
      <h2 className="type-headline text-label-1">{t("aiAdmin.me.title")}</h2>
      <AiUsageBanner />
      <div className="grid gap-4 sm:grid-cols-2">
        <Meter
          testId="my-ai-day"
          pct={d.daily_pct}
          state={meterState(d.daily_pct, d.soft_pct)}
          label={
            <>
              {t("aiAdmin.me.today")}: <Tokens n={d.day_tokens} />
              {d.daily_limit ? ` / ${compactTokens(d.daily_limit, locale)}` : ""}
            </>
          }
        />
        <Meter
          testId="my-ai-month"
          pct={d.monthly_pct}
          state={meterState(d.monthly_pct, d.soft_pct)}
          label={
            <>
              {t("aiAdmin.me.month")}: <Tokens n={d.month_tokens} />
              {d.monthly_limit ? ` / ${compactTokens(d.monthly_limit, locale)}` : ""}
            </>
          }
        />
      </div>
      <p className="type-footnote text-label-2">{d.daily_limit || d.monthly_limit ? t("aiAdmin.me.resets", { day: resetDate("day", locale), month: resetDate("month", locale) }) : t("aiAdmin.me.none")}</p>
      {d.month_audio_s ? (
        <p className="type-footnote text-label-2" data-testid="my-ai-audio">
          {t("voice.admin.me.line", {
            day: Math.round((d.day_audio_s ?? 0) / 60),
            dayLimit: d.audio_daily_limit_s ? t("voice.admin.me.of", { n: Math.round(d.audio_daily_limit_s / 60) }) : "",
            month: Math.round(d.month_audio_s / 60),
            monthLimit: d.audio_monthly_limit_s ? t("voice.admin.me.of", { n: Math.round(d.audio_monthly_limit_s / 60) }) : "",
          })}
        </p>
      ) : null}
      {d.by_feature.length ? (
        <p className="type-footnote text-label-2">
          {d.by_feature.map((r) => `${labels.feature(String(r.key))}: ${compactTokens(r.tokens, locale)}`).join(" · ")}
        </p>
      ) : null}
      <AiNotice />
    </Card>
  );
}

/** Near / at-limit banner for AI surfaces; renders nothing while the user is below the threshold. */
export function AiUsageBanner() {
  const { t, locale } = useI18n();
  const q = useMyAiUsage();
  const d = q.data;
  if (!d) return null;
  const monthly = (d.monthly_pct ?? 0) >= (d.daily_pct ?? 0);
  const date = resetDate(monthly ? "month" : "day", locale);
  if (d.state === "hard")
    return (
      <Alert tone="error" testId="ai-banner-at">
        {d.org_state === "hard" && (d.pct ?? 0) < 100 ? t("aiAdmin.banner.orgHardUser") : t("aiAdmin.banner.at", { date })}
      </Alert>
    );
  if (d.state === "soft")
    return (
      <Alert tone="warning" testId="ai-banner-near">
        {t("aiAdmin.banner.near", { pct: pctText(d.pct, locale), date })}
      </Alert>
    );
  if (d.state === "org_soft")
    return (
      <Alert tone="info" testId="ai-banner-org">
        {t("aiAdmin.banner.orgSoftUser")}
      </Alert>
    );
  return null;
}
