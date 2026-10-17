"use client";
/**
 * The setup sheet shell of a connector (W3-HUB; docs/design/v3/integrations.md §5, §10a, §11). Desktop: a 608 px sheet
 * from the right; phones: a full-screen page with a back button, scrolling inside itself, the primary action sticky
 * above the home indicator (MOBILE M-04 / M-05). Header: monogram, name, status word, "Son değişiklik: <ad>, <zaman>";
 * for configured connectors the "Kullanımda" switch (on phones the gallery rows have none). Focus goes to the heading
 * on open and back to the card on close.
 *
 * Content is the owning area's own admin panel, embedded unchanged (read-only reuse):
 *   identity   → Microsoft Entra sign-in (components/identity/sso-settings) + LDAP (components/admin/ldap-settings)
 *                until W3-IDP's IdentityProvidersPanel lands
 *   email      → SMTP + outbox (components/admin/email-settings) until W3-MAIL's EmailSettingsPanel lands
 *   calendar   → calendar sync sign-off + Google / Microsoft 365 OAuth clients (components/settings/calendar-*)
 *   channels   → notification channels (components/channels/channels-admin)
 *   automation → the guided n8n / Activepieces / Pipedream / Zapier setup, or every webhook (webhooks-admin)
 */
import { ArrowLeft } from "lucide-react";
import { useRef } from "react";
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
import { Switch } from "@/components/ui/switch";
import { AREA_KEYS, type AreaKey, type ConnectorCard } from "@/lib/api/integrations";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Monogram, StatusPill, cardName, useCardLines } from "./connector-card";
import { GuidedWebhook } from "./guided-webhook";
import { platformOfCard, switchState, type HubTab } from "./integrations-model";

/** the area of a card key ("calendar.google" → calendar), else the open tab */
export function areaOf(cardKey: string | null, tab: HubTab): AreaKey | null {
  const head = cardKey?.split(".")[0] ?? "";
  if ((AREA_KEYS as readonly string[]).includes(head)) return head as AreaKey;
  return tab === "all" ? null : tab;
}

interface Props {
  open: boolean;
  cardKey: string | null;
  card: ConnectorCard | null;
  tab: HubTab;
  loading: boolean;
  canEdit: boolean;
  busy: boolean;
  onSwitch: (card: ConnectorCard, next: boolean) => void;
  onClose: () => void;
}

export function SetupSheet({ open, cardKey, card, tab, loading, canEdit, busy, onSwitch, onClose }: Props) {
  const { t, locale } = useI18n();
  const phone = useIsPhone();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const platform = cardKey ? platformOfCard(cardKey) : null;
  const guided = platform !== null || cardKey === "automation.connect";
  const area = areaOf(cardKey, tab);
  const webhookId = typeof card?.ref?.webhook_id === "number" ? card.ref.webhook_id : null;
  const title = card ? cardName(card, locale) : guided ? t("integrations.guided.title") : area ? t(`integrations.tab.${area}`) : t("integrations.title");
  return (
    <Sheet open={open} onOpenChange={(o) => (o ? undefined : onClose())}>
      <SheetContent
        side={phone ? "bottom" : "right"}
        initialFocus={headingRef}
        className={cn("gap-0", phone ? "inset-0! top-0! bottom-0! h-dvh! max-h-dvh! rounded-none! pt-0!" : "w-full data-[side=right]:sm:max-w-[608px]")}
        data-testid="setup-sheet"
      >
        <SheetHeader className="gap-2 px-5 pt-3 pb-3 pr-12 hairline-b">
          {phone ? (
            <Button variant="ghost" size="md" onClick={onClose} className="-ml-2 self-start pointer-coarse:min-h-11" data-testid="setup-back">
              <ArrowLeft aria-hidden />
              {t("integrations.sheet.back")}
            </Button>
          ) : null}
          <div className="flex items-center gap-3">
            {card ? <Monogram card={card} /> : null}
            <div className="min-w-0 flex-1">
              <SheetTitle ref={headingRef} tabIndex={-1} className="focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid="setup-title">
                {title}
              </SheetTitle>
              {card ? <StatusPill status={card.status} /> : null}
            </div>
          </div>
          {card ? <HeaderLines card={card} /> : null}
          <SheetDescription>{t("integrations.sheet.lead")}</SheetDescription>
          {card?.toggle && canEdit ? (
            <label className="flex items-center justify-between gap-3 rounded-xl bg-fill-2 px-3 py-1 type-callout text-label-1 pointer-coarse:min-h-11" data-testid="setup-inuse">
              <span aria-hidden>{t("integrations.card.inUse")}</span>
              <Switch checked={switchState(card).checked} disabled={busy} onCheckedChange={(next) => onSwitch(card, next)} aria-label={t("integrations.card.switchLabel", { name: cardName(card, locale) })} />
            </label>
          ) : null}
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-5 pt-4 pb-0" data-testid="setup-sheet-body">
          {loading ? <Loading /> : null}
          {!loading && cardKey && !card && !guided ? <Alert tone="warning">{t("integrations.sheet.notFound")}</Alert> : null}
          {!canEdit ? <Alert tone="info">{t("integrations.readOnly")}</Alert> : null}
          {loading ? null : guided && canEdit ? (
            <GuidedWebhook key={`${cardKey}-${webhookId ?? "new"}`} initialPlatform={platform} webhookId={webhookId} />
          ) : (
            <>
              {canEdit && area ? <AreaContent area={area} card={card} /> : null}
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

function HeaderLines({ card }: { card: ConnectorCard }) {
  const lines = useCardLines(card);
  return (
    <div className="grid gap-0.5 type-footnote text-label-2" data-testid="setup-lines">
      <p title={lines.checkTitle}>{lines.check}</p>
      <p>{lines.change}</p>
    </div>
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
