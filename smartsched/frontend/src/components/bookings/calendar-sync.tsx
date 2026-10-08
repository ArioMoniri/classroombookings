"use client";
/**
 * "Sync to calendar" (docs/product/calendar-sync-api.md): private subscription links for my bookings, a room
 * and a department (https + webcal, with copy buttons), "Add to Google Calendar" / "Add to Outlook" through
 * the providers' add-by-URL pages, Apple Calendar through webcal, and a reset of the private link. Two-way
 * push connectors appear only when an administrator configured them (`configured: true`); there is never a
 * disabled or fake "Connect" button.
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
import { bookingErrorMessage } from "./booking-errors";
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
  const { t } = useI18n();
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
  const fail = (e: unknown) => toast.error(bookingErrorMessage(crbsError(e), t));

  const s = status.data;
  const rooms = options.data?.rooms ?? [];
  const departments = options.data?.departments ?? [];
  const roomPick = room ?? roomId ?? rooms[0]?.id ?? null;
  const deptPick = dept ?? departmentId ?? me.data?.department_id ?? departments[0]?.id ?? null;
  const roomName = rooms.find((r) => r.id === roomPick)?.name ?? "";
  const deptName = departments.find((d) => d.id === deptPick)?.name ?? "";
  const configured = (s?.connectors ?? []).filter((c) => c.configured);

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
                  <SelectField aria-label={t("reserve.sync.pickRoom")} value={String(roomPick ?? "")} onChange={(e) => setRoom(Number(e.target.value))} data-testid="sync-room-select">
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
                  <SelectField aria-label={t("reserve.sync.pickDepartment")} value={String(deptPick ?? "")} onChange={(e) => setDept(Number(e.target.value))} data-testid="sync-dept-select">
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
              <Button variant="ghost" onClick={() => setConfirm(true)} disabled={reset.isPending} data-testid="sync-reset">
                <RefreshCw aria-hidden />
                {t("reserve.sync.reset")}
              </Button>
            </div>
          </>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="type-callout text-label-2">{s.feeds.tokens.length ? t("reserve.sync.existing", { n: s.feeds.tokens.length, hints: s.feeds.tokens.map((x) => x.hint).join(", ") }) : t("reserve.sync.none")}</p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => create.mutate(undefined, { onSuccess: onLink, onError: fail })} disabled={create.isPending} data-testid="sync-create">
                <Link2 aria-hidden />
                {t("reserve.sync.create")}
              </Button>
              {s.feeds.tokens.length ? (
                <Button variant="ghost" onClick={() => setConfirm(true)} disabled={reset.isPending} data-testid="sync-reset">
                  <RefreshCw aria-hidden />
                  {t("reserve.sync.reset")}
                </Button>
              ) : null}
            </div>
          </div>
        )
      ) : null}
      {s?.enabled && configured.length ? <Connectors connectors={configured} /> : null}
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
        <Input readOnly value={url} aria-label={`${title}: ${t("reserve.sync.https")}`} onFocus={(e) => e.currentTarget.select()} className="min-w-0 flex-1 font-mono text-[12px]" data-testid={`sync-url-${id}`} />
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

function Connectors({ connectors }: { connectors: { provider: string; label: string; connected: boolean; status?: string | null; account_email?: string | null }[] }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const path = usePathname();
  const [busy, setBusy] = useState<string | null>(null);
  const connect = async (provider: string) => {
    setBusy(provider);
    try {
      const { authorize_url } = await crbs.calendar.connect(provider, path || "/my-bookings");
      window.location.assign(authorize_url);
    } catch (e) {
      toast.error(t("reserve.sync.connectError", { message: bookingErrorMessage(crbsError(e), t) }));
      setBusy(null);
    }
  };
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
          <div key={c.provider} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-fill-2 px-3 py-2">
            <span className="type-callout text-label-1">{c.connected ? t("reserve.sync.connected", { account: c.account_email ?? c.label }) : c.label}</span>
            {c.connected && c.status !== "REAUTH" ? (
              <Button variant="ghost" size="sm" onClick={() => void disconnect(c.provider)} disabled={busy === c.provider}>
                <Unplug aria-hidden />
                {t("reserve.sync.disconnect")}
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={() => void connect(c.provider)} disabled={busy === c.provider} data-testid={`sync-connect-${c.provider}`}>
                {c.status === "REAUTH" ? t("reserve.sync.reconnect") : label}
              </Button>
            )}
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
