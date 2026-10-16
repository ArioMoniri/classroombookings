"use client";
/**
 * Profile › Bildirimler (F-01 S11): which event reaches the user on which channel, `GET/PUT
 * /me/notification-preferences` (backend `app/services/notify_dispatch.py`).
 *
 * - Channels: the backend lists every registered channel (in-app, e-mail, and the external channels an
 *   administrator switched on: push, Telegram, WhatsApp, SMS, Teams / Slack) with the user's master switch and
 *   whether it can reach them. A channel that cannot (no e-mail address on the account; an external channel the
 *   user has not linked, or the institution has not switched on) is shown disabled with the reason as text.
 * - Events × channels: one switch per pair (desktop: a matrix; phone: one card per event with ≥ 44 px rows,
 *   MOBILE.md M-02 / M-07). Each switch saves at once (a partial PUT) and confirms with a toast; a failure puts
 *   the switch back and says so.
 *
 * Exported for the profile screen (the identity frontend mounts it): `<NotificationPreferencesPanel />`.
 */
import { BellRing } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { useNotificationPrefs, useSaveNotificationPrefs, type ChannelPref, type EventPref, type NotificationPrefsIn } from "@/lib/api/approval-first";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { pairLang } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

type Pending = Record<string, boolean>;
const chanKey = (c: string) => `c:${c}`;
const cellKey = (e: string, c: string) => `e:${e}:${c}`;

export function NotificationPreferencesPanel({ className }: { className?: string }) {
  const { t, locale } = useI18n();
  const q = useNotificationPrefs();
  const save = useSaveNotificationPrefs();
  const phone = useIsPhone();
  // the switch shows the new value while the PUT runs; the answer (or the old value on failure) replaces it
  const [pending, setPending] = useState<Pending>({});
  const lang = pairLang(locale);
  const data = q.data;

  const put = (key: string, on: boolean, body: NotificationPrefsIn) => {
    setPending((p) => ({ ...p, [key]: on }));
    save.mutate(body, {
      onSuccess: () => toast.success(t("notifications.prefs.saved")),
      onError: (e) => toast.error(errorText(wave1Error(e), locale) || t("notifications.prefs.failed")),
      onSettled: () =>
        setPending((p) => {
          const next = { ...p };
          delete next[key];
          return next;
        }),
    });
  };

  const channelOn = (c: ChannelPref) => pending[chanKey(c.name)] ?? c.enabled;
  const cellOn = (e: EventPref, c: ChannelPref) => pending[cellKey(e.event, c.name)] ?? (e.channels[c.name] ?? false);
  const why = (c: ChannelPref): string | null => {
    if (!c.available) return t(c.name === "email" ? "notifications.prefs.unavailableEmail" : c.name === "in_app" ? "notifications.prefs.unavailableInApp" : "notifications.prefs.unavailableOther");
    if (!channelOn(c)) return t("notifications.prefs.channelOff");
    return null;
  };
  const cellDisabled = (c: ChannelPref) => !c.available || !channelOn(c);
  const label = (x: { label_tr: string; label_en: string }) => (lang === "tr" ? x.label_tr : x.label_en);
  const toggleCell = (e: EventPref, c: ChannelPref, on: boolean) => put(cellKey(e.event, c.name), on, { events: { [e.event]: { [c.name]: on } } });

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
        {q.isLoading ? <p className="type-callout text-label-2">{t("crbs.common.loading")}</p> : null}
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
              <ul className="mt-1 flex flex-col overflow-hidden rounded-xl bg-fill-3">
                {data.channels.map((c) => {
                  const reason = !c.available ? why(c) : null;
                  const id = `pref-channel-${c.name}`;
                  return (
                    <li key={c.name} className="flex min-h-11 items-center justify-between gap-3 px-3 py-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none" data-available={c.available || undefined}>
                      <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
                        <span className="block type-callout font-medium text-label-1">{label(c)}</span>
                        {reason ? (
                          <span className="block type-footnote text-label-2" id={`${id}-why`}>
                            {reason}
                          </span>
                        ) : null}
                      </label>
                      <Switch
                        id={id}
                        checked={channelOn(c) && c.available}
                        disabled={!c.available}
                        aria-describedby={reason ? `${id}-why` : undefined}
                        onCheckedChange={(on) => put(chanKey(c.name), on, { channels: { [c.name]: on } })}
                        data-testid={id}
                      />
                    </li>
                  );
                })}
              </ul>
            </section>

            <section aria-labelledby="prefs-events" className="flex flex-col gap-2">
              <h3 id="prefs-events" className="type-headline text-label-1">
                {t("notifications.prefs.events")}
              </h3>
              {phone ? (
                <ul className="flex flex-col gap-3" data-testid="prefs-cards">
                  {data.events.map((e) => (
                    <li key={e.event} className="overflow-hidden rounded-xl bg-fill-3" data-event={e.event}>
                      <p className="px-3 pt-2.5 pb-1 type-callout font-medium text-label-1">{label(e)}</p>
                      <ul>
                        {data.channels.map((c) => {
                          const id = `pref-${e.event}-${c.name}`;
                          const note = cellDisabled(c) ? why(c) : null;
                          return (
                            <li key={c.name} className="flex min-h-11 items-center justify-between gap-3 px-3 py-1.5 shadow-[inset_0_1px_0_var(--hairline)]">
                              <label htmlFor={id} className="min-w-0 flex-1">
                                <span className="block type-callout text-label-1">{label(c)}</span>
                                {note ? <span className="block type-caption text-label-3">{note}</span> : null}
                              </label>
                              <Switch id={id} checked={cellOn(e, c) && !cellDisabled(c)} disabled={cellDisabled(c)} onCheckedChange={(on) => toggleCell(e, c, on)} data-testid={id} />
                            </li>
                          );
                        })}
                      </ul>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="overflow-x-auto rounded-xl bg-fill-3">
                  <table className="w-full type-callout" data-testid="prefs-matrix">
                    <thead>
                      <tr className="shadow-[inset_0_-1px_0_var(--hairline)]">
                        <th scope="col" className="px-3 py-2 text-left type-footnote font-medium text-label-2">
                          {t("notifications.prefs.event")}
                        </th>
                        {data.channels.map((c) => (
                          <th key={c.name} scope="col" className="w-28 px-3 py-2 text-center type-footnote font-medium text-label-2">
                            <span className="block">{label(c)}</span>
                            {cellDisabled(c) ? <span className="block type-caption font-normal text-label-3">{why(c)}</span> : null}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.events.map((e) => (
                        <tr key={e.event} className="shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none" data-event={e.event}>
                          <th scope="row" className="px-3 py-2.5 text-left font-normal text-label-1">
                            {label(e)}
                          </th>
                          {data.channels.map((c) => (
                            <td key={c.name} className={cn("px-3 py-2 text-center", cellDisabled(c) && "opacity-70")}>
                              <Switch
                                aria-label={t("notifications.prefs.toggle", { event: label(e), channel: label(c) })}
                                checked={cellOn(e, c) && !cellDisabled(c)}
                                disabled={cellDisabled(c)}
                                onCheckedChange={(on) => toggleCell(e, c, on)}
                                data-testid={`pref-${e.event}-${c.name}`}
                              />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
