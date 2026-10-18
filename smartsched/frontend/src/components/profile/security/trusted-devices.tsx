"use client";
/**
 * "Hatırlanan cihazlar" inside "Oturumlar ve cihazlar" (docs/design/v3/auth.md §5.5, §6.5; AUX-07): the devices that
 * skip the second step ("2FA {date} tarihine kadar hatırlanıyor"), each with "Unutulsun", and "Hatırlanan tüm
 * cihazları unut" when there are several. A `<ul>`; no addresses (KVKK).
 */
import { MonitorSmartphone } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { BusyButton } from "@/components/ui/busy-label";
import { authSecurity, mfaErrorText, type TrustedDevice } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { shortDate } from "./format";
import "@/components/auth/auth.css";

export function RememberedDevices({ devices, onChanged }: { devices: TrustedDevice[]; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const [busy, setBusy] = useState<number | "all" | null>(null);

  const forget = async (id: number | "all") => {
    setBusy(id);
    try {
      if (id === "all") {
        const out = await authSecurity.forgetAllDevices();
        toast.success(t("auth.security.forgottenAll", { n: out.revoked }));
      } else {
        await authSecurity.forgetDevice(id);
        toast.success(t("auth.security.forgotten"));
      }
      onChanged();
    } catch (e) {
      toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    } finally {
      setBusy(null);
    }
  };

  if (!devices.length) return null;
  return (
    <div className="flex flex-col gap-2" data-testid="remembered-devices">
      <h4 className="type-subheadline font-semibold text-label-1">{t("auth.security.devices")}</h4>
      <ul className="flex flex-col divide-y divide-(--hairline) rounded-xl bg-fill-3" data-testid="device-list">
        {devices.map((d) => (
          <li key={d.id} className="auth-row-in flex flex-wrap items-center gap-3 px-3 py-2.5" data-testid="device-row">
            <MonitorSmartphone aria-hidden className="size-5 shrink-0 text-label-2" />
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="truncate type-callout font-semibold text-label-1">{d.label || t("auth.security.unknownDevice")}</span>
              <span className="type-footnote text-label-2">{t("auth.security.deviceUntil", { date: shortDate(d.expires_at, locale) })}</span>
            </div>
            <BusyButton type="button" variant="ghost" shape="rect" busy={busy === d.id} busyLabel={t("busy.working")} onClick={() => void forget(d.id)} data-testid="device-forget">
              {t("auth.security.forget")}
            </BusyButton>
          </li>
        ))}
      </ul>
      {devices.length > 1 ? (
        <BusyButton type="button" variant="ghost" shape="rect" className="self-start" busy={busy === "all"} busyLabel={t("busy.working")} onClick={() => void forget("all")} data-testid="device-forget-all">
          {t("auth.security.forgetAll")}
        </BusyButton>
      ) : null}
    </div>
  );
}
