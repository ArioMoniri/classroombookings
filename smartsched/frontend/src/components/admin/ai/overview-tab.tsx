"use client";
/**
 * Yapay zekâ › Genel bakış: "is anything wrong?" in one screen — this month's KPIs, the org budget meter, each
 * provider's status, the top users and the latest refusals, each with a way to the tab that explains it.
 */
import { Alert, Loading } from "@/components/admin/kit";
import { BarList } from "@/components/ui/bar-list";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAiProviders, useAiRefusals, useAiSummary, useAiUsage } from "@/lib/api/ai-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { Meter, StatTile, StatusWord, Tokens, useAiLabels } from "./ai-kit";
import { compactTokens, errorMessage, meterState, providerLabel, providerStatus, resetDate, usd } from "./ai-model";

export function OverviewTab({ go }: { go: (tab: string) => void }) {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const summary = useAiSummary();
  const providers = useAiProviders();
  const users = useAiUsage("user");
  const refusals = useAiRefusals();
  if (summary.isLoading) return <Loading />;
  if (!summary.data) return <Alert tone="error">{errorMessage(summary.error, locale, t("aiAdmin.error.load"))}</Alert>;
  const org = summary.data.org;
  const blocked = summary.data.by_feature.reduce((a, r) => a + r.refused, 0);
  const connected = (providers.data?.providers ?? []).filter((p) => p.has_credentials && p.config.enabled !== false);
  const fmt = new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-GB");
  return (
    <div className="flex flex-col gap-4" data-testid="ai-overview">
      {org.state === "hard" || org.state === "soft" ? (
        <Alert tone={org.state === "hard" ? "error" : "warning"} testId="ai-org-banner">
          {t(org.state === "hard" ? "aiAdmin.banner.orgHard" : "aiAdmin.banner.orgSoft", { pct: String(Math.round(org.pct ?? 0)) })}
        </Alert>
      ) : null}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile testId="ai-ov-tokens" label={t("aiAdmin.kpi.tokens")} value={<Tokens n={org.month_tokens} />} />
        <StatTile testId="ai-ov-cost" label={t("aiAdmin.kpi.cost")} value={usd(org.month_cost_usd, locale)} note={t("aiAdmin.kpi.costNote")} />
        <StatTile testId="ai-ov-requests" label={t("aiAdmin.kpi.requests")} value={fmt.format(org.month_calls)} />
        <StatTile testId="ai-ov-blocked" label={t("aiAdmin.kpi.blocked")} value={fmt.format(blocked)} />
      </div>
      <Card className="px-4 py-4">
        {org.budget_tokens || org.budget_cost_usd ? (
          <Meter
            pct={org.pct}
            state={meterState(org.pct, org.soft_pct)}
            label={org.budget_tokens ? t("aiAdmin.budget.line", { used: compactTokens(org.month_tokens, locale), limit: compactTokens(org.budget_tokens, locale), date: resetDate("month", locale) }) : t("aiAdmin.budget.lineCost", { used: usd(org.month_cost_usd, locale), limit: usd(org.budget_cost_usd, locale), date: resetDate("month", locale) })}
          />
        ) : (
          <p className="type-callout text-label-2">{t("aiAdmin.budget.none")}</p>
        )}
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="gap-3 px-4 py-4" data-testid="ai-ov-providers">
          <h3 className="type-headline text-label-1">{t("aiAdmin.tab.providers")}</h3>
          {!connected.length && providers.data ? <p className="type-callout text-label-2">{t("aiAdmin.empty.noProvider")}</p> : null}
          <ul className="flex flex-col gap-2">
            {connected.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2">
                <span className="type-callout text-label-1">{providerLabel(p, locale)}</span>
                <StatusWord tone={providerStatus(p)}>{t(`aiAdmin.provider.status.${providerStatus(p)}` as MessageKey)}</StatusWord>
              </li>
            ))}
          </ul>
          <Button variant="outline" className="self-start" onClick={() => go("providers")}>
            {t("aiAdmin.overview.toProviders")}
          </Button>
        </Card>
        <Card className="gap-3 px-4 py-4" data-testid="ai-ov-top">
          <h3 className="type-headline text-label-1">{t("aiAdmin.overview.topUsers")}</h3>
          {users.data?.rows.length ? (
            <BarList aria-label={t("aiAdmin.overview.topUsers")} items={users.data.rows.slice(0, 5).map((r) => ({ key: String(r.key), label: r.label ?? t("aiAdmin.users.system"), value: r.tokens, display: compactTokens(r.tokens, locale) }))} />
          ) : (
            <p className="type-callout text-label-2">{t("aiAdmin.users.empty")}</p>
          )}
          <Button variant="outline" className="self-start" onClick={() => go("usage")}>
            {t("aiAdmin.overview.toUsage")}
          </Button>
        </Card>
      </div>
      <Card className="gap-3 px-4 py-4" data-testid="ai-ov-refusals">
        <h3 className="type-headline text-label-1">{t("aiAdmin.log.title")}</h3>
        {(refusals.data?.rows ?? []).slice(0, 5).map((r) => (
          <p key={r.id} className="type-callout text-label-1">
            {r.user_label ?? t("aiAdmin.users.system")} · {labels.reason(r.reason_code)} · <span className="text-label-2">{labels.feature(r.feature)}</span>
          </p>
        ))}
        {!refusals.data?.rows.length ? <p className="type-callout text-label-2">{t("aiAdmin.log.empty")}</p> : null}
        <Button variant="outline" className="self-start" onClick={() => go("guard")}>
          {t("aiAdmin.overview.toGuard")}
        </Button>
      </Card>
    </div>
  );
}
