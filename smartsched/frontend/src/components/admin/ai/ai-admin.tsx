"use client";
/**
 * Yönetim › Yapay zekâ (`/admin/ai`, docs/design/v3/ai-admin.md): Genel bakış · Sağlayıcılar · Modeller · Kullanım ·
 * Limitler · Koruma · Yardımcı. Administrators with `planning.admin` or `setup.settings` (the backend checks every call again).
 * The tab lives in the URL (`?tab=`), so a bell notification can open Kullanım directly.
 */
import { useRouter, useSearchParams } from "next/navigation";
import { NoAccess, PageTitle } from "@/components/admin/kit";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { HelperAdminTab } from "@/components/helper/admin/helper-admin";
import { AiNotice } from "./ai-kit";
import { GuardTab } from "./guard-tab";
import { LimitsTab } from "./limits-tab";
import { ModelsTab } from "./models-tab";
import { OverviewTab } from "./overview-tab";
import { ProvidersTab } from "./providers-tab";
import { UsageTab } from "./usage-tab";

export const AI_TABS = ["overview", "providers", "models", "usage", "limits", "guard", "helper"] as const;
export type AiTab = (typeof AI_TABS)[number];

export function AiAdmin() {
  const { t } = useI18n();
  const { can, loading } = usePermissions();
  const router = useRouter();
  const params = useSearchParams();
  const allowed = can(["planning.admin", "setup.settings"]);
  if (loading) return null;
  if (!allowed) return <NoAccess title={t("aiAdmin.noAccessTitle")} body={t("aiAdmin.noAccessBody")} />;
  const requested = params.get("tab");
  const tab: AiTab = (AI_TABS as readonly string[]).includes(requested ?? "") ? (requested as AiTab) : "overview";
  const go = (v: string) => router.replace(`/admin/ai?tab=${v}`);
  return (
    <div className="flex max-w-5xl flex-col" data-testid="ai-admin">
      <PageTitle title={t("aiAdmin.title")} subtitle={t("aiAdmin.lead")} />
      <AiNotice className="mb-4" />
      <Tabs value={tab} onValueChange={(v) => go(String(v))}>
        <div className="mb-5 max-w-full overflow-x-auto">
          <TabsList className="pointer-coarse:h-auto">
            {AI_TABS.map((x) => (
              <TabsTrigger key={x} value={x} className="pointer-coarse:min-h-11" data-testid={`ai-tab-${x}`}>
                {t(`aiAdmin.tab.${x}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="overview">{tab === "overview" ? <OverviewTab go={go} /> : null}</TabsContent>
        <TabsContent value="providers">{tab === "providers" ? <ProvidersTab canEdit={allowed} /> : null}</TabsContent>
        <TabsContent value="models">{tab === "models" ? <ModelsTab canEdit={allowed} /> : null}</TabsContent>
        <TabsContent value="usage">{tab === "usage" ? <UsageTab /> : null}</TabsContent>
        <TabsContent value="limits">{tab === "limits" ? <LimitsTab canEdit={allowed} /> : null}</TabsContent>
        <TabsContent value="guard">{tab === "guard" ? <GuardTab canEdit={allowed} /> : null}</TabsContent>
        {/* HX-09: the helper ("Yardımcı"): on / off, mode, audiences, actions, summary */}
        <TabsContent value="helper">{tab === "helper" ? <HelperAdminTab canEdit={allowed} /> : null}</TabsContent>
      </Tabs>
    </div>
  );
}
