"use client";
/**
 * Yönetim › Entegrasyonlar (`/admin/integrations`, wave 3b W3-HUB; docs/design/v3/integrations.md §3–§4, §10a, §11).
 *
 * Tabs Tümü · Kimlik · E-posta · Takvim · Kanallar · Webhook ve otomasyon · Yapay zekâ (each with its count), a search,
 * the summary line ("6 bağlı · 1 hata · 9 yapılandırılmadı") and a pinned "Dikkat isteyen" row for cards in error.
 * Cards keep the backend's fixed order (no reordering when a status changes). "Kur" / "Yönet" opens the setup sheet
 * with the owning area's own panel or the guided webhook setup; the switch calls the area's own endpoint. Every
 * value is organisation-wide (GET /integrations/status); planning admins without `setup.settings` see the same cards
 * read-only.
 *
 * URL: `?area=<area>&setup=<card key>` (the older `?tab=` is read too); `/admin/integrations/<key>` redirects here.
 * Phones: 64 px rows that open the sheet (the switch moves into the sheet), 44 px targets, 16 px inputs.
 */
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, ConfirmDialog, Loading, NoAccess, PageTitle } from "@/components/admin/kit";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { HttpError } from "@/lib/api/client";
import { problemText } from "@/lib/api/error-text";
import { useIntegrationsStatus, useToggleConnector, type AreaKey, type ConnectorCard, type IntegrationArea } from "@/lib/api/integrations";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { ConnectorCardView, StatusPill, cardName } from "./connector-card";
import { TABS, attentionCards, countsLine, galleryHref, matches, parseSetupHref, switchIntent, tabOf, type HubTab } from "./integrations-model";
import { SetupSheet } from "./setup-sheet";

export const HUB_PERMS = ["setup.settings", "planning.admin"];
/** configure, test, switch: `setup.settings` (spec §1); `planning.admin` alone reads */
export const EDIT_PERM = "setup.settings";

export function IntegrationsGallery() {
  const { t } = useI18n();
  const { can, loading } = usePermissions();
  if (loading) return <Loading />;
  if (!can(HUB_PERMS)) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("integrations.noAccess")} />;
  return <GalleryBody canEdit={can(EDIT_PERM)} />;
}

function GalleryBody({ canEdit }: { canEdit: boolean }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const phone = useIsPhone();
  const status = useIntegrationsStatus();
  const toggle = useToggleConnector();
  const tab = tabOf(params.get("area") ?? params.get("tab"));
  const setupKey = params.get("setup");
  const [q, setQ] = useState("");
  const [confirmOff, setConfirmOff] = useState<ConnectorCard | null>(null);
  const triggers = useRef(new Map<string, HTMLButtonElement | null>());
  const lastKey = useRef<string | null>(null);

  const go = useCallback((next: HubTab, setup?: string | null) => router.replace(galleryHref(next, setup), { scroll: false }), [router]);

  const forbidden = status.error instanceof HttpError && status.error.status === 403;
  if (forbidden) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("integrations.noAccess")} />;

  const areas = status.data?.areas ?? [];
  const all = areas.flatMap((a) => a.cards);
  const byKey = new Map(all.map((c) => [c.key, c] as const));
  // `setup` is a card key; an area may also link with its own short name (`?area=identity&setup=entra`)
  const openCard = setupKey ? (byKey.get(setupKey) ?? (tab !== "all" ? byKey.get(`${tab}.${setupKey}`) : undefined) ?? all.find((c) => c.key.endsWith(`.${setupKey}`)) ?? null) : null;
  const sheetKey = openCard?.key ?? setupKey;
  const attention = attentionCards(all);
  const shown = (tab === "all" ? areas : areas.filter((a) => a.key === tab)).map((a) => ({ ...a, cards: a.cards.filter((c) => matches(c, q)) })).filter((a) => a.cards.length > 0);
  const focusCard = (key: string | null | undefined) =>
    requestAnimationFrame(() => {
      const el = key ? triggers.current.get(key) : null;
      (el ?? document.querySelector<HTMLElement>(`[data-testid="integrations-tab-${tab}"]`))?.focus();
    });

  const openSetup = (card: ConnectorCard) => {
    const target = parseSetupHref(card.setup_href);
    if (!target) {
      router.push(card.setup_href);
      return;
    }
    lastKey.current = card.key;
    go(tab === "all" ? "all" : target.tab, card.key);
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
          if (!setupKey) focusCard(card.key);
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
    const key = sheetKey ?? lastKey.current;
    go(tab, null);
    void qc.invalidateQueries({ queryKey: ["integrations"] });
    focusCard(key); // back to the card that opened the sheet, never <body>
  };

  const counts = countsLine(status.data?.counts ?? {});
  const tabCount = (x: HubTab) => (x === "all" ? all.length : (areas.find((a) => a.key === x)?.cards.length ?? 0));
  const tabLabel = (x: HubTab) => t(x === "all" ? "integrations.tab.all" : `integrations.tab.${x}`);
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
      <div className="relative max-w-md">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-label-3" />
        <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("integrations.search")} aria-label={t("integrations.search")} className="pl-9 pointer-coarse:min-h-11 pointer-coarse:text-base" data-testid="integrations-search" />
      </div>
      {status.data ? (
        <p className="type-callout text-label-1" data-testid="integrations-summary">
          {t("integrations.summary", counts)}
        </p>
      ) : null}
      {status.isLoading ? <Loading /> : null}
      {status.isError && !forbidden ? (
        <Alert tone={status.data ? "warning" : "error"}>
          <span className="block">{t("integrations.loadError")}</span>
          <Button size="sm" variant="outline" className="mt-2 pointer-coarse:min-h-11" onClick={() => void status.refetch()}>
            {t("integrations.retry")}
          </Button>
        </Alert>
      ) : null}
      <AttentionRow cards={attention} onFix={openSetup} />
      <Tabs value={tab} onValueChange={(v) => go(tabOf(String(v)))}>
        {/* seven tabs scroll sideways on phones (the track is max-content wide) */}
        <div className="-mx-1 mb-4 max-w-full overflow-x-auto px-1">
          <TabsList className="pointer-coarse:h-auto">
            {TABS.map((x) => (
              <TabsTrigger key={x} value={x} className="pointer-coarse:min-h-11" data-testid={`integrations-tab-${x}`}>
                {tabLabel(x)}
                {status.data ? (
                  <span className="ml-1 tabular-nums text-label-2" title={t("integrations.tabCountName", { label: tabLabel(x), n: tabCount(x) })}>
                    {tabCount(x)}
                  </span>
                ) : null}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {TABS.map((x) => (
          <TabsContent key={x} value={x} className="grid gap-6" data-testid={`integrations-panel-${x}`}>
            {x === tab ? (
              <>
                {q && shown.length === 0 ? <p className="type-callout text-label-2">{t("integrations.emptySearch", { q })}</p> : null}
                {shown.map((a) => (
                  <AreaSection key={a.key} area={a} heading={tab === "all"} phone={phone} canEdit={canEdit} busyKey={toggle.isPending ? (toggle.variables?.card.key ?? null) : null} onPrimary={openSetup} onSwitch={onSwitch} registerTrigger={(k, el) => triggers.current.set(k, el)} />
                ))}
              </>
            ) : null}
          </TabsContent>
        ))}
      </Tabs>
      <SetupSheet open={setupKey !== null} cardKey={sheetKey} card={openCard} tab={tab} loading={status.isLoading} canEdit={canEdit} busy={toggle.isPending} onSwitch={onSwitch} onClose={closeSetup} />
      <ConfirmDialog
        open={confirmOff !== null}
        onOpenChange={(o) => {
          if (!o) {
            const key = confirmOff?.key;
            setConfirmOff(null);
            if (!setupKey) focusCard(key);
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

/** "Dikkat isteyen": cards in error, one line each + "Sorunu gider" (spec §3, §10a: polite status on change). */
function AttentionRow({ cards, onFix }: { cards: ConnectorCard[]; onFix: (card: ConnectorCard) => void }) {
  const { t, locale } = useI18n();
  return (
    <div role="status" aria-live="polite">
      {cards.length ? (
        <section aria-labelledby="integrations-attention-h" className="grid gap-2 rounded-2xl bg-status-infeasible px-4 py-3" data-testid="integrations-attention">
          <h2 id="integrations-attention-h" className="type-headline text-status-infeasible-fg">
            {t("integrations.attention")}
          </h2>
          <ul className="grid gap-2">
            {cards.map((c) => {
              const name = cardName(c, locale);
              const detail = locale === "tr" ? c.detail_tr : c.detail_en;
              return (
                <li key={c.key} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 type-callout text-label-1">
                    <span className="font-semibold">{name}</span>
                    {detail ? <span className="text-label-2"> · {detail}</span> : null}
                  </span>
                  <Button size="sm" variant="outline" onClick={() => onFix(c)} aria-label={t("integrations.fixFor", { name })} className="pointer-coarse:min-h-11" data-testid={`attention-fix-${c.key}`}>
                    {t("integrations.fix")}
                  </Button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function AreaSection({
  area,
  heading,
  phone,
  canEdit,
  busyKey,
  onPrimary,
  onSwitch,
  registerTrigger,
}: {
  area: IntegrationArea;
  heading: boolean;
  phone: boolean;
  canEdit: boolean;
  busyKey: string | null;
  onPrimary: (card: ConnectorCard) => void;
  onSwitch: (card: ConnectorCard, next: boolean) => void;
  registerTrigger: (key: string, el: HTMLButtonElement | null) => void;
}) {
  const { t } = useI18n();
  const key = area.key as AreaKey;
  const hid = `integrations-${key}-h`;
  return (
    <section aria-labelledby={hid} className="grid gap-3" data-testid={`integrations-area-${key}`}>
      <h2 id={hid} className={heading ? "type-title-3 text-label-1" : "sr-only"}>
        {t(`integrations.tab.${key}`)}
      </h2>
      <p className="type-footnote text-label-2">{t(`integrations.tabLead.${key}`)}</p>
      <ul className={phone ? "grid gap-2" : "grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"}>
        {area.cards.map((c) => (
          <li key={c.key}>
            <ConnectorCardView ref={(el) => registerTrigger(c.key, el)} card={c} row={phone} canEdit={canEdit} busy={busyKey === c.key} onPrimary={onPrimary} onSwitch={onSwitch} />
          </li>
        ))}
      </ul>
      {key === "ai" ? (
        <p className="type-footnote text-label-2">
          {t("integrations.ai.lead")}{" "}
          <Link href="/admin/ai" className="text-tint-text underline-offset-2 hover:underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center" data-testid="integrations-ai-link">
            {t("integrations.ai.open")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}

export { StatusPill };
