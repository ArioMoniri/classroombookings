"use client";
/**
 * Settings › Entegrasyonlar › Takvim eşitleme (KVKK; M-40, F-11 S09, F-04): `GET/PUT /calendar/admin/settings`
 * (backend `app/api/v1/calendar_sync.py`, `setup.settings`).
 *
 * - Off on a fresh install, with no sign-off (never pre-seeded, M-18). Turning it on shows what is transferred
 *   (booking date, time, room and notes to the calendars users connect, Google / Microsoft 365, servers abroad,
 *   and the subscription feeds) and needs the administrator's acknowledgement first.
 * - The backend writes the sign-off record on every change (who, when, the legal basis, the features) and an
 *   `integrations.calendar_sync` audit row; the record stays visible (E-8). Turning it off needs no
 *   acknowledgement and writes a new record (`enabled: false`); token feeds answer 404 from then on.
 * - The legal basis the backend stores (an English constant) reads in the user's language.
 * The outgoing webhooks switch lives in WebhooksAdmin, with the endpoints it governs.
 */
import { CalendarSync, ShieldCheck } from "lucide-react";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ResponsiveDialog } from "@/components/approvals/responsive-dialog";
import { useIntegrationSettings, useSaveIntegrationSettings, type CalendarSignoff } from "@/lib/api/approval-first";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";

/** `calendar_sync_signoff.legal_basis` as `app/api/v1/calendar_sync.py` writes it. */
export const CALENDAR_LEGAL_BASIS = "KVKK Art. 9 as amended by Law 7499 (cross-border transfer)";

export function SignoffRecord({ signoff }: { signoff: CalendarSignoff }) {
  const { t, locale } = useI18n();
  const basis = signoff.legal_basis === CALENDAR_LEGAL_BASIS ? t("notifications.admin.calendar.basis") : signoff.legal_basis;
  const when = new Date(signoff.at);
  const date = Number.isNaN(when.getTime()) ? signoff.at : when.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "long", timeStyle: "short" });
  const who = signoff.by || t("notifications.admin.calendar.someone");
  return (
    <div className="flex items-start gap-2 rounded-xl bg-fill-3 px-3 py-2.5 type-footnote text-label-2" data-testid="calendar-signoff">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-label-3" aria-hidden />
      <div className="min-w-0">
        <p className="text-label-1">{signoff.enabled ? t("notifications.admin.calendar.signedOn", { who, date }) : t("notifications.admin.calendar.signedOff", { who, date })}</p>
        {basis ? <p>{t("notifications.admin.calendar.legal", { basis })}</p> : null}
      </div>
    </div>
  );
}

export function CalendarSyncAdmin() {
  const { t, locale } = useI18n();
  const q = useIntegrationSettings();
  const save = useSaveIntegrationSettings();
  const [asking, setAsking] = useState(false);
  const [ack, setAck] = useState(false);
  const ackId = useId();
  const ackRef = useRef<HTMLInputElement>(null);
  const s = q.data;
  const fail = (e: unknown) => toast.error(errorText(wave1Error(e), locale) || t("notifications.admin.failed"));

  const setCalendar = (on: boolean) => {
    if (on) {
      setAck(false);
      setAsking(true);
      return;
    }
    save.mutate({ calendar_sync_enabled: false }, { onSuccess: () => toast.success(t("notifications.admin.calendar.savedOff")), onError: fail });
  };
  const confirm = () => {
    if (!ack) return;
    save.mutate(
      { calendar_sync_enabled: true },
      {
        onSuccess: () => {
          setAsking(false);
          toast.success(t("notifications.admin.calendar.savedOn"));
        },
        onError: fail,
      },
    );
  };

  return (
    <Card data-testid="calendar-sync-admin">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <CalendarSync className="size-4 text-label-3" aria-hidden />
            {t("notifications.admin.calendar.title")}
          </CardTitle>
          {s ? (
            <span data-testid="calendar-status-pill">
              <StatusBadge kind={s.calendar_sync_enabled ? "feasible" : "locked"} label={t(s.calendar_sync_enabled ? "notifications.admin.on" : "notifications.admin.off")} />
            </span>
          ) : null}
        </div>
        <CardDescription>{t("notifications.admin.calendar.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {q.isError ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {errorText(wave1Error(q.error), locale)}
          </p>
        ) : null}
        <div className="flex min-h-11 items-center justify-between gap-4 py-2.5">
          <div className="min-w-0">
            <Label htmlFor="calendar-sync-switch" className="type-callout font-medium text-label-1">
              {t("notifications.admin.calendar.switch")}
            </Label>
            <p className="type-footnote text-label-2">{t("notifications.admin.calendar.switchHint")}</p>
          </div>
          <Switch id="calendar-sync-switch" checked={!!s?.calendar_sync_enabled} disabled={!s || save.isPending} onCheckedChange={setCalendar} data-testid="calendar-sync-switch" />
        </div>
        {s ? s.calendar_sync_signoff ? <SignoffRecord signoff={s.calendar_sync_signoff} /> : <p className="pt-1 type-footnote text-label-3" data-testid="calendar-no-signoff">{t("notifications.admin.calendar.noSignoff")}</p> : null}
      </CardContent>

      <ResponsiveDialog
        open={asking}
        onOpenChange={(o) => !save.isPending && setAsking(o)}
        title={t("notifications.admin.calendar.noticeTitle")}
        description={t("notifications.admin.calendar.readFirst")}
        testId="calendar-notice"
        initialFocus={ackRef}
        footer={
          <>
            <Button variant="ghost" onClick={() => setAsking(false)} disabled={save.isPending}>
              {t("crbs.common.cancel")}
            </Button>
            <Button onClick={confirm} {...busyProps(save.isPending, !ack)} data-testid="calendar-confirm">
              <BusyLabel busy={save.isPending} label={t("busy.saving")}>
                {t("notifications.admin.calendar.enable")}
              </BusyLabel>
            </Button>
          </>
        }
      >
        <p className="rounded-xl bg-fill-3 p-3 type-callout leading-5 text-label-1" data-testid="calendar-notice-text">
          {t("notifications.admin.calendar.notice")}
        </p>
        <p className="type-footnote text-label-3">{t("notifications.admin.calendar.legalBefore")}</p>
        <label htmlFor={ackId} className="flex min-h-11 cursor-pointer items-start gap-3 type-callout text-label-1">
          <input id={ackId} ref={ackRef} type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-(--accent)" data-testid="calendar-ack" />
          <span>{t("notifications.admin.calendar.ack")}</span>
        </label>
      </ResponsiveDialog>
    </Card>
  );
}
