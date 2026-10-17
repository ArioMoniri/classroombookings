"use client";
/**
 * Profil › Takvim aktarımı: the signed-in user's Google Calendar / Microsoft 365 push connections
 * (`GET /calendar/sync`, `POST /calendar/connectors/{p}/connect`, `GET …/calendars`, `PUT …/{p}`, `POST …/resync`,
 * `DELETE …/{p}`; backend `app/api/v1/calendar_sync.py`).
 *
 * - A provider the administrator has not configured shows a sentence, never a disabled or fake "Connect".
 * - Connect asks the backend for the provider's authorize URL (PKCE + state are made there) and sends the browser
 *   to it; the provider comes back through the backend callback to `/profile?calendar=connected|error&provider=…`,
 *   which this section reads once (toast, refresh) and removes from the address bar.
 * - With calendar sync off (the organisation's KVKK switch) the section says so and offers nothing.
 * - Consent gates (2026-10-16): while `GET /calendar/sync` `consent` is required and not granted, Connect opens the
 *   inline calendar-sync consent step (`privacy/calendar-consent.tsx`) and connects once it is given; a 409
 *   `consent_required` shows the backend's sentence with a link to its `grant_path`.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2, RefreshCw, Unplug } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, ConfirmDialog, Loading, SectionTitle, SelectField } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { CalendarConsentStep, ConsentRefusal, consentRefusal } from "@/components/privacy/calendar-consent";
import { crbs, type SyncConnector } from "@/lib/api/crbs";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";

export const SYNC_KEY = ["crbs", "calendar-sync"] as const;
/** where the provider's redirect lands (a panel path; `app/api/v1/calendar_sync.py` ConnectIn) */
export const RETURN_PATH = "/profile";
const REASONS = new Set(["denied", "state", "exchange", "disabled", "not_configured"]);

/** `?calendar=…&provider=…&reason=…` after the OAuth round trip, or null. */
export function connectResult(params: URLSearchParams): { ok: boolean; provider: string | null; reason: string | null } | null {
  const v = params.get("calendar");
  if (v !== "connected" && v !== "error") return null;
  return { ok: v === "connected", provider: params.get("provider"), reason: params.get("reason") };
}

function providerName(p: string, t: ReturnType<typeof useI18n>["t"], fallback: string): string {
  return p === "google" || p === "microsoft" ? t(`calendarPush.provider.${p}`) : fallback;
}

/** reads the redirect's query once; its own component so useSearchParams sits under a Suspense boundary */
function ConnectResult() {
  useConnectResult();
  return null;
}

function useConnectResult() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const done = useRef(false);
  useEffect(() => {
    const r = connectResult(new URLSearchParams(params.toString()));
    if (!r || done.current) return;
    done.current = true;
    const name = r.provider ? providerName(r.provider, t, r.provider) : "";
    if (r.ok) toast.success(t("calendarPush.me.connectedToast", { provider: name }));
    else toast.error(t("calendarPush.me.connectError", { reason: r.reason && REASONS.has(r.reason) ? t(`calendarPush.me.reason.${r.reason as "denied"}`) : (r.reason ?? "") }));
    void qc.invalidateQueries({ queryKey: SYNC_KEY });
    document.getElementById("calendar-push")?.scrollIntoView?.({ block: "start" });
    router.replace(path || RETURN_PATH, { scroll: false });
  }, [params, qc, t, router, path]);
}

function Connection({ c, needsConsent }: { c: SyncConnector; needsConsent: boolean }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<"connect" | "disconnect" | "resync" | "calendar" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ text: string; href: string } | null>(null);
  const [ask, setAsk] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const name = providerName(c.provider, t, c.label);
  const base = `cc-${c.provider}`;
  const reauth = c.status === "REAUTH";
  const calendars = useQuery({ queryKey: ["crbs", "calendar-calendars", c.provider], queryFn: () => crbs.calendar.calendars(c.provider), enabled: c.connected && !reauth, retry: false, staleTime: 60_000 });
  const fail = (e: unknown) => {
    const r = consentRefusal(e, locale);
    if (!r) return setError(errorText(wave1Error(e), locale));
    setRefusal(r);
    // the consent went missing meanwhile: refresh, so the next Connect asks for it first
    void qc.invalidateQueries({ queryKey: SYNC_KEY });
  };
  const run = async (what: NonNullable<typeof busy>, fn: () => Promise<unknown>) => {
    setBusy(what);
    setError(null);
    setRefusal(null);
    try {
      await fn();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };
  const connect = () =>
    run("connect", async () => {
      const { authorize_url } = await crbs.calendar.connect(c.provider, RETURN_PATH);
      window.location.assign(authorize_url);
    });
  const disconnect = () =>
    run("disconnect", async () => {
      await crbs.calendar.disconnect(c.provider);
      setConfirm(false);
      toast.success(t("calendarPush.me.disconnected", { provider: name }));
      await qc.invalidateQueries({ queryKey: SYNC_KEY });
    });
  const resync = () =>
    run("resync", async () => {
      const r = await crbs.calendar.resync(c.provider);
      toast.success(t("calendarPush.me.resyncQueued", { n: r.queued }));
      await qc.invalidateQueries({ queryKey: SYNC_KEY });
    });
  const choose = (id: string) => {
    const picked = calendars.data?.find((x) => x.id === id);
    void run("calendar", async () => {
      await crbs.calendar.chooseCalendar(c.provider, id, picked?.name ?? null);
      toast.success(t("calendarPush.me.calendarSaved", { name: picked?.name ?? id }));
      await qc.invalidateQueries({ queryKey: SYNC_KEY });
    });
  };
  const when = c.last_synced_at ? new Date(c.last_synced_at.endsWith("Z") ? c.last_synced_at : `${c.last_synced_at}Z`) : null;
  const synced = when && !Number.isNaN(when.getTime()) ? when.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" }) : null;

  return (
    <li className="grid gap-2 rounded-xl bg-fill-2 px-3 py-3" data-testid={`calendar-connection-${c.provider}`} data-state={!c.configured ? "not-configured" : c.connected ? (reauth ? "reauth" : "connected") : "disconnected"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="type-callout font-medium text-label-1">{name}</p>
          <p className="type-footnote text-label-2">
            {!c.configured
              ? t("calendarPush.me.notConfigured")
              : c.connected
                ? reauth
                  ? t("calendarPush.me.reauth")
                  : t("calendarPush.me.connectedAs", { account: c.account_email ?? name })
                : t("calendarPush.me.notConnected")}
          </p>
        </div>
        {c.configured ? (
          c.connected && !reauth ? (
            <Button className="pointer-coarse:h-11" variant="ghost" size="sm" onClick={() => setConfirm(true)} disabled={busy !== null} data-testid={`calendar-disconnect-${c.provider}`}>
              <Unplug aria-hidden />
              {t("calendarPush.me.disconnect")}
            </Button>
          ) : (
            <Button className="pointer-coarse:h-11" variant="outline" size="sm" onClick={() => (needsConsent ? setAsk(true) : void connect())} disabled={busy !== null || ask} aria-busy={busy === "connect" || undefined} data-testid={`calendar-connect-${c.provider}`}>
              <BusyLabel busy={busy === "connect"} label={t("calendarPush.me.redirecting")}>
                {reauth ? t("calendarPush.me.reconnect") : t("calendarPush.me.connect", { provider: name })}
              </BusyLabel>
            </Button>
          )
        ) : null}
      </div>
      {c.connected && !reauth ? (
        <div className="grid gap-2">
          <div className="grid gap-1.5">
            <Label htmlFor={`${base}-cal`}>{t("calendarPush.me.calendar")}</Label>
            {calendars.isLoading ? (
              <Loading label={t("calendarPush.me.loadingCalendars")} />
            ) : calendars.data?.length ? (
              <SelectField id={`${base}-cal`} value={c.calendar_id ?? ""} onChange={(e) => choose(e.target.value)} disabled={busy !== null} data-testid={`calendar-choose-${c.provider}`}>
                {c.calendar_id && !calendars.data.some((x) => x.id === c.calendar_id) ? <option value={c.calendar_id}>{c.calendar_name ?? c.calendar_id}</option> : null}
                {calendars.data.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name ?? x.id}
                    {x.primary ? ` (${t("calendarPush.me.primary")})` : ""}
                  </option>
                ))}
              </SelectField>
            ) : (
              <p className="type-footnote text-label-2">{c.calendar_name ?? t("calendarPush.me.defaultCalendar")}</p>
            )}
            {calendars.isError ? <p className="type-footnote text-status-warning-fg">{errorText(wave1Error(calendars.error), locale)}</p> : null}
          </div>
          <p className="type-footnote text-label-2" data-testid={`calendar-sync-state-${c.provider}`}>
            {synced ? t("calendarPush.me.lastSynced", { date: synced }) : t("calendarPush.me.never")}
            {c.pending_jobs ? ` · ${t("calendarPush.me.pending", { n: c.pending_jobs })}` : ""}
            {c.failed_jobs ? ` · ${t("calendarPush.me.failed", { n: c.failed_jobs })}` : ""}
          </p>
          {c.last_error ? <p className="type-footnote text-status-warning-fg">{c.last_error}</p> : null}
          <div>
            <Button className="pointer-coarse:h-11" variant="ghost" size="sm" onClick={() => void resync()} disabled={busy !== null} aria-busy={busy === "resync" || undefined}>
              <RefreshCw aria-hidden />
              <BusyLabel busy={busy === "resync"} label={t("busy.saving")}>{t("calendarPush.me.resync")}</BusyLabel>
            </Button>
          </div>
        </div>
      ) : null}
      {ask ? (
        <CalendarConsentStep
          testId={`calendar-consent-${c.provider}`}
          onGranted={() => {
            setAsk(false);
            void connect();
          }}
          onCancel={() => setAsk(false)}
        />
      ) : null}
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
      {refusal ? <ConsentRefusal refusal={refusal} /> : null}
      <ConfirmDialog
        open={confirm}
        onOpenChange={(o) => busy === null && setConfirm(o)}
        title={t("calendarPush.me.disconnectTitle", { provider: name })}
        description={t("calendarPush.me.disconnectBody")}
        confirmLabel={t("calendarPush.me.disconnect")}
        destructive
        busy={busy === "disconnect"}
        onConfirm={() => void disconnect()}
      />
    </li>
  );
}

export function CalendarConnectionsSection() {
  const { t, locale } = useI18n();
  const status = useQuery({ queryKey: SYNC_KEY, queryFn: crbs.calendar.sync, retry: false, staleTime: 30_000 });
  const s = status.data;
  const needsConsent = !!s?.consent?.required && !s.consent.granted;
  return (
    <section aria-labelledby="pf-calendar-push" id="calendar-push" className="scroll-mt-20" data-testid="calendar-connections">
      <Suspense fallback={null}>
        <ConnectResult />
      </Suspense>
      <SectionTitle id="pf-calendar-push">
        <span className="inline-flex items-center gap-2">
          <CalendarCheck2 className="size-4 text-label-3" aria-hidden />
          {t("calendarPush.me.title")}
        </span>
      </SectionTitle>
      <Card variant="glass" className="gap-3 px-4">
        <p className="type-callout text-label-2">{t("calendarPush.me.lead")}</p>
        {status.isLoading ? <Loading /> : null}
        {status.isError ? <Alert tone="error">{errorText(wave1Error(status.error), locale)}</Alert> : null}
        {/* round 2 sweeper 3: a quiet note, not a role=status live region: screen readers heard the Alert announced like a
            toast on every /profile visit (the state is the organisation's, nothing on this page changed it) */}
        {s && !s.enabled ? (
          <p data-testid="calendar-connections-off" className="type-callout text-label-2">
            {t("calendarPush.me.off")}
          </p>
        ) : null}
        {s?.enabled && needsConsent ? (
          <Alert tone="info" testId="calendar-connections-consent">
            {t("calendarPush.me.needsConsent")}{" "}
            <Link href="/profile#privacy" className="font-medium text-tint-text underline-offset-4 hover:underline">
              {t("calendarPush.me.consentLink")}
            </Link>
          </Alert>
        ) : null}
        {s?.enabled ? (
          <ul className="grid gap-2">
            {s.connectors.map((c) => (
              <Connection key={c.provider} c={c} needsConsent={needsConsent} />
            ))}
          </ul>
        ) : null}
      </Card>
    </section>
  );
}
