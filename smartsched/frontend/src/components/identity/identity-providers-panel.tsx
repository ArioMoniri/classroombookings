"use client";
/**
 * `IdentityProvidersPanel` (wave 3b W3-IDP): every sign-in provider of the organisation, set by administrators and
 * shared by all of them (design docs/design/v3/integrations.md §4.1-§4.3, §5). Embedded by W3-HUB in
 * /admin/integrations (tab "Kimlik") and reachable in Settings › Kimlik sağlayıcıları.
 *
 * - The list in the /login button order (up/down buttons, keyboard reachable), each row with its monogram, status word
 *   (Bağlı / Yapılandırılmadı / Hata / Kapalı), last check, "Son değişiklik: <ad>, <zaman>", "Kur" / "Yönet" and the
 *   "Kullanımda" switch. Switching on without a passed test opens the guided setup at the missing step; switching off
 *   asks first (the backend refuses when it would leave an administrator without a way in).
 * - "+ Sağlayıcı ekle": the gallery of kinds with their presets (text badges, no logo assets); LDAP links to its own
 *   settings.
 * - Invitations per provider (components/identity/invites-panel).
 */
import { ArrowDown, ArrowUp, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog, Loading } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { Button, IconButton } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { apiProblem } from "@/lib/api/identity";
import { problemText } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";
import { idp, useIdpMutation, useKinds, useProviders, type KindCard, type Provider, type ProviderKind } from "./providers-api";
import { changedLine, Monogram, ProviderWizard, StatusWord } from "./provider-wizard";
import { InvitesPanel } from "./invites-panel";

type View = { kind: "list" } | { kind: "gallery" } | { kind: "setup"; id: number };

export function IdentityProvidersPanel({ initialSetup = null, showInvites = true }: { initialSetup?: string | null; showInvites?: boolean }) {
  const { t, locale } = useI18n();
  const q = useProviders();
  const [view, setView] = useState<View | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <Alert tone="error">{problemText(q.error, locale) ?? t("identity.loadError")}</Alert>;
  const list = q.data;
  const current: View = view ?? (initialSetup ? (list.providers.find((p) => p.name === initialSetup) ? { kind: "setup", id: list.providers.find((p) => p.name === initialSetup)!.id } : { kind: "list" }) : { kind: "list" });
  if (current.kind === "setup") return <ProviderWizard providerId={current.id} onBack={() => setView({ kind: "list" })} />;
  if (current.kind === "gallery") return <Gallery onBack={() => setView({ kind: "list" })} onCreated={(p) => setView({ kind: "setup", id: p.id })} existing={list.providers} />;
  return (
    <div className="flex flex-col gap-5" data-testid="identity-providers-panel">
      <Card>
        <CardHeader>
          <CardTitle>{t("identity.title")}</CardTitle>
          <CardDescription>{t("identity.lead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {list.providers.length ? (
            <ul className="flex flex-col" data-testid="idp-list">
              {list.providers.map((p, i) => (
                <ProviderRow key={p.id} p={p} first={i === 0} last={i === list.providers.length - 1} ids={list.providers.map((x) => x.id)} onSetup={() => setView({ kind: "setup", id: p.id })} />
              ))}
            </ul>
          ) : (
            <p className="type-callout text-label-2" data-testid="idp-empty">
              {t("identity.empty")}
            </p>
          )}
          <div className="flex items-center gap-3 py-2 hairline-t" data-testid="idp-ldap">
            <Monogram text={list.ldap.badge} />
            <div className="min-w-0 flex-1">
              <p className="type-callout font-semibold text-label-1">{locale === "en" ? list.ldap.label_en : list.ldap.label}</p>
              <p className="type-footnote text-label-2">{t(list.ldap.enabled ? "identity.status.connected" : list.ldap.configured ? "identity.status.disabled" : "identity.status.not_configured")}</p>
            </div>
            <Link href={list.ldap.settings_href} className="inline-flex min-h-11 items-center rounded-lg px-3 type-callout text-(--accent) underline sm:min-h-9">
              {t("identity.manage")}
            </Link>
          </div>
          <div>
            <Button variant="outline" className="min-h-11 sm:min-h-9" onClick={() => setView({ kind: "gallery" })} data-testid="idp-add">
              <Plus aria-hidden />
              {t("identity.add")}
            </Button>
          </div>
          {list.break_glass_admins < 1 ? <Alert tone="warning">{t("identity.noBreakGlass")}</Alert> : null}
        </CardContent>
      </Card>
      {showInvites ? <InvitesPanel providers={list.providers} /> : null}
    </div>
  );
}

function lastCheck(t: ReturnType<typeof useI18n>["t"], p: Provider, locale: string): string {
  if (!p.last_check_at) return t("identity.neverChecked");
  const d = new Date(p.last_check_at);
  const when = Number.isNaN(d.getTime()) ? p.last_check_at : d.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Istanbul" });
  return t(p.last_check_ok ? "identity.checkedOk" : "identity.checkedFail", { when });
}

function ProviderRow({ p, first, last, ids, onSetup }: { p: Provider; first: boolean; last: boolean; ids: number[]; onSetup: () => void }) {
  const { t, locale } = useI18n();
  const [confirmOff, setConfirmOff] = useState(false);
  const toggle = useIdpMutation((enabled: boolean) => idp.put(p.id, { version: p.version, enabled }));
  const order = useIdpMutation((next: number[]) => idp.order(next));
  const name = locale === "en" ? p.label_en : p.label;
  const fail = (e: unknown) => toast.error(problemText(e, locale) ?? apiProblem(e, locale).text ?? t("identity.saveFailed"));
  const move = (dir: -1 | 1) => {
    const i = ids.indexOf(p.id);
    const next = [...ids];
    [next[i], next[i + dir]] = [next[i + dir], next[i]];
    order.mutate(next, { onError: fail });
  };
  return (
    <li className="flex flex-wrap items-center gap-3 py-3 hairline-b" data-testid={`idp-row-${p.name}`}>
      <Monogram text={p.badge} />
      <div className="min-w-0 flex-1">
        <p className="type-callout font-semibold text-label-1">{name}</p>
        <p className="type-footnote text-label-2">
          <StatusWord status={p.status} /> · {lastCheck(t, p, locale)}
        </p>
        <p className="type-footnote text-label-3">{changedLine(t, p, locale)}</p>
        {p.status === "error" && p.last_check_detail ? <p className="type-footnote text-(--infeasible)">{p.last_check_detail}</p> : null}
      </div>
      <div className="flex items-center gap-1">
        <IconButton label={t("identity.moveUp", { name })} size="sm" disabled={first || order.isPending} onClick={() => move(-1)} className="pointer-coarse:size-11">
          <ArrowUp />
        </IconButton>
        <IconButton label={t("identity.moveDown", { name })} size="sm" disabled={last || order.isPending} onClick={() => move(1)} className="pointer-coarse:size-11">
          <ArrowDown />
        </IconButton>
      </div>
      <Button variant={p.configured ? "secondary" : "default"} size="sm" className="min-h-11 sm:min-h-9" onClick={onSetup} data-testid={`idp-setup-${p.name}`}>
        {t(p.configured ? "identity.manage" : "identity.setup")}
      </Button>
      {p.configured ? (
        <span className="flex items-center gap-2">
          <Switch
            aria-label={t("identity.inUse", { name })}
            checked={p.enabled}
            disabled={toggle.isPending}
            onCheckedChange={(on) => {
              if (on && !p.test_ok) return onSetup(); // the switch opens the sheet at the missing step (§4.1)
              if (!on) return setConfirmOff(true);
              toggle.mutate(true, { onError: fail, onSuccess: () => toast.success(t("identity.enable.enabled", { name })) });
            }}
            data-testid={`idp-switch-${p.name}`}
          />
        </span>
      ) : null}
      <ConfirmDialog
        open={confirmOff}
        onOpenChange={setConfirmOff}
        title={t("identity.off.title", { name })}
        description={t("identity.off.body", { n: p.identities })}
        confirmLabel={t("identity.off.confirm")}
        destructive
        busy={toggle.isPending}
        onConfirm={() => toggle.mutate(false, { onError: fail, onSettled: () => setConfirmOff(false) })}
      />
    </li>
  );
}

function Gallery({ onBack, onCreated, existing }: { onBack: () => void; onCreated: (p: Provider) => void; existing: Provider[] }) {
  const { t, locale } = useI18n();
  const kinds = useKinds();
  const create = useIdpMutation((b: { kind: ProviderKind; preset?: string }) => idp.create(b));
  const taken = new Set(existing.map((p) => p.kind));
  const pick = (kind: ProviderKind, preset?: string) =>
    create.mutate({ kind, preset }, { onSuccess: onCreated, onError: (e) => toast.error(problemText(e, locale) ?? apiProblem(e, locale).text ?? t("identity.saveFailed")) });
  return (
    <div className="flex flex-col gap-4" data-testid="idp-gallery">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="md" onClick={onBack} className="-ml-2 pointer-coarse:min-h-11">
          {t("identity.back")}
        </Button>
        <h2 className="type-title-3 text-label-1">{t("identity.add")}</h2>
      </div>
      {kinds.isLoading ? <Loading /> : null}
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {(kinds.data ?? []).map((k: KindCard) => {
          const single = (k.kind === "entra" || k.kind === "google_workspace") && taken.has(k.kind);
          return (
            <li key={k.kind} className="flex flex-col gap-3 rounded-2xl bg-(--mat) p-4 shadow-[inset_0_0_0_1px_var(--border-control)]" data-testid={`idp-kind-${k.kind}`}>
              <div className="flex items-center gap-3">
                <Monogram text={k.badge} />
                <div className="min-w-0">
                  <p className="type-callout font-semibold text-label-1">{locale === "en" ? k.label.en : k.label.tr}</p>
                  <p className="type-footnote text-label-2">{locale === "en" ? k.description.en : k.description.tr}</p>
                </div>
              </div>
              {k.library_required ? <Alert tone="warning">{t("identity.libraryRequired")}</Alert> : null}
              {k.kind === "ldap" ? (
                <Link href="/settings?tab=ldap" className="inline-flex min-h-11 items-center self-start rounded-lg px-3 type-callout text-(--accent) underline sm:min-h-9">
                  {t("identity.gallery.ldap")}
                </Link>
              ) : single ? (
                <p className="type-footnote text-label-2">{t("identity.gallery.exists")}</p>
              ) : k.presets.length ? (
                <div className="flex flex-wrap gap-2">
                  {k.presets.map((pr) => (
                    <Button key={pr.key} size="sm" variant="outline" disabled={create.isPending} className="min-h-11 sm:min-h-9" onClick={() => pick(k.kind as ProviderKind, pr.key)} data-testid={`idp-preset-${k.kind}-${pr.key}`}>
                      {pr.key === "generic" ? t("identity.gallery.generic") : pr.label}
                    </Button>
                  ))}
                </div>
              ) : (
                <Button size="sm" disabled={create.isPending} className="min-h-11 self-start sm:min-h-9" onClick={() => pick(k.kind as ProviderKind)} data-testid={`idp-create-${k.kind}`}>
                  {t("identity.gallery.start")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
