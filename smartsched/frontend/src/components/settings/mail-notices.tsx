"use client";
/**
 * Ayarlar › Genel › E-posta bildirimleri (RF-11; backend app/services/mail_senders.py): two organisation settings of
 * `PUT /org/settings` (setup.settings, audited by the settings hook):
 * - `reminder_lead_hours` (0-336, default 24): booking reminders go this many hours before the start; 0 = none.
 *   Each person can still switch reminders off in Profil › Bildirimler.
 * - `new_device_sign_in_mail` (default on): "Yeni cihazdan giriş" security e-mails. A person cannot switch it off;
 *   only the organisation can.
 * Mounted by settings-view.tsx in the general tab for setup.settings holders.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Field } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { request } from "@/lib/api/client";
import { crbsKeys } from "@/lib/api/crbs";
import { refusalBody } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";

const Notices = z.object({
  reminder_lead_hours: z.number().int().catch(24).default(24),
  new_device_sign_in_mail: z.boolean().catch(true).default(true),
});
type Notices = z.infer<typeof Notices>;
const KEY = ["org", "settings", "mail-notices"];
export const LEAD_MAX = 336;

/** The typed hours as a whole number in 0-336, or null (empty, a fraction, out of range). */
export function parseLeadHours(raw: string): number | null {
  const text = raw.replace(/ /g, " ").trim();
  if (!/^\d{1,3}$/.test(text)) return null;
  const n = Number(text);
  return n >= 0 && n <= LEAD_MAX ? n : null;
}

export function MailNoticesCard() {
  const { t, locale } = useI18n();
  const ids = useId();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: () => request("/org/settings", { schema: Notices, silent: true }) });
  const [hours, setHours] = useState<string | null>(null);
  const [newDevice, setNewDevice] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hoursRef = useRef<HTMLInputElement>(null);
  const saveRef = useRef<HTMLButtonElement>(null);
  const shownHours = hours ?? (q.data ? String(q.data.reminder_lead_hours) : "");
  const shownDevice = newDevice ?? q.data?.new_device_sign_in_mail ?? true;

  const save = useMutation({
    mutationFn: (body: Notices) => request("/org/settings", { method: "PUT", body, schema: Notices, silent: true }),
    onSuccess: (data: Notices) => {
      qc.setQueryData(KEY, data);
      void qc.invalidateQueries({ queryKey: crbsKeys.orgSettings });
      setHours(null);
      setNewDevice(null);
      setError(null);
      toast.success(t("settings.mailNotices.saved"));
      saveRef.current?.focus();
    },
    onError: (e: unknown) => {
      const d = refusalBody(e);
      const said = d ? (locale === "tr" ? d.message_tr : d.message_en) : null;
      toast.error(typeof said === "string" && said ? said : t("settings.mailNotices.failed"));
      saveRef.current?.focus();
    },
  });

  const lead = parseLeadHours(shownHours);
  return (
    <Card data-testid="settings-mail-notices">
      <CardHeader>
        <CardTitle>{t("settings.mailNotices.title")}</CardTitle>
        <CardDescription>{t("settings.mailNotices.lead")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (save.isPending) return;
            if (lead === null) {
              setError(t("settings.mailNotices.hoursInvalid"));
              hoursRef.current?.focus();
              return;
            }
            setError(null);
            save.mutate({ reminder_lead_hours: lead, new_device_sign_in_mail: shownDevice });
          }}
        >
          <Field label={t("settings.mailNotices.hours")} htmlFor={`${ids}-hours`} hint={lead === 0 ? t("settings.mailNotices.hoursOff") : t("settings.mailNotices.hoursHint")} error={error}>
            <div className="flex items-center gap-2">
              <Input
                id={`${ids}-hours`}
                ref={hoursRef}
                // text, not number: a number input silently drops the comma of a Turkish "2,5" (saved as 25 h);
                // parseLeadHours refuses it with the inline error instead (e2e 2026-10-18)
                type="text"
                inputMode="numeric"
                autoComplete="off"
                className="w-24 max-md:text-base"
                aria-invalid={error ? true : undefined}
                value={shownHours}
                onChange={(e) => setHours(e.target.value)}
                data-testid="mail-notices-hours"
              />
              <span className="type-footnote text-label-2">{t("settings.mailNotices.hoursUnit")}</span>
            </div>
          </Field>
          <div className="flex min-h-11 items-center justify-between gap-4">
            <span className="min-w-0">
              <span className="block type-callout font-medium text-label-1">{t("settings.mailNotices.newDevice")}</span>
              <span id={`${ids}-device-hint`} className="block type-footnote text-label-2">{t("settings.mailNotices.newDeviceHint")}</span>
            </span>
            <Switch checked={shownDevice} onCheckedChange={(v: boolean) => setNewDevice(v)} aria-label={t("settings.mailNotices.newDevice")} aria-describedby={`${ids}-device-hint`} data-testid="mail-notices-new-device" />
          </div>
          {/* never disabled while saving: a disabled button drops the focus to <body>; a second submit is ignored */}
          <Button ref={saveRef} type="submit" aria-busy={save.isPending || undefined} className="pointer-coarse:min-h-11" data-testid="mail-notices-save">
            {t("settings.mailNotices.save")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
