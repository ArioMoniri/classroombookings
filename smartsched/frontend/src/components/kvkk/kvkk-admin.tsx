"use client";
/**
 * Yönetim › KVKK (A4): the request queue (`setup.users`), retention periods, the privacy notice and the data inventory
 * (`setup.settings`). Each tab is shown only to the permission the backend checks. The privacy-notice gate never opens
 * on this page, so an administrator can always write and publish a notice.
 */
import { useRouter, useSearchParams } from "next/navigation";
import { PageTitle } from "@/components/admin/kit";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { DsrQueue } from "./dsr-queue";
import { InventoryTable } from "./inventory-table";
import { NoticeEditor } from "./notice-editor";
import { RetentionEditor } from "./retention-editor";

export function KvkkAdmin() {
  const { t } = useI18n();
  const { can } = usePermissions();
  const router = useRouter();
  const params = useSearchParams();
  const tabs = [
    { value: "requests", label: t("kvkk.tabs.requests"), show: can("setup.users") },
    { value: "notice", label: t("kvkk.tabs.notice"), show: can("setup.settings") },
    { value: "retention", label: t("kvkk.tabs.retention"), show: can("setup.settings") },
    { value: "inventory", label: t("kvkk.tabs.inventory"), show: can("setup.settings") },
  ].filter((x) => x.show);
  const requested = params.get("tab");
  const tab = tabs.some((x) => x.value === requested) ? requested! : (tabs[0]?.value ?? "requests");
  return (
    <div className="flex max-w-5xl flex-col" data-testid="kvkk-admin">
      <PageTitle title={t("kvkk.title")} subtitle={t("kvkk.lead")} />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/admin/kvkk?tab=${String(v)}`)}>
        <div className="mb-5 max-w-full overflow-x-auto">
          <TabsList className="pointer-coarse:h-auto">
            {tabs.map((x) => (
              <TabsTrigger key={x.value} value={x.value} className="pointer-coarse:min-h-11" data-testid={`kvkk-tab-${x.value}`}>
                {x.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {can("setup.users") ? (
          <TabsContent value="requests">
            <DsrQueue />
          </TabsContent>
        ) : null}
        {can("setup.settings") ? (
          <>
            <TabsContent value="notice">
              <NoticeEditor />
            </TabsContent>
            <TabsContent value="retention">
              <RetentionEditor />
            </TabsContent>
            <TabsContent value="inventory">
              <InventoryTable />
            </TabsContent>
          </>
        ) : null}
      </Tabs>
    </div>
  );
}
