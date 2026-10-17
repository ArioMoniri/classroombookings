"use client";
/**
 * Ayarlar › Entegrasyonlar › Herkese açık günlük görünüm (V2; `GET/PUT /public-schedule/admin/settings`, setup.settings).
 *
 * Same pattern as calendar sync (calendar-sync-admin.tsx, M-40): off on a fresh install with no sign-off; turning it on
 * first shows what is published (room codes, course codes, generic block labels, "Rezerve" or nothing for bookings; no
 * names, notes or e-mail addresses) and needs the administrator's acknowledgement; the backend records who, when and
 * the legal basis, and the record stays visible. Off: every public page answers the same 404.
 */
import Link from "next/link";
import { ExternalLink, Monitor, ShieldCheck } from "lucide-react";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/common/status-badge";
import { ResponsiveDialog } from "@/components/approvals/responsive-dialog";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { PUBLIC_LEGAL_BASIS, usePublicSettings, useSavePublicSettings } from "@/lib/api/public-schedule";
import type { CalendarSignoff } from "@/lib/api/approval-first";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";

function Signoff({ signoff }: { signoff: CalendarSignoff }) {
  const { t, locale } = useI18n();
  const basis = signoff.legal_basis === PUBLIC_LEGAL_BASIS ? t("publicSchedule.admin.basis") : signoff.legal_basis;
  const when = new Date(signoff.at);
  const date = Number.isNaN(when.getTime()) ? signoff.at : when.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "long", timeStyle: "short" });
  const who = signoff.by || t("notifications.admin.calendar.someone");
  return (
    <div className="flex items-start gap-2 rounded-xl bg-fill-3 px-3 py-2.5 type-footnote text-label-2" data-testid="public-signoff">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-label-3" aria-hidden />
      <div className="min-w-0">
        <p className="text-label-1">{signoff.enabled ? t("publicSchedule.admin.signedOn", { who, date }) : t("publicSchedule.admin.signedOff", { who, date })}</p>
        {basis ? <p>{t("notifications.admin.calendar.legal", { basis })}</p> : null}
      </div>
    </div>
  );
}

export function PublicScheduleAdmin() {
  const { t, locale } = useI18n();
  const q = usePublicSettings();
  const save = useSavePublicSettings();
  const [asking, setAsking] = useState(false);
  const [ack, setAck] = useState(false);
  const ackId = useId();
  const ackRef = useRef<HTMLInputElement>(null);
  const showId = useId();
  const s = q.data;
  const fail = (e: unknown) => toast.error(errorText(wave1Error(e), locale) || t("notifications.admin.failed"));

  const setOn = (on: boolean) => {
    if (on) {
      setAck(false);
      setAsking(true);
      return;
    }
    save.mutate({ enabled: false }, { onSuccess: () => toast.success(t("publicSchedule.admin.savedOff")), onError: fail });
  };
  const confirm = () => {
    if (!ack) return;
    save.mutate(
      { enabled: true },
      {
        onSuccess: () => {
          setAsking(false);
          toast.success(t("publicSchedule.admin.savedOn"));
        },
        onError: fail,
      },
    );
  };

  return (
    <Card data-testid="public-schedule-admin">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Monitor className="size-4 text-label-3" aria-hidden />
            {t("publicSchedule.admin.title")}
          </CardTitle>
          {s ? (
            <span data-testid="public-status-pill">
              <StatusBadge kind={s.enabled ? "feasible" : "locked"} label={t(s.enabled ? "notifications.admin.on" : "notifications.admin.off")} />
            </span>
          ) : null}
        </div>
        <CardDescription>{t("publicSchedule.admin.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {q.isError ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {errorText(wave1Error(q.error), locale)}
          </p>
        ) : null}
        <div className="flex min-h-11 items-center justify-between gap-4 py-1.5">
          <div className="min-w-0">
            <Label htmlFor="public-schedule-switch" className="type-callout font-medium text-label-1">
              {t("publicSchedule.admin.switch")}
            </Label>
            <p className="type-footnote text-label-2">{t("publicSchedule.admin.switchHint")}</p>
          </div>
          <Switch id="public-schedule-switch" checked={!!s?.enabled} disabled={!s || save.isPending} onCheckedChange={setOn} data-testid="public-schedule-switch" />
        </div>
        <div className="flex flex-col gap-1.5 py-1.5">
          <span id={showId} className="type-callout font-medium text-label-1">
            {t("publicSchedule.admin.bookings")}
          </span>
          <SegmentedControl
            aria-labelledby={showId}
            size="sm"
            value={s?.show_bookings ?? "busy"}
            onValueChange={(v) => save.mutate({ show_bookings: v as "busy" | "hidden" }, { onSuccess: () => toast.success(t("publicSchedule.admin.saved")), onError: fail })}
            options={[
              { value: "busy", label: t("publicSchedule.admin.busy"), testId: "public-show-busy", disabled: !s },
              { value: "hidden", label: t("publicSchedule.admin.hidden"), testId: "public-show-hidden", disabled: !s },
            ]}
          />
          <p className="type-footnote text-label-3">{t("publicSchedule.admin.bookingsHint")}</p>
        </div>
        {s?.enabled ? (
          <Button variant="outline" size="sm" className="self-start" render={<Link href="/public" target="_blank" rel="noopener" />} nativeButton={false} data-testid="public-open">
            <ExternalLink aria-hidden />
            {t("publicSchedule.admin.open")}
          </Button>
        ) : null}
        {s ? s.signoff ? <Signoff signoff={s.signoff} /> : <p className="pt-1 type-footnote text-label-3" data-testid="public-no-signoff">{t("publicSchedule.admin.noSignoff")}</p> : null}
      </CardContent>

      <ResponsiveDialog
        open={asking}
        onOpenChange={(o) => !save.isPending && setAsking(o)}
        title={t("publicSchedule.admin.noticeTitle")}
        description={t("notifications.admin.calendar.readFirst")}
        testId="public-notice"
        initialFocus={ackRef}
        footer={
          <>
            <Button variant="ghost" onClick={() => setAsking(false)} disabled={save.isPending}>
              {t("crbs.common.cancel")}
            </Button>
            <Button onClick={confirm} {...busyProps(save.isPending, !ack)} data-testid="public-confirm">
              <BusyLabel busy={save.isPending} label={t("busy.saving")}>
                {t("publicSchedule.admin.enable")}
              </BusyLabel>
            </Button>
          </>
        }
      >
        <div className="rounded-xl bg-fill-3 p-3 type-callout leading-5 text-label-1" data-testid="public-notice-text">
          <p>{t("publicSchedule.admin.notice")}</p>
          <ul className="mt-2 list-disc pl-4">
            <li>{t("publicSchedule.admin.noticeShown")}</li>
            <li>{t("publicSchedule.admin.noticeHidden")}</li>
            <li>{t("publicSchedule.admin.noticeLimit")}</li>
          </ul>
        </div>
        <p className="type-footnote text-label-3">{t("notifications.admin.calendar.legalBefore")}</p>
        <label htmlFor={ackId} className="flex min-h-11 cursor-pointer items-start gap-3 type-callout text-label-1">
          <input id={ackId} ref={ackRef} type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-(--accent)" data-testid="public-ack" />
          <span>{t("publicSchedule.admin.ack")}</span>
        </label>
      </ResponsiveDialog>
    </Card>
  );
}
