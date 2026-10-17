"use client";
/**
 * Yönetim › Karşılama rehberi (`/admin/welcome`, spec §4.6, wireframes welcome-admin-{1440,390}.svg): Genel ·
 * Metinler · Tamamlanma. Permission `setup.settings` or `planning.admin` (the backend checks every call again).
 * The tab lives in the URL (`?tab=`). Calm by default: the four part switches up front, the rest under "Gelişmiş".
 */
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { NoAccess, PageTitle } from "@/components/admin/kit";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWelcomeEvent } from "@/lib/api/welcome";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { WelcomeGeneral } from "./welcome-general";
import { WelcomeStatsTab } from "./welcome-stats";
import { WelcomeTexts } from "./welcome-texts";

export const WELCOME_TABS = ["general", "texts", "stats"] as const;
export type WelcomeTab = (typeof WELCOME_TABS)[number];
export const WELCOME_ADMIN_PERMS = ["setup.settings", "planning.admin"];

export function WelcomeAdmin() {
  const { t } = useI18n();
  const { can, loading } = usePermissions();
  const router = useRouter();
  const params = useSearchParams();
  const event = useWelcomeEvent();
  const allowed = can(WELCOME_ADMIN_PERMS);
  // the admin checklist's view-only item "Karşılama rehberine göz atın" (also posted by the provider on this route)
  useEffect(() => {
    if (allowed) event.mutate({ guide_key: "checklist", event: "item_done", item: "welcome_reviewed" });
    // once per visit
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed]);
  if (loading) return null;
  if (!allowed) return <NoAccess title={t("welcome.admin.noAccessTitle")} body={t("welcome.admin.noAccessBody")} />;
  const requested = params.get("tab");
  const tab: WelcomeTab = (WELCOME_TABS as readonly string[]).includes(requested ?? "") ? (requested as WelcomeTab) : "general";
  const go = (v: string) => router.replace(`/admin/welcome?tab=${v}`);
  return (
    <div className="flex max-w-5xl flex-col" data-testid="welcome-admin">
      <PageTitle title={t("welcome.admin.title")} subtitle={t("welcome.admin.lead")} />
      <Tabs value={tab} onValueChange={(v) => go(String(v))}>
        <div className="mb-5 max-w-full overflow-x-auto">
          <TabsList className="pointer-coarse:h-auto">
            {WELCOME_TABS.map((x) => (
              <TabsTrigger key={x} value={x} className="pointer-coarse:min-h-11" data-testid={`welcome-tab-${x}`}>
                {t(`welcome.admin.tab.${x}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="general">{tab === "general" ? <WelcomeGeneral /> : null}</TabsContent>
        <TabsContent value="texts">{tab === "texts" ? <WelcomeTexts /> : null}</TabsContent>
        <TabsContent value="stats">{tab === "stats" ? <WelcomeStatsTab /> : null}</TabsContent>
      </Tabs>
    </div>
  );
}
