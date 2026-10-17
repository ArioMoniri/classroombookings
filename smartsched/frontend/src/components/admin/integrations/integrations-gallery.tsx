"use client";
/**
 * Yönetim › Entegrasyonlar (`/admin/integrations`, wave 3b W3-HUB; docs/design/v3/integrations.md): a gallery of
 * connector cards in six tabs — Kimlik · E-posta · Takvim · Kanallar · Webhook ve otomasyon · Yapay zekâ. Each card
 * shows its status (GET /integrations/status, organisation-wide), last check and last change; "Kur" / "Düzenle"
 * opens the setup sheet with the owning area's own admin panel (embedded as is, never rewritten here) or, for the
 * automation platforms, the guided webhook setup. The switch calls the area's own endpoint.
 *
 * URL state: `?tab=<area>&setup=<card key>` (a deep link opens the sheet; closing returns focus to the card).
 * Phones: one column, the sheet comes from the bottom with its primary action sticky, 44 px targets, 16 px inputs.
 */
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, ConfirmDialog, Loading, NoAccess, PageTitle } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { HttpError } from "@/lib/api/client";
import { problemText } from "@/lib/api/error-text";
import { useIntegrationsStatus, useToggleConnector, type AreaKey, type ConnectorCard, type IntegrationArea } from "@/lib/api/integrations";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { ConnectorCardView, cardName } from "./connector-card";
import { TABS, countsLine, galleryHref, parseSetupHref, sortCards, switchIntent, tabOf } from "./integrations-model";
import { SetupSheet } from "./setup-sheet";

export const HUB_PERMS = ["setup.settings", "planning.admin"];

export function IntegrationsGallery() {
  const { t } = useI18n();
  const { can, loading } = usePermissions();
  if (loading) return <Loading />;
  if (!can(HUB_PERMS)) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("integrations.noAccess")} />;
  return <GalleryBody />;
}

function GalleryBody() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const status = useIntegrationsStatus();
  const toggle = useToggleConnector();
  const tab = tabOf(params.get("tab"));
  const setupKey = params.get("setup");
  const [confirmOff, setConfirmOff] = useState<ConnectorCard | null>(null);
  const triggers = useRef(new Map<string, HTMLButtonElement | null>());
  const lastKey = useRef<string | null>(null);

  const go = useCallback((next: AreaKey, setup?: string | null) => router.replace(galleryHref(next, setup), { scroll: false }), [router]);

  const forbidden = status.error instanceof HttpError && status.error.status === 403;
  if (forbidden) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("integrations.noAccess")} />;

  const areas = status.data?.areas ?? [];
  const byKey = new Map(areas.flatMap((a) => a.cards.map((c) => [c.key, c] as const)));
  const openCard = setupKey ? (byKey.get(setupKey) ?? null) : null;

  const openSetup = (card: ConnectorCard) => {
    const target = parseSetupHref(card.setup_href);
    if (!target) {
      router.push(card.setup_href);
      return;
    }
    lastKey.current = card.key;
    go(target.tab, target.setup ?? card.key);
  };

  const flip = (card: ConnectorCard, on: boolean) => {
    if (!card.toggle) return;
    const name = cardName(card, locale);
    toggle.mutate(
      { card, toggle: card.toggle, on },
      {
        onSuccess: () => toast.success(t(on ? "integrations.toast.on" : "integrations.toast.off", { name })),
        onError: (e) => toast.error(t("integrations.toast.failed", { reason: problemText(e, locale) ?? (e as Error).message })),
        onSettled: () => {
          setConfirmOff(null);
          requestAnimationFrame(() => triggers.current.get(card.key)?.focus());
        },
      },
    );
  };

  const onSwitch = (card: ConnectorCard, next: boolean) => {
    const intent = switchIntent(card, next);
    if (intent === "confirm_off") setConfirmOff(card);
    else if (intent === "open_setup") openSetup(card);
    else if (intent === "toggle") flip(card, next);
  };

  const closeSetup = () => {
    const key = setupKey ?? lastKey.current;
    go(tab, null);
    void qc.invalidateQueries({ queryKey: ["integrations"] });
    // focus back to the card that opened the sheet (never to <body>)
    requestAnimationFrame(() => {
      const el = key ? triggers.current.get(key) : null;
      (el ?? document.querySelector<HTMLElement>(`[data-testid="integrations-tab-${tab}"]`))?.focus();
    });
  };

  const counts = countsLine(status.data?.counts ?? {});
  return (
    <div className="flex max-w-6xl flex-col gap-4" data-testid="integrations-gallery">
      <PageTitle
        title={t("integrations.title")}
        subtitle={t("integrations.lead")}
        actions={
          <Button variant="outline" size="md" onClick={() => void status.refetch().then(() => toast.success(t("integrations.toast.refreshed")))} disabled={status.isFetching} className="pointer-coarse:min-h-11" data-testid="integrations-refresh">
            <RefreshCw aria-hidden className={status.isFetching ? "animate-spin motion-reduce:animate-none" : undefined} />
            {t("integrations.refresh")}
          </Button>
        }
      />
      <p className="type-footnote text-label-2" data-testid="integrations-shared">
        {t("integrations.shared")}
      </p>
      {status.data ? (
        <p className="type-callout text-label-1" data-testid="integrations-summary" aria-live="polite">
          {t("integrations.summary", counts)}
        </p>
      ) : null}
      {status.isLoading ? <Loading /> : null}
      {status.isError && !forbidden ? (
        <Alert tone="error">
          <span className="block">{t("integrations.loadError")}</span>
          <Button size="sm" variant="outline" className="mt-2 pointer-coarse:min-h-11" onClick={() => void status.refetch()}>
            {t("integrations.retry")}
          </Button>
        </Alert>
      ) : null}
      <Tabs value={tab} onValueChange={(v) => go(tabOf(String(v)))}>
        {/* six tabs scroll sideways on phones (the track is max-content wide) */}
        <div className="-mx-1 mb-4 max-w-full overflow-x-auto px-1">
          <TabsList className="pointer-coarse:h-auto">
            {TABS.map((x) => (
              <TabsTrigger key={x} value={x} className="pointer-coarse:min-h-11" data-testid={`integrations-tab-${x}`}>
                {t(`integrations.tab.${x}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {TABS.map((x) => (
          <TabsContent key={x} value={x}>
            {x === tab ? <AreaPanel area={x} data={areas.find((a) => a.key === x)} busyKey={toggle.isPending ? (toggle.variables?.card.key ?? null) : null} onPrimary={openSetup} onSwitch={onSwitch} registerTrigger={(k, el) => triggers.current.set(k, el)} /> : null}
          </TabsContent>
        ))}
      </Tabs>
      <SetupSheet open={setupKey !== null} cardKey={setupKey} card={openCard} tab={tab} loading={status.isLoading} onClose={closeSetup} />
      <ConfirmDialog
        open={confirmOff !== null}
        onOpenChange={(o) => {
          if (!o) {
            const key = confirmOff?.key;
            setConfirmOff(null);
            requestAnimationFrame(() => (key ? triggers.current.get(key)?.focus() : undefined));
          }
        }}
        title={confirmOff ? t("integrations.confirmOff.title", { name: cardName(confirmOff, locale) }) : ""}
        description={t("integrations.confirmOff.body")}
        confirmLabel={t("integrations.confirmOff.confirm")}
        destructive
        busy={toggle.isPending}
        onConfirm={() => confirmOff && flip(confirmOff, false)}
      />
    </div>
  );
}

function AreaPanel({
  area,
  data,
  busyKey,
  onPrimary,
  onSwitch,
  registerTrigger,
}: {
  area: AreaKey;
  data: IntegrationArea | undefined;
  busyKey: string | null;
  onPrimary: (card: ConnectorCard) => void;
  onSwitch: (card: ConnectorCard, next: boolean) => void;
  registerTrigger: (key: string, el: HTMLButtonElement | null) => void;
}) {
  const { t } = useI18n();
  const cards = sortCards(data?.cards ?? []);
  return (
    <section aria-labelledby={`integrations-${area}-h`} className="grid gap-3" data-testid={`integrations-panel-${area}`}>
      <h2 id={`integrations-${area}-h`} className="sr-only">
        {t("integrations.card.list", { area: t(`integrations.tab.${area}`) })}
      </h2>
      <p className="type-callout text-label-2">{t(`integrations.tabLead.${area}`)}</p>
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {cards.map((c) => (
          <li key={c.key}>
            <ConnectorCardView ref={(el) => registerTrigger(c.key, el)} card={c} busy={busyKey === c.key} onPrimary={onPrimary} onSwitch={onSwitch} />
          </li>
        ))}
      </ul>
      {area === "ai" ? (
        <p className="type-callout text-label-2">
          {t("integrations.ai.lead")}{" "}
          <Link href="/admin/ai" className="text-tint-text underline-offset-2 hover:underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center" data-testid="integrations-ai-link">
            {t("integrations.ai.open")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
