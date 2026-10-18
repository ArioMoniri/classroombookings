"use client";
/**
 * "İki aşamalı doğrulama" row (docs/design/v3/auth.md §6.2, §6.3; AUX-06). Off: one tint "Aç" (the section's only
 * primary) → the setup sheet (re-authentication first when the sign-in is older than 10 minutes). On: "Yönet" with
 * "Yeni kurtarma kodları oluştur" and "Kapat" ("Kapat" hidden when the policy requires it, with the reason). The
 * shield draws a ✓ once when it turns on (free Success check, auth.css). "Uygulamayı değiştir" waits for AU-B
 * (`totp/start` refuses `already_enabled` while an app is on).
 */
import { ChevronDown, ShieldCheck, ShieldOff } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { OtpInput } from "@/components/auth/otp-input";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { authSecurity, mfaErrorCode, mfaErrorText, type MfaStatus } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { shortDate } from "./format";
import { MfaSetupSheet } from "./mfa-setup-sheet";
import { RecoveryCodes } from "./recovery-codes";
import { ReauthCancelled, useReauth } from "./reauth-dialog";
import type { TotpTransport } from "./totp-setup";
import "@/components/auth/auth.css";

export function SecurityRow({ title, status, action, testId, children }: { title: string; status: React.ReactNode; action?: React.ReactNode; testId?: string; children?: React.ReactNode }) {
  return (
    <li className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0" data-testid={testId}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="type-headline text-label-1">{title}</h3>
          <div className="type-callout text-label-2">{status}</div>
        </div>
        {action ? <div className="flex shrink-0 flex-wrap gap-2 max-sm:[&>*]:w-full">{action}</div> : null}
      </div>
      {children}
    </li>
  );
}

export function MfaRow({ status, org, onChanged }: { status: MfaStatus; org?: string | null; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const { run, dialog } = useReauth();
  const [setup, setSetup] = useState(false);
  const [justOn, setJustOn] = useState(false);
  const [regen, setRegen] = useState<"ask" | string[] | null>(null);
  const [off, setOff] = useState(false);
  const [offCode, setOffCode] = useState("");
  const [offError, setOffError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // the start call carries the re-authentication: the sheet opens only once it is through, and uses that answer
  const started = useRef<ReturnType<TotpTransport["start"]> | null>(null);
  const transport = useMemo<TotpTransport>(
    () => ({
      start: () => {
        const first = started.current;
        started.current = null;
        return first ?? authSecurity.totpStart();
      },
      confirm: (code) => authSecurity.totpConfirm(code),
    }),
    [],
  );
  const on = status.totp.enabled || status.passkeys.length > 0;
  const appOn = status.totp.enabled;
  const left = status.recovery_codes.remaining;

  if (status.reason === "mfa_off") {
    return <SecurityRow title={t("auth.security.mfa")} status={t("auth.security.mfaOrgOff")} testId="security-mfa" />;
  }

  const openSetup = async () => {
    try {
      started.current = run((pw) => authSecurity.totpStart(pw));
      await started.current;
      setSetup(true);
    } catch (e) {
      if (!(e instanceof ReauthCancelled)) toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    }
  };

  const regenerate = async () => {
    setBusy(true);
    try {
      const out = await run((pw) => authSecurity.regenerateCodes(pw));
      setRegen(out.recovery_codes);
      onChanged();
    } catch (e) {
      if (!(e instanceof ReauthCancelled)) toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
      setRegen(null);
    } finally {
      setBusy(false);
    }
  };

  const turnOff = async (e: FormEvent) => {
    e.preventDefault();
    if (offCode.length < 6) return;
    setBusy(true);
    setOffError(null);
    try {
      await run((pw) => authSecurity.disable(offCode, pw));
      setOff(false);
      setOffCode("");
      toast.success(t("auth.setup.offDone"));
      onChanged();
    } catch (err) {
      if (err instanceof ReauthCancelled) return;
      setOffError(mfaErrorCode(err) === "invalid_code" ? t("auth.mfa.wrong") : (mfaErrorText(err, locale) ?? t("auth.admin.errGeneric")));
      setOffCode("");
    } finally {
      setBusy(false);
    }
  };

  const statusLine = on ? (
    <span className="flex items-center gap-1.5">
      <ShieldCheck aria-hidden className={justOn ? "auth-check size-4 text-status-feasible-fg" : "size-4 text-status-feasible-fg"} />
      {appOn ? t("auth.security.mfaOn", { date: shortDate(status.totp.enabled_at, locale), n: left }) : t("auth.security.mfaOnPasskey", { n: left })}
    </span>
  ) : (
    <span className="flex items-center gap-1.5">
      <ShieldOff aria-hidden className="size-4" />
      {t("auth.security.mfaOff")}
    </span>
  );

  return (
    <SecurityRow
      title={t("auth.security.mfa")}
      status={
        <>
          {statusLine}
          {on && status.required ? <p className="mt-1 type-footnote text-label-3">{t("auth.security.requiredNote")}</p> : null}
        </>
      }
      testId="security-mfa"
      action={
        !on ? (
          <Button type="button" shape="rect" onClick={() => void openSetup()} data-testid="mfa-turn-on">
            {t("auth.security.turnOn")}
          </Button>
        ) : (
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button type="button" variant="secondary" shape="rect" data-testid="mfa-manage" />}>
              {t("auth.security.manage")}
              <ChevronDown aria-hidden />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setRegen("ask")} data-testid="mfa-new-codes">
                {t("auth.security.newCodes")}
              </DropdownMenuItem>
              {appOn && !status.required ? (
                <DropdownMenuItem variant="destructive" onClick={() => setOff(true)} data-testid="mfa-turn-off">
                  {t("auth.security.turnOff")}
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        )
      }
    >
      {dialog}
      <MfaSetupSheet
        open={setup}
        onOpenChange={setSetup}
        transport={transport}
        org={org}
        onDone={() => {
          setJustOn(true);
          toast.success(t("auth.enrol.done"));
          onChanged();
        }}
      />
      <Dialog open={regen !== null} onOpenChange={(o) => (!o ? setRegen(null) : undefined)}>
        <DialogContent data-testid="mfa-regen-dialog">
          {regen === "ask" ? (
            <>
              <DialogHeader>
                <DialogTitle>{t("auth.setup.regenTitle")}</DialogTitle>
                <DialogDescription>{t("auth.setup.regenBody")}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button type="button" variant="secondary" shape="rect" onClick={() => setRegen(null)}>
                  {t("auth.security.cancel")}
                </Button>
                <BusyButton type="button" shape="rect" busy={busy} busyLabel={t("busy.working")} onClick={() => void regenerate()} data-testid="mfa-regen-confirm">
                  {t("auth.setup.regenCreate")}
                </BusyButton>
              </DialogFooter>
            </>
          ) : regen ? (
            <>
              <DialogHeader>
                <DialogTitle>{t("auth.setup.newCodesTitle")}</DialogTitle>
              </DialogHeader>
              <RecoveryCodes codes={regen} org={org} account="" onFinish={() => (setRegen(null), toast.success(t("auth.setup.codesDone")))} />
            </>
          ) : null}
        </DialogContent>
      </Dialog>
      <Dialog open={off} onOpenChange={(o) => (setOff(o), setOffError(null), setOffCode(""))}>
        <DialogContent role="alertdialog" data-testid="mfa-off-dialog">
          <form onSubmit={turnOff} className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>{t("auth.setup.offTitle")}</DialogTitle>
              <DialogDescription>
                {t("auth.setup.offBody")}
                {status.passkeys.length ? ` ${t("auth.setup.offPasskeys")}` : ""}
              </DialogDescription>
            </DialogHeader>
            <p className="type-callout text-label-2">{t("auth.setup.offCode")}</p>
            <OtpInput value={offCode} onChange={setOffCode} state={offError ? "error" : "idle"} message={offError ?? undefined} autoFocus data-testid="mfa-off-code" />
            <DialogFooter>
              <Button type="button" variant="secondary" shape="rect" onClick={() => setOff(false)}>
                {t("auth.security.cancel")}
              </Button>
              <BusyButton type="submit" variant="destructive" shape="rect" busy={busy} busyLabel={t("busy.working")} disabled={offCode.length < 6} data-testid="mfa-off-confirm">
                {t("auth.security.turnOff")}
              </BusyButton>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </SecurityRow>
  );
}
