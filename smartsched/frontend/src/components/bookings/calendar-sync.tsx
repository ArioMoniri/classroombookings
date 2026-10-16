"use client";
import { focusAfter } from "./focus-after";
/**
 * "Sync to calendar" (docs/product/calendar-sync-api.md): private subscription links for my bookings, a room
 * and a department (https + webcal, with copy buttons), "Add to Google Calendar" / "Add to Outlook" through
 * the providers' add-by-URL pages, Apple Calendar through webcal, and a reset of the private link. Two-way
 * push connectors appear only when an administrator configured them (`configured: true`); there is never a
 * disabled or fake "Connect" button.
 *
 * Consent gates (2026-10-16): with the calendar-sync sign-off on, `GET /calendar/sync` `consent` says whether the
 * person's `calendar_sync` consent is still missing; "Create link", "Reset" and "Connect" then open the inline consent
 * step first (`privacy/calendar-consent.tsx`) and continue once it is given. A 409 `consent_required` that arrives
 * anyway shows the backend's sentence with a link to `grant_path` (Profil › Gizlilik).
 *
 * The server keeps only a hash of a link's token and shows it once, when the link is made. The panel keeps
 * that token for the browser tab (sessionStorage, per user), so /bookings and /my-bookings show the same
 * links; after the tab is closed the user makes a new link (or resets them all).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CalendarSync as CalendarSyncIcon, Copy, ExternalLink, Link2, RefreshCw, Unplug } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMe, useCrbsMutation, type FeedTokenCreated } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, ConfirmDialog, Loading, SelectField } from "@/components/admin/kit";
import { CalendarConsentStep, ConsentRefusal, consentRefusal, needsCalendarConsent } from "@/components/privacy/calendar-consent";
import { bookingErrorMessage } from "./booking-errors";
import { useBookingFormat } from "./use-booking-format";
import { googleSubscribeUrl, outlookSubscribeUrl, webcalUrl } from "./reserve-model";

const SYNC_KEY = ["crbs", "calendar-sync"] as const;
const storeKey = (uid: number) => `smartsched.calendar-link.${uid}`;
const listeners = new Set<() => void>();

function readLink(uid: number | undefined): string | null {
  if (!uid || typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(storeKey(uid));
  } catch {
    return null;
  }
}

function writeLink(uid: number, link: Pick<FeedTokenCreated, "urls" | "hint"> | null) {
  try {
    if (link) window.sessionStorage.setItem(storeKey(uid), JSON.stringify({ urls: link.urls, hint: link.hint }));
    else window.sessionStorage.removeItem(storeKey(uid));
  } catch {
    /* storage blocked: the links live until the next render only */
  }
  for (const l of listeners) l();
}

function useStoredLink(uid: number | undefined): Pick<FeedTokenCreated, "urls" | "hint"> | null {
  const raw = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => void listeners.delete(cb);
    },
    () => readLink(uid),
    () => null,
  );
  return useMemo(() => {
    if (!raw) return null;
    try {
      return JSON.parse(raw) as Pick<FeedTokenCreated, "urls" | "hint">;
    } catch {
      return null;
    }
  }, [raw]);
}

function absolute(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  return typeof window !== "undefined" ? `${window.location.origin}${url}` : url;
}

export function CalendarSyncPanel({ roomId, departmentId }: { roomId?: number | null; departmentId?: number | null }) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const qc = useQueryClient();
  const me = useCrbsMe();
  const uid = me.data?.id;
  const status = useQuery({ queryKey: SYNC_KEY, queryFn: crbs.calendar.sync, retry: false, staleTime: 30_000 });
  const options = useQuery({ queryKey: ["crbs", "calendar-options"], queryFn: crbs.calendar.options, retry: false, staleTime: 5 * 60_000 });
  const link = useStoredLink(uid);
  const [confirm, setConfirm] = useState(false);
  const [room, setRoom] = useState<number | null>(roomId ?? null);
  const [dept, setDept] = useState<number | null>(departmentId ?? me.data?.department_id ?? null);
  useConnectResult();

  const onLink = (made: FeedTokenCreated) => {
    if (uid) writeLink(uid, made);
    void qc.invalidateQueries({ queryKey: SYNC_KEY });
  };
  const create = useCrbsMutation(() => crbs.calendar.createToken("SmartSched"));
  const reset = useCrbsMutation(() => crbs.calendar.reset());
  const [ask, setAsk] = useState<"create" | "reset" | null>(null);
  const [refusal, setRefusal] = useState<{ text: string; href: string } | null>(null);
  const fail = (e: unknown) => {
    const r = consentRefusal(e, locale);
    if (!r) return void toast.error(bookingErrorMessage(crbsError(e), t));
    // the consent went missing meanwhile (withdrawn in another tab, the sign-off switched on): say so where the
    // person is, and refresh the state so the next try asks for it first
    setRefusal(r);
    setConfirm(false);
    void qc.invalidateQueries({ queryKey: SYNC_KEY });
  };

  const s = status.data;
  const rooms = options.data?.rooms ?? [];
  const departments = options.data?.departments ?? [];
  // T-R1-17 (R1-A-20, U-23): no invented default (the alphabetically first department, the first room): the caller's
  // own department when the account has one, else "Bölüm seçin" / "Oda seçin" and no link until one is picked
  const roomPick = room ?? roomId ?? null;
  const deptPick = dept ?? departmentId ?? me.data?.department_id ?? null;
  const roomName = rooms.find((r) => r.id === roomPick)?.name ?? "";
  const deptName = departments.find((d) => d.id === deptPick)?.name ?? "";
  const configured = (s?.connectors ?? []).filter((c) => c.configured);
  const needsConsent = needsCalendarConsent(s);
  const doCreate = () => {
    setRefusal(null);
    create.mutate(undefined, { onSuccess: onLink, onError: fail });
  };
  const startCreate = () => (needsConsent ? setAsk("create") : doCreate());
  const startReset = () => {
    setRefusal(null);
    if (needsConsent) setAsk("reset");
    else setConfirm(true);
  };

  return (
    <div className="flex flex-col gap-4" data-testid="calendar-sync">
      <p className="type-callout text-label-2">{t("reserve.sync.lead")}</p>
      {status.isLoading ? <Loading label={t("reserve.sync.loading")} /> : null}
      {status.isError ? <Alert tone="error">{bookingErrorMessage(crbsError(status.error), t)}</Alert> : null}
      {s && !s.enabled ? <Alert tone="warning">{t("reserve.sync.disabled")}</Alert> : null}
      {s?.enabled ? (
        link ? (
          <>
            <FeedRow id="mine" title={t("reserve.sync.mine")} url={absolute(link.urls.mine)} name={t("reserve.sync.mine")} />
            {rooms.length ? (
              <FeedRow
                id="room"
                title={t("reserve.sync.room", { name: roomName })}
                url={roomPick ? absolute(link.urls.room.replace("{id}", String(roomPick))) : ""}
                name={roomName}
                picker={
                  <SelectField aria-label={t("reserve.sync.pickRoom")} value={String(roomPick ?? "")} onChange={(e) => setRoom(e.target.value ? Number(e.target.value) : null)} data-testid="sync-room-select">
                    {roomPick === null ? <option value="">{t("reserve.sync.choose")}</option> : null}
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </SelectField>
                }
              />
            ) : null}
            {departments.length ? (
              <FeedRow
                id="department"
                title={t("reserve.sync.department", { name: deptName })}
                url={deptPick ? absolute(link.urls.department.replace("{id}", String(deptPick))) : ""}
                name={deptName}
                picker={
                  <SelectField aria-label={t("reserve.sync.pickDepartment")} value={String(deptPick ?? "")} onChange={(e) => setDept(e.target.value ? Number(e.target.value) : null)} data-testid="sync-dept-select">
                    {deptPick === null ? <option value="">{t("reserve.sync.chooseDepartment")}</option> : null}
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </SelectField>
                }
              />
            ) : null}
            <p className="type-footnote text-label-3">
              {t("reserve.sync.private")} {t("reserve.sync.googleNote")}
            </p>
            <div>
              <Button variant="ghost" onClick={startReset} disabled={reset.isPending || ask !== null} data-testid="sync-reset">
                <RefreshCw aria-hidden />
                {t("reserve.sync.reset")}
              </Button>
            </div>
          </>
        ) : (
          <div className="flex flex-col gap-2">
            {/* T-R1-17 (R1-A-21): with a link in place (made on another device) the only action is a reset, which
                revokes the old link; a second set is never added. Each link is described by its dates, not "154Y". */}
            <p className="type-callout text-label-2" data-testid="sync-existing">
              {s.feeds.tokens.length
                ? t("reserve.sync.existingDated", {
                    n: s.feeds.tokens.length,
                    dates: s.feeds.tokens.map((x) => (x.created_at ? t("reserve.sync.madeOn", { date: fmt.short(x.created_at.slice(0, 10)) }) : x.hint)).join(", "),
                  })
                : t("reserve.sync.none")}
            </p>
            <div className="flex flex-wrap gap-2">
              {s.feeds.tokens.length ? (
                <Button onClick={startReset} disabled={reset.isPending || ask !== null} aria-expanded={needsConsent ? ask === "reset" : undefined} data-testid="sync-reset">
                  <RefreshCw aria-hidden />
                  {t("reserve.sync.reset")}
                </Button>
              ) : (
                <Button onClick={startCreate} disabled={create.isPending || ask !== null} aria-expanded={needsConsent ? ask === "create" : undefined} data-testid="sync-create">
                  <Link2 aria-hidden />
                  {t("reserve.sync.create")}
                </Button>
              )}
            </div>
          </div>
        )
      ) : null}
      {s?.enabled && ask ? (
        <CalendarConsentStep
          onGranted={() => {
            const next = ask;
            setAsk(null);
            if (next === "create") doCreate();
            else setConfirm(true);
          }}
          onCancel={() => setAsk(null)}
        />
      ) : null}
      {refusal ? <ConsentRefusal refusal={refusal} /> : null}
      {s?.enabled && configured.length ? <Connectors connectors={configured} needsConsent={needsConsent} /> : null}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t("reserve.sync.resetTitle")}
        description={t("reserve.sync.resetBody")}
        confirmLabel={t("reserve.sync.reset")}
        busy={reset.isPending}
        onConfirm={() =>
          reset.mutate(undefined, {
            onSuccess: (made) => {
              onLink(made);
              setConfirm(false);
              // say what happened and put focus on the new link (persona U-22)
              toast.success(t("wave1.sync.resetDone"));
              focusAfter(['[data-testid^="sync-url"]']);
            },
            onError: fail,
          })
        }
      />
    </div>
  );
}

function FeedRow({ id, title, url, name, picker }: { id: string; title: string; url: string; name: string; picker?: React.ReactNode }) {
  const { t } = useI18n();
  const copy = (text: string) => void navigator.clipboard?.writeText(text).then(() => toast.success(t("reserve.sync.copied")));
  const webcal = url ? webcalUrl(url) : "";
  const label = `SmartSched – ${name}`;
  return (
    <section className="flex flex-col gap-2 rounded-xl bg-fill-2 p-3" aria-label={title} data-testid={`sync-feed-${id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 type-subheadline font-medium text-label-1">
          <CalendarSyncIcon className="size-4 text-label-2" aria-hidden />
          {title}
        </h3>
        {picker ? <div className="min-w-40">{picker}</div> : null}
      </div>
      <div className="flex gap-2">
        <Input readOnly value={url} aria-label={`${title}: ${t("reserve.sync.https")}`} onFocus={(e) => e.currentTarget.select()} className="min-w-0 flex-1 font-mono type-footnote" data-testid={`sync-url-${id}`} />
        <Button variant="outline" size="icon" aria-label={t("reserve.sync.copy", { what: t("reserve.sync.https") })} onClick={() => copy(url)} disabled={!url} data-testid={`sync-copy-${id}`}>
          <Copy />
        </Button>
        <Button variant="outline" size="icon" aria-label={t("reserve.sync.copy", { what: t("reserve.sync.webcal") })} onClick={() => copy(webcal)} disabled={!url} data-testid={`sync-copy-webcal-${id}`}>
          <CalendarPlus />
        </Button>
      </div>
      {url ? (
        <div className="flex flex-wrap gap-1.5">
          <Button variant="secondary" size="sm" className="min-h-11 sm:min-h-0" nativeButton={false} render={<a href={googleSubscribeUrl(url)} target="_blank" rel="noopener noreferrer" data-testid={`sync-google-${id}`} />}>
            <ExternalLink aria-hidden />
            {t("reserve.sync.google")}
          </Button>
          <Button variant="secondary" size="sm" className="min-h-11 sm:min-h-0" nativeButton={false} render={<a href={outlookSubscribeUrl(url, label, true)} target="_blank" rel="noopener noreferrer" data-testid={`sync-outlook-${id}`} />}>
            <ExternalLink aria-hidden />
            {t("reserve.sync.outlook")}
          </Button>
          <Button variant="secondary" size="sm" className="min-h-11 sm:min-h-0" nativeButton={false} render={<a href={webcal} data-testid={`sync-apple-${id}`} />}>
            <CalendarPlus aria-hidden />
            {t("reserve.sync.apple")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function Connectors({ connectors, needsConsent }: { connectors: { provider: string; label: string; connected: boolean; status?: string | null; account_email?: string | null }[]; needsConsent: boolean }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const path = usePathname();
  const [busy, setBusy] = useState<string | null>(null);
  const [ask, setAsk] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ provider: string; text: string; href: string } | null>(null);
  const connect = async (provider: string) => {
    setBusy(provider);
    setRefusal(null);
    try {
      const { authorize_url } = await crbs.calendar.connect(provider, path || "/my-bookings");
      window.location.assign(authorize_url);
    } catch (e) {
      const r = consentRefusal(e, locale);
      if (r) {
        setRefusal({ provider, ...r });
        void qc.invalidateQueries({ queryKey: SYNC_KEY });
      } else toast.error(t("reserve.sync.connectError", { message: bookingErrorMessage(crbsError(e), t) }));
      setBusy(null);
    }
  };
  const startConnect = (provider: string) => (needsConsent ? setAsk(provider) : void connect(provider));
  const disconnect = async (provider: string) => {
    setBusy(provider);
    try {
      await crbs.calendar.disconnect(provider);
      await qc.invalidateQueries({ queryKey: SYNC_KEY });
    } catch (e) {
      toast.error(bookingErrorMessage(crbsError(e), t));
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="flex flex-col gap-2" aria-label={t("reserve.sync.connectLead")} data-testid="sync-connectors">
      <p className="type-footnote text-label-2">{t("reserve.sync.connectLead")}</p>
      {connectors.map((c) => {
        const label = c.provider === "google" ? t("reserve.sync.connectGoogle") : c.provider === "microsoft" ? t("reserve.sync.connectMicrosoft") : c.label;
        return (
          <div key={c.provider} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-fill-2 px-3 py-2">
              <span className="type-callout text-label-1">{c.connected ? t("reserve.sync.connected", { account: c.account_email ?? c.label }) : c.label}</span>
              {c.connected && c.status !== "REAUTH" ? (
                <Button variant="ghost" size="sm" onClick={() => void disconnect(c.provider)} disabled={busy === c.provider}>
                  <Unplug aria-hidden />
                  {t("reserve.sync.disconnect")}
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => startConnect(c.provider)} disabled={busy === c.provider || ask === c.provider} data-testid={`sync-connect-${c.provider}`}>
                  {c.status === "REAUTH" ? t("reserve.sync.reconnect") : label}
                </Button>
              )}
            </div>
            {ask === c.provider ? (
              <CalendarConsentStep
                testId={`sync-consent-${c.provider}`}
                onGranted={() => {
                  setAsk(null);
                  void connect(c.provider);
                }}
                onCancel={() => setAsk(null)}
              />
            ) : null}
            {refusal?.provider === c.provider ? <ConsentRefusal refusal={refusal} /> : null}
          </div>
        );
      })}
    </section>
  );
}

/** After the OAuth round trip the backend redirects with `?calendar=connected|error&provider=…`. */
function useConnectResult() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const params = useSearchParams();
  const done = useRef(false);
  const result = params.get("calendar");
  useEffect(() => {
    if (!result || done.current) return;
    done.current = true;
    if (result === "connected") toast.success(t("reserve.sync.connectedToast"));
    else toast.error(t("reserve.sync.connectError", { message: params.get("reason") ?? "" }));
    void qc.invalidateQueries({ queryKey: SYNC_KEY });
  }, [params, qc, result, t]);
}
