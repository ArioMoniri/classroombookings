"use client";
/**
 * The setup sheet of a connector (W3-HUB). Desktop: a wide sheet from the right; phones: a full-width sheet from the
 * bottom (MOBILE M-04), scrolling inside itself, with the primary action sticky above the home indicator (M-05).
 *
 * Content is the owning area's own admin panel, embedded unchanged (read-only reuse):
 *   identity   → Microsoft Entra sign-in (components/identity/sso-settings) + LDAP (components/admin/ldap-settings)
 *                until W3-IDP's IdentityProvidersPanel lands
 *   email      → SMTP + outbox (components/admin/email-settings) until W3-MAIL's EmailSettingsPanel lands
 *   calendar   → calendar sync sign-off + Google / Microsoft 365 OAuth clients (components/settings/calendar-*)
 *   channels   → notification channels (components/channels/channels-admin)
 *   automation → the guided n8n / Activepieces / Pipedream / Zapier setup, or every webhook (webhooks-admin)
 */
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { ChannelsAdmin } from "@/components/channels/channels-admin";
import { EmailSettingsView } from "@/components/admin/email-settings";
import { LdapSettingsView } from "@/components/admin/ldap-settings";
import { SsoSettings } from "@/components/identity/sso-settings";
import { CalendarPushAdmin } from "@/components/settings/calendar-push-admin";
import { CalendarSyncAdmin } from "@/components/settings/calendar-sync-admin";
import { WebhooksAdmin } from "@/components/settings/webhooks-admin";
import { Alert, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { AreaKey, ConnectorCard } from "@/lib/api/integrations";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { StatusPill, cardName } from "./connector-card";
import { GuidedWebhook } from "./guided-webhook";
import { platformOfCard } from "./integrations-model";

export function SetupSheet({ open, cardKey, card, tab, loading, onClose }: { open: boolean; cardKey: string | null; card: ConnectorCard | null; tab: AreaKey; loading: boolean; onClose: () => void }) {
  const { t, locale } = useI18n();
  const phone = useIsPhone();
  const platform = cardKey ? platformOfCard(cardKey) : null;
  const guided = platform !== null || cardKey === "automation.connect";
  const webhookId = typeof card?.ref?.webhook_id === "number" ? card.ref.webhook_id : null;
  const title = card ? cardName(card, locale) : guided ? t("integrations.guided.title") : t(`integrations.tab.${tab}`);
  return (
    <Sheet open={open} onOpenChange={(o) => (o ? undefined : onClose())}>
      <SheetContent
        side={phone ? "bottom" : "right"}
        className={cn("gap-0", phone ? "inset-x-0! bottom-0! max-h-[calc(100dvh-1rem)]! rounded-b-none!" : "w-full data-[side=right]:sm:max-w-2xl")}
        data-testid="setup-sheet"
      >
        <SheetHeader className="px-5 pt-3 pb-2 pr-12">
          <div className="flex flex-wrap items-center gap-2">
            <SheetTitle>{title}</SheetTitle>
            {card ? <StatusPill status={card.status} /> : null}
          </div>
          <SheetDescription>{t("integrations.sheet.lead")}</SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-5 pb-0" data-testid="setup-sheet-body">
          {loading ? <Loading /> : null}
          {!loading && cardKey && !card && !guided ? <Alert tone="warning">{t("integrations.sheet.notFound")}</Alert> : null}
          {guided ? (
            <GuidedWebhook key={`${cardKey}-${webhookId ?? "new"}`} initialPlatform={platform} webhookId={webhookId} />
          ) : (
            <>
              <AreaContent area={tab} card={card} />
              {/* MOBILE M-05: the primary action stays in thumb reach; the panels above save their own fields */}
              <div className="sticky bottom-0 z-10 -mx-5 mt-auto flex justify-end bg-(--mat-thick) px-5 py-3 hairline-t">
                <Button size="lg" onClick={onClose} className="w-full sm:w-auto" data-testid="setup-done">
                  {t("integrations.sheet.done")}
                </Button>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function AreaContent({ area, card }: { area: AreaKey; card: ConnectorCard | null }) {
  const { t } = useI18n();
  const pending = card?.source === "missing" ? <Alert tone="info">{t("integrations.sheet.pending")}</Alert> : null;
  switch (area) {
    case "identity":
      return (
        <div className="grid gap-5">
          {pending}
          <SsoSettings />
          <LdapSettingsView />
        </div>
      );
    case "email":
      return (
        <div className="grid gap-5">
          {pending}
          <EmailSettingsView />
        </div>
      );
    case "calendar":
      return (
        <div className="grid gap-5">
          <CalendarSyncAdmin />
          <CalendarPushAdmin />
        </div>
      );
    case "channels":
      return <ChannelsAdmin />;
    case "automation":
      return <WebhooksAdmin />;
    case "ai":
      return null;
  }
}
