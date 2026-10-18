"use client";
/**
 * "Hatırlanan cihazlar" + "Her yerden çıkış yap" (docs/design/v3/auth.md §6.5; AUX-07). Sessions are stateless tokens
 * (AU-B API.md §10), so until AU-15 brings a sessions list this block shows the remembered devices ("2FA {date}
 * tarihine kadar hatırlanıyor", "Unutulsun", "Hatırlanan tüm cihazları unut") and one "Her yerden çıkış yap"
 * (`POST /api/auth/logout`, which bumps the token version: every browser signs out). No IP addresses (KVKK).
 */
import { MonitorSmartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { authSecurity, mfaErrorText, type TrustedDevice } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { shortDate } from "./format";
import { SecurityRow } from "./mfa-row";
import "@/components/auth/auth.css";

export function DevicesRow({ devices, onChanged }: { devices: TrustedDevice[]; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const [busy, setBusy] = useState<number | "all" | "out" | null>(null);
  const [confirmOut, setConfirmOut] = useState(false);

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

  const signOutAll = async () => {
    setBusy("out");
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    } finally {
      router.replace("/login?reason=signed_out");
      router.refresh();
    }
  };

  return (
    <SecurityRow
      title={t("auth.security.devices")}
      status={devices.length ? null : t("auth.security.devicesNone")}
      action={
        <Button type="button" variant="secondary" shape="rect" onClick={() => setConfirmOut(true)} data-testid="sign-out-everywhere">
          {t("auth.security.signOutAll")}
        </Button>
      }
      testId="security-devices"
    >
      {devices.length ? (
        <>
          <ul className="flex flex-col divide-y divide-(--hairline) rounded-xl bg-fill-3" data-testid="device-list">
            {devices.map((d) => (
              <li key={d.id} className="auth-row-in flex items-center gap-3 px-3 py-2.5" data-testid="device-row">
                <MonitorSmartphone aria-hidden className="size-5 shrink-0 text-label-2" />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate type-callout font-semibold text-label-1">{d.label || "—"}</span>
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
        </>
      ) : null}
      <p className="type-footnote text-label-3">{t("auth.security.sessionsNote")}</p>
      <Dialog open={confirmOut} onOpenChange={setConfirmOut}>
        <DialogContent role="alertdialog" data-testid="sign-out-everywhere-dialog">
          <DialogHeader>
            <DialogTitle>{t("auth.security.signOutAllTitle")}</DialogTitle>
            <DialogDescription>{t("auth.security.signOutAllBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="secondary" shape="rect" onClick={() => setConfirmOut(false)}>
              {t("auth.security.cancel")}
            </Button>
            <BusyButton type="button" variant="destructive" shape="rect" busy={busy === "out"} busyLabel={t("busy.working")} onClick={() => void signOutAll()} data-testid="sign-out-everywhere-confirm">
              {t("auth.security.signOutAll")}
            </BusyButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SecurityRow>
  );
}
