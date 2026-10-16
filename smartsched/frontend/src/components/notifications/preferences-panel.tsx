"use client";
/**
 * Profile › Bildirimler (F-01 S11): which event reaches the user on which channel, `GET/PUT
 * /me/notification-preferences` (backend `app/services/notify_dispatch.py`).
 *
 * - Channels: only the channels that can reach the user get a row with the master switch. The ones that cannot are
 *   summed up in one line ("Telegram, SMS: bağlı değil — Profil › Bağlı kanallar", linking to the profile's
 *   linked-channels section; e-mail without an address on the account says so), never repeated per event
 *   (identity agent's 390 px pass: the old matrix was ~6,000 px tall on a phone).
 * - Events are grouped (Onaylar, Rezervasyonlar, Program) in collapsible sections, each with an "all on / off"
 *   switch for the group. Inside a group: a matrix of events × reachable channels (rows ≥ 44 px); on a phone with
 *   more than three reachable channels, one card per event instead (MOBILE.md M-02 / M-07). A channel the user
 *   switched off stays as a column, disabled, with "Kanal kapalı".
 * - Each switch saves at once (a partial PUT) and confirms with a toast; a failure puts the switch back and says so.
 *
 * Exported for the profile screen (the identity frontend mounts it): `<NotificationPreferencesPanel />`.
 */
import { BellRing, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { useNotificationPrefs, useSaveNotificationPrefs, type ChannelPref, type EventPref, type NotificationPrefsIn } from "@/lib/api/approval-first";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { pairLang, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

type Pending = Record<string, boolean>;
const chanKey = (c: string) => `c:${c}`;
const cellKey = (e: string, c: string) => `e:${e}:${c}`;

export type EventGroup = "approvals" | "bookings" | "timetable" | "other";
const GROUP_ORDER: EventGroup[] = ["approvals", "bookings", "timetable", "other"];
const GROUP_KEY: Record<EventGroup, MessageKey> = {
  approvals: "notifications.prefs.groups.approvals",
  bookings: "notifications.prefs.groups.bookings",
  timetable: "notifications.prefs.groups.timetable",
  other: "notifications.prefs.groups.other",
};

/** The section an event belongs to, from its backend name (`approval.*`, `booking.*`, `room_owner.*`,
 *  `timetable.*`, and `preference.*`: an academician's timetable wish accepted or rejected). */
export function eventGroup(event: string): EventGroup {
  if (event.startsWith("approval.")) return "approvals";
  if (event.startsWith("booking.") || event.startsWith("room_owner.")) return "bookings";
  if (event.startsWith("timetable.") || event.startsWith("preference.")) return "timetable";
  return "other";
}

/** Events per section, in the backend's order inside a section; empty sections are left out. */
export function groupEvents<T extends { event: string }>(events: readonly T[]): { group: EventGroup; events: T[] }[] {
  return GROUP_ORDER.map((group) => ({ group, events: events.filter((e) => eventGroup(e.event) === group) })).filter((g) => g.events.length > 0);
}

export function NotificationPreferencesPanel({ className }: { className?: string }) {
  const { t, locale } = useI18n();
  const q = useNotificationPrefs();
  const save = useSaveNotificationPrefs();
  const phone = useIsPhone();
  // the switch shows the new value while the PUT runs; the answer (or the old value on failure) replaces it
  const [pending, setPending] = useState<Pending>({});
  const lang = pairLang(locale);
  const data = q.data;

  const put = (keys: string[], on: boolean, body: NotificationPrefsIn) => {
    setPending((p) => ({ ...p, ...Object.fromEntries(keys.map((k) => [k, on])) }));
    save.mutate(body, {
      onSuccess: () => toast.success(t("notifications.prefs.saved")),
      onError: (e) => toast.error(errorText(wave1Error(e), locale) || t("notifications.prefs.failed")),
      onSettled: () =>
        setPending((p) => {
          const next = { ...p };
          for (const k of keys) delete next[k];
          return next;
        }),
    });
  };

  const label = (x: { label_tr: string; label_en: string }) => (lang === "tr" ? x.label_tr : x.label_en);
  const channelOn = (c: ChannelPref) => pending[chanKey(c.name)] ?? c.enabled;
  const cellOn = (e: EventPref, c: ChannelPref) => pending[cellKey(e.event, c.name)] ?? (e.channels[c.name] ?? false);
  const reachable = (data?.channels ?? []).filter((c) => c.available);
  const unreachable = (data?.channels ?? []).filter((c) => !c.available);
  const live = reachable.filter(channelOn);
  const toggleCell = (e: EventPref, c: ChannelPref, on: boolean) => put([cellKey(e.event, c.name)], on, { events: { [e.event]: { [c.name]: on } } });
  const toggleGroup = (events: EventPref[], on: boolean) => {
    const body: Record<string, Record<string, boolean>> = {};
    const keys: string[] = [];
    for (const e of events) {
      body[e.event] = Object.fromEntries(live.map((c) => [c.name, on]));
      for (const c of live) keys.push(cellKey(e.event, c.name));
    }
    put(keys, on, { events: body });
  };
  const cards = phone && reachable.length > 3;

  return (
    <Card className={className} data-testid="notification-prefs">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BellRing className="size-4 text-label-3" aria-hidden />
          {t("notifications.prefs.title")}
        </CardTitle>
        <CardDescription>{t("notifications.prefs.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {q.isLoading ? (
          <div className="flex flex-col gap-2" aria-busy="true" aria-label={t("crbs.common.loading")}>
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-2/3" />
          </div>
        ) : null}
        {q.isError ? (
          <p role="alert" className="type-callout text-status-infeasible-fg">
            {t("notifications.prefs.loadFailed")}
          </p>
        ) : null}
        {data ? (
          <>
            <section aria-labelledby="prefs-channels" className="flex flex-col gap-1">
              <h3 id="prefs-channels" className="type-headline text-label-1">
                {t("notifications.prefs.channels")}
              </h3>
              <p className="type-footnote text-label-2">{t("notifications.prefs.channelsHint")}</p>
              {reachable.length ? (
                <ul className="mt-1 flex flex-col overflow-hidden rounded-xl bg-fill-3">
                  {reachable.map((c) => {
                    const id = `pref-channel-${c.name}`;
                    return (
                      <li key={c.name} className="flex min-h-11 items-center justify-between gap-3 px-3 py-2 hairline-b last:shadow-none">
                        <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer type-callout font-medium text-label-1">
                          {label(c)}
                        </label>
                        <Switch id={id} checked={channelOn(c)} onCheckedChange={(on) => put([chanKey(c.name)], on, { channels: { [c.name]: on } })} data-testid={id} />
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="mt-1 type-callout text-label-2">{t("notifications.prefs.noneReachable")}</p>
              )}
              <Unreachable channels={unreachable} label={label} />
            </section>

            {reachable.length ? (
              <section aria-labelledby="prefs-events" className="flex flex-col gap-2">
                <h3 id="prefs-events" className="type-headline text-label-1">
                  {t("notifications.prefs.events")}
                </h3>
                {groupEvents(data.events).map(({ group, events }) => {
                  const name = t(GROUP_KEY[group]);
                  const allOn = live.length > 0 && events.every((e) => live.every((c) => cellOn(e, c)));
                  const allId = `pref-group-${group}`;
                  return (
                    <details key={group} open={!phone || group === "approvals"} className="group/prefs overflow-hidden rounded-xl bg-fill-3" data-testid={`prefs-group-${group}`}>
                      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 py-2 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus) [&::-webkit-details-marker]:hidden">
                        <ChevronDown className="size-4 shrink-0 -rotate-90 text-label-3 transition-transform duration-(--dur-fast) group-open/prefs:rotate-0" aria-hidden />
                        <span className="flex-1 type-callout font-medium text-label-1">{name}</span>
                        <span className="type-footnote text-label-3">{t("notifications.prefs.groupCount", { n: events.length })}</span>
                      </summary>
                      <div className="flex min-h-11 items-center justify-between gap-3 px-3 py-1.5 hairline-t">
                        <label htmlFor={allId} className="min-w-0 flex-1 cursor-pointer type-footnote font-medium text-label-2">
                          {t("notifications.prefs.groupAll")}
                        </label>
                        <Switch id={allId} aria-label={t("notifications.prefs.groupAllLabel", { group: name })} checked={allOn} disabled={live.length === 0} onCheckedChange={(on) => toggleGroup(events, on)} data-testid={allId} />
                      </div>
                      {cards ? (
                        <ul className="flex flex-col" data-testid={`prefs-cards-${group}`}>
                          {events.map((e) => (
                            <li key={e.event} className="hairline-t" data-event={e.event}>
                              <p className="px-3 pt-2.5 pb-1 type-callout font-medium text-label-1">{label(e)}</p>
                              <ul>
                                {reachable.map((c) => {
                                  const id = `pref-${e.event}-${c.name}`;
                                  const off = !channelOn(c);
                                  return (
                                    <li key={c.name} className="flex min-h-11 items-center justify-between gap-3 px-3 py-1.5">
                                      <label htmlFor={id} className="min-w-0 flex-1 type-callout text-label-1">
                                        {label(c)}
                                        {off ? <span className="block type-caption text-label-3">{t("notifications.prefs.channelOff")}</span> : null}
                                      </label>
                                      <Switch id={id} checked={!off && cellOn(e, c)} disabled={off} onCheckedChange={(on) => toggleCell(e, c, on)} data-testid={id} />
                                    </li>
                                  );
                                })}
                              </ul>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div className="overflow-x-auto hairline-t">
                          <table className="w-full type-callout" data-testid={`prefs-matrix-${group}`}>
                            <thead>
                              <tr className="hairline-b">
                                <th scope="col" className="px-3 py-2 text-left type-footnote font-medium text-label-2">
                                  {t("notifications.prefs.event")}
                                </th>
                                {reachable.map((c) => (
                                  <th key={c.name} scope="col" className="w-20 px-2 py-2 text-center type-footnote font-medium text-label-2 sm:w-28">
                                    <span className="block">{label(c)}</span>
                                    {!channelOn(c) ? <span className="block type-caption font-normal text-label-3">{t("notifications.prefs.channelOff")}</span> : null}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {events.map((e) => (
                                <tr key={e.event} className="hairline-b last:shadow-none" data-event={e.event}>
                                  <th scope="row" className="h-11 px-3 py-2 text-left font-normal text-label-1">
                                    {label(e)}
                                  </th>
                                  {reachable.map((c) => {
                                    const off = !channelOn(c);
                                    return (
                                      <td key={c.name} className={cn("px-2 py-2 text-center", off && "opacity-70")}>
                                        <Switch
                                          aria-label={t("notifications.prefs.toggle", { event: label(e), channel: label(c) })}
                                          checked={!off && cellOn(e, c)}
                                          disabled={off}
                                          onCheckedChange={(on) => toggleCell(e, c, on)}
                                          data-testid={`pref-${e.event}-${c.name}`}
                                        />
                                      </td>
                                    );
                                  })}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </details>
                  );
                })}
              </section>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** One line for every channel that cannot reach the user (never one disabled switch per event). */
function Unreachable({ channels, label }: { channels: ChannelPref[]; label: (x: { label_tr: string; label_en: string }) => string }) {
  const { t } = useI18n();
  if (!channels.length) return null;
  const email = channels.find((c) => c.name === "email");
  const inApp = channels.find((c) => c.name === "in_app");
  const linked = channels.filter((c) => c !== email && c !== inApp);
  return (
    <div className="mt-1 flex flex-col gap-0.5 type-footnote text-label-2" data-testid="prefs-unreachable">
      {email ? <p>{t("notifications.prefs.noEmail")}</p> : null}
      {inApp ? <p>{t("notifications.prefs.unavailableInApp")}</p> : null}
      {linked.length ? (
        <p>
          {t("notifications.prefs.notLinked", { names: linked.map(label).join(", ") })}
          {" — "}
          <Link href="/profile#channels" className="font-medium text-tint-text underline-offset-2 hover:underline" data-testid="prefs-link-channels">
            {t("notifications.prefs.linkChannels")}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
