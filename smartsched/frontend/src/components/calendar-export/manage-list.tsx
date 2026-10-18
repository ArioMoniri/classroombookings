"use client";
/**
 * Profil › Takvim manage list (CAL-08, research doc §3.7): one row per subscription, "Derslerim · Google · Son
 * eşitleme 14:05", "Bölümümün dersleri · Bağlantı · Takviminiz en son 13:10'da çekti". Actions: "Şimdi eşitle" (push),
 * "Bağlantıyı yenile" (a new token, shown once), "Kaldır" (confirm; focus moves to the next row, never <body>).
 * Connected accounts carry "Daha az izinle yeniden bağlan" (an old broad Google grant), "Yeniden bağlan" (REAUTH)
 * and "Bağlantıyı kes" (deletes the SmartSched calendar, revokes the grant).
 */
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, RotateCw, ShieldCheck, Trash2, Unplug } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loading } from "@/components/admin/kit";
import { calendarExportApi, calendarExportKeys, useExportOptions, useRefreshCalendar, useSubscriptions, type PushChannel, type Subscription, type SubscriptionCreated, type ScopeKind, type SubscriptionsOut } from "@/lib/api/calendar-export";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { RETURN_PATH, legacyProviders, manageRows, nextFocus, pushAccounts, pushScope, relativeWhen } from "./model";
import { Advanced, LinkResult, backendText, providerName, scopeName } from "./steps";

type T = ReturnType<typeof useI18n>["t"];

function rowTitle(r: Subscription, t: T, locale: string): string {
  // the backend names the scope itself ("Psikoloji bölümünün dersleri"); the sheet's words otherwise
  const own = locale === "tr" ? r.scope_label : (r.scope_label_en ?? null);
  if (own && r.scope_kind === "department_classes") return own;
  return scopeName(r.scope_kind, t, r.scope_kind === "department_classes" ? r.scope_label : null);
}

export function rowState(r: Subscription, t: T, locale: string, now?: Date): string {
  const words = { today: t("calendarExport.manage.today"), yesterday: t("calendarExport.manage.yesterday") };
  if (r.channel === "push") {
    const w = relativeWhen(r.last_synced_at, locale, words, now);
    const parts = [providerName(r.provider ?? "", t), w ? t("calendarExport.manage.pushSynced", { when: w.label }) : t("calendarExport.manage.pushNever")];
    if (r.pending_jobs) parts.push(t("calendarExport.manage.pending", { n: r.pending_jobs }));
    if (r.failed_jobs) parts.push(t("calendarExport.manage.failedJobs", { n: r.failed_jobs }));
    return parts.join(" · ");
  }
  const w = relativeWhen(r.last_used_at, locale, words, now);
  return [t("calendarExport.manage.channelLink"), w ? t("calendarExport.manage.linkPulled", { at: w.at }) : t("calendarExport.manage.linkNever")].join(" · ");
}

export function CalendarExportManage({ fallbackFocus }: { fallbackFocus: RefObject<HTMLElement | null> }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const subs = useSubscriptions();
  const options = useExportOptions();
  const refresh = useRefreshCalendar();
  const rows = manageRows(subs.data?.rows);
  const legacy = legacyProviders(options.data, subs.data?.rows, subs.data?.connections);
  const accounts = pushAccounts(options.data, subs.data?.connections).filter((p) => p.connected || p.status === "REAUTH" || p.status === "CAL_DELETED");
  const [confirm, setConfirm] = useState<Subscription | null>(null);
  // CAL10-F05 (fix-h-2026-10-18): "Bağlantıyı yenile" breaks every calendar subscribed to the old link; it asks first
  const [confirmRotate, setConfirmRotate] = useState<Subscription | null>(null);
  const rotateTrigger = useRef<HTMLElement | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rotated, setRotated] = useState<{ id: Subscription["id"]; made: SubscriptionCreated } | null>(null);
  const [focusAfter, setFocusAfter] = useState<Subscription["id"] | "fallback" | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // after a removal: the next row's first action, else the "Takvimime ekle" button (never <body>)
  useEffect(() => {
    if (focusAfter === null) return;
    const id = window.requestAnimationFrame(() => {
      const el = focusAfter === "fallback" ? null : listRef.current?.querySelector<HTMLElement>(`[data-row-id="${String(focusAfter)}"] [data-row-action]`);
      (el ?? fallbackFocus.current)?.focus();
      setFocusAfter(null);
    });
    return () => window.cancelAnimationFrame(id);
  }, [focusAfter, fallbackFocus, rows.length]);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(t("calendarExport.failed", { message: backendText(e, locale) }));
    } finally {
      setBusy(null);
    }
  };

  const remove = (r: Subscription) =>
    run(`remove-${r.id}`, async () => {
      const next = nextFocus(rows, r.id);
      if (r.channel === "push") {
        // a push scope lives on the connection: put the account's scopes back without this one
        const acc = accounts.find((a) => a.provider === r.provider);
        const gone = pushScope(r.scope_kind as ScopeKind, r.scope_id ?? null);
        await calendarExportApi.pushScopes(r.provider ?? "", (acc?.scopes ?? []).filter((x) => x !== gone && x !== r.scope_kind + (r.scope_id ? `:${r.scope_id}` : "")));
      } else {
        await calendarExportApi.remove(r.id);
      }
      qc.setQueryData<SubscriptionsOut>(calendarExportKeys.subscriptions, (old) => (old ? { ...old, rows: old.rows.filter((x) => x.id !== r.id) } : old));
      setConfirm(null);
      setFocusAfter(next ?? "fallback");
      toast.success(t("calendarExport.manage.removed"));
      void refresh();
    });
  const rotate = (r: Subscription) =>
    run(`rotate-${r.id}`, async () => {
      const made = await calendarExportApi.rotate(r);
      setConfirmRotate(null);
      setRotated({ id: made.id, made });
      toast.success(t("calendarExport.manage.rotated"));
      await qc.invalidateQueries({ queryKey: calendarExportKeys.subscriptions });
    });
  const resync = (r: Subscription) =>
    run(`sync-${r.id}`, async () => {
      await calendarExportApi.resync(r.provider ?? "");
      toast.success(t("calendarExport.manage.syncQueued"));
      await qc.invalidateQueries({ queryKey: calendarExportKeys.subscriptions });
    });
  const reconnect = (p: PushChannel) =>
    run(`reconnect-${p.provider}`, async () => {
      const { authorize_url } = await calendarExportApi.connect(p.provider, RETURN_PATH, p.scopes);
      window.location.assign(authorize_url);
    });

  if (subs.isLoading) return <Loading />;
  return (
    <div className="grid gap-3" data-testid="cal-manage">
      {subs.isError ? <Alert tone="error">{errorText(wave1Error(subs.error), locale)}</Alert> : null}
      {accounts.map((p) => (
        <Account key={p.provider} p={p} legacy={legacy.has(p.provider)} busy={busy} onReconnect={() => void reconnect(p)} onDisconnected={() => void refresh()} />
      ))}
      {subs.isSuccess && !rows.length ? (
        <p className="type-callout text-label-2" data-testid="cal-manage-empty">
          {t("calendarExport.manage.empty")}
        </p>
      ) : null}
      {rows.length ? (
        <ul ref={listRef} className="grid gap-2" aria-label={t("calendarExport.manage.title")} data-testid="cal-manage-rows">
          {rows.map((r) => (
            <li key={String(r.id)} data-row-id={String(r.id)} className="grid gap-2 rounded-xl bg-fill-2 px-3 py-3" data-testid={`cal-row-${r.id}`} data-channel={r.channel}>
              <div className="min-w-0">
                <p className="type-callout font-medium text-label-1">{rowTitle(r, t, locale)}</p>
                <p className="type-footnote text-label-2" data-testid={`cal-row-state-${r.id}`}>
                  {rowState(r, t, locale)}
                </p>
                {r.last_error ? <p className="type-footnote text-status-warning-fg">{r.last_error}</p> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" className="pointer-coarse:min-h-11" data-row-action="" onClick={() => setConfirm(r)} disabled={busy !== null} data-testid={`cal-remove-${r.id}`}>
                  <Trash2 aria-hidden />
                  {t("calendarExport.manage.remove")}
                </Button>
              </div>
              {/* the simplicity principle: syncing by hand and renewing a link are for the few who need them */}
              <Advanced testId={`cal-row-advanced-${r.id}`} className="bg-fill-3">
                <div className="flex flex-wrap gap-2">
                  {r.channel === "push" ? (
                    <Button variant="outline" size="sm" className="pointer-coarse:min-h-11" onClick={() => void resync(r)} disabled={busy !== null} aria-busy={busy === `sync-${r.id}` || undefined} data-testid={`cal-sync-${r.id}`}>
                      <RefreshCw aria-hidden />
                      <BusyLabel busy={busy === `sync-${r.id}`} label={t("busy.working")}>
                        {t("calendarExport.manage.syncNow")}
                      </BusyLabel>
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" className="pointer-coarse:min-h-11" onClick={(e) => {
                        rotateTrigger.current = e.currentTarget;
                        setConfirmRotate(r);
                      }} disabled={busy !== null} aria-busy={busy === `rotate-${r.id}` || undefined} data-testid={`cal-rotate-${r.id}`}>
                      <RotateCw aria-hidden />
                      <BusyLabel busy={busy === `rotate-${r.id}`} label={t("busy.working")}>
                        {t("calendarExport.manage.rotate")}
                      </BusyLabel>
                    </Button>
                  )}
                </div>
              </Advanced>
              {rotated && String(rotated.id) === String(r.id) ? <LinkResult urls={rotated.made.urls} name={rowTitle(r, t, locale)} testId={`cal-rotated-${r.id}`} /> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="cal-manage-error">
          {error}
        </p>
      ) : null}
      <Dialog open={confirm !== null} onOpenChange={(o) => !o && busy === null && setConfirm(null)}>
        {/* finalFocus off: a removed row's button is gone, the effect above moves focus to the next row */}
        <DialogContent role="alertdialog" className="sm:max-w-md" finalFocus={false} data-testid="cal-remove-dialog">
          <DialogHeader>
            <DialogTitle>{confirm ? t("calendarExport.manage.removeTitle", { scope: rowTitle(confirm, t, locale) }) : ""}</DialogTitle>
            <DialogDescription>{t("calendarExport.manage.removeBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirm(null)} disabled={busy !== null}>
              {t("crbs.common.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => confirm && void remove(confirm)} disabled={busy !== null} aria-busy={busy?.startsWith("remove-") || undefined} data-testid="cal-remove-confirm">
              <BusyLabel busy={!!busy?.startsWith("remove-")} label={t("busy.deleting")}>
                {t("calendarExport.manage.remove")}
              </BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={confirmRotate !== null} onOpenChange={(o) => !o && busy === null && setConfirmRotate(null)}>
        <DialogContent role="alertdialog" className="sm:max-w-md" finalFocus={() => rotateTrigger.current ?? true} data-testid="cal-rotate-dialog">
          <DialogHeader>
            <DialogTitle>{confirmRotate ? t("calendarExport.manage.rotateTitle", { scope: rowTitle(confirmRotate, t, locale) }) : ""}</DialogTitle>
            <DialogDescription>{t("calendarExport.manage.rotateBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmRotate(null)} disabled={busy !== null}>
              {t("crbs.common.cancel")}
            </Button>
            <Button onClick={() => confirmRotate && void rotate(confirmRotate)} disabled={busy !== null} aria-busy={busy?.startsWith("rotate-") || undefined} data-testid="cal-rotate-confirm">
              <BusyLabel busy={!!busy?.startsWith("rotate-")} label={t("busy.working")}>
                {t("calendarExport.manage.rotate")}
              </BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Account({ p, legacy, busy, onReconnect, onDisconnected }: { p: PushChannel; legacy: boolean; busy: string | null; onReconnect: () => void; onDisconnected: () => void }) {
  const { t, locale } = useI18n();
  const [asking, setAsking] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const name = providerName(p.provider, t);
  // REAUTH: the grant expired; CAL_DELETED: the person deleted the SmartSched calendar twice (API.md); both reconnect
  const reauth = p.status === "REAUTH" || p.status === "CAL_DELETED";
  const disconnect = async () => {
    setWorking(true);
    setError(null);
    try {
      await calendarExportApi.disconnect(p.provider);
      setAsking(false);
      toast.success(t("calendarExport.manage.disconnected", { provider: name }));
      onDisconnected();
    } catch (e) {
      setError(t("calendarExport.failed", { message: backendText(e, locale) }));
    } finally {
      setWorking(false);
    }
  };
  return (
    <section className="grid gap-2 rounded-xl bg-fill-3 px-3 py-3" aria-label={name} data-testid={`cal-account-${p.provider}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 type-callout font-medium text-label-1">{p.account_email ? t("calendarExport.manage.account", { provider: name, account: p.account_email }) : name}</p>
        {!reauth && p.account_verified && p.account_verified !== "none" ? (
          <span className="inline-flex items-center gap-1 type-footnote text-status-feasible-fg">
            <ShieldCheck className="size-3.5" aria-hidden />
            {t("calendarExport.manage.verified")}
          </span>
        ) : null}
      </div>
      {reauth ? <p className="type-footnote text-status-warning-fg">{p.status === "CAL_DELETED" ? t("calendarExport.manage.calDeleted") : t("calendarExport.manage.reauth")}</p> : null}
      {p.status === "ERROR" ? <p className="type-footnote text-status-warning-fg">{t("calendarExport.manage.error")}</p> : null}
      {reauth ? (
        <div>
          <Button variant="outline" size="sm" className="pointer-coarse:min-h-11" onClick={onReconnect} disabled={busy !== null} aria-busy={busy === `reconnect-${p.provider}` || undefined} data-testid={`cal-reconnect-${p.provider}`}>
            <BusyLabel busy={busy === `reconnect-${p.provider}`} label={t("calendarPush.me.redirecting")}>
              {p.status === "CAL_DELETED" ? t("calendarExport.manage.renewConnection") : t("calendarExport.manage.reconnect")}
            </BusyLabel>
          </Button>
        </div>
      ) : null}
      <Advanced testId={`cal-account-advanced-${p.provider}`} className="bg-fill-2">
        {legacy && !reauth ? <p className="type-footnote text-label-2">{t("calendarExport.manage.reconnectLessHint")}</p> : null}
        <div className="flex flex-wrap gap-2">
          {legacy && !reauth ? (
            <Button variant="outline" size="sm" className="pointer-coarse:min-h-11" onClick={onReconnect} disabled={busy !== null} aria-busy={busy === `reconnect-${p.provider}` || undefined} data-testid={`cal-reconnect-${p.provider}`}>
              <BusyLabel busy={busy === `reconnect-${p.provider}`} label={t("calendarPush.me.redirecting")}>
                {t("calendarExport.manage.reconnectLess")}
              </BusyLabel>
            </Button>
          ) : null}
          <Button ref={triggerRef} variant="ghost" size="sm" className="pointer-coarse:min-h-11" onClick={() => setAsking(true)} disabled={busy !== null || working} data-testid={`cal-disconnect-${p.provider}`}>
            <Unplug aria-hidden />
            {t("calendarExport.manage.disconnect")}
          </Button>
        </div>
      </Advanced>
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
      <Dialog open={asking} onOpenChange={(o) => !working && setAsking(o)}>
        <DialogContent role="alertdialog" className="sm:max-w-md" data-testid={`cal-disconnect-dialog-${p.provider}`}>
          <DialogHeader>
            <DialogTitle>{t("calendarExport.manage.disconnectTitle", { provider: name })}</DialogTitle>
            <DialogDescription>{t("calendarExport.manage.disconnectBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAsking(false)} disabled={working}>
              {t("crbs.common.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => void disconnect()} disabled={working} aria-busy={working || undefined} data-testid={`cal-disconnect-confirm-${p.provider}`}>
              <BusyLabel busy={working} label={t("busy.working")}>
                {t("calendarExport.manage.disconnect")}
              </BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
