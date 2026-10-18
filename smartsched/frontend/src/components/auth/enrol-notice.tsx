"use client";
/**
 * The enrolment the policy requires (`/login/setup-2fa`, docs/design/v3/auth.md §5.6; AUX-04). Two modes:
 * - `enforced`: the grace period is over; the person has no session yet, only the setup token in the route handler's
 *   httpOnly cookie, so setup goes through `/api/auth/mfa/setup-*` and finishing it signs them in;
 * - `grace`: signed in, with "Daha sonra ({n} gün kaldı)".
 * "Şimdi kur" opens the same TOTP flow as Profil in the sheet; "İsterseniz bunun yerine geçiş anahtarı ekleyin."
 * offers a passkey instead (a passkey satisfies required 2FA, AU-B).
 */
import { KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { defaultPasskeyName } from "@/components/profile/security/aaguid";
import { RecoveryCodes } from "@/components/profile/security/recovery-codes";
import { TotpSetup, type TotpTransport } from "@/components/profile/security/totp-setup";
import { authSecurity, signInStep, TotpStart, type SignInStepOut } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { daysLeft } from "./mfa-model";
import { createPasskey, passkeyErrorKey, passkeyErrorKind, type ServerOptions } from "./passkey";
import { useFinishSignIn } from "./use-finish-sign-in";
import { homeFor } from "./signin-model";
import "./auth.css";

export function formatDeadline(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  const v = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  return new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "long", timeZone: "Europe/Istanbul" }).format(new Date(v));
}

export function EnrolNotice({ mode, graceUntil, methods, org, next, account, permissions }: { mode: "enforced" | "grace"; graceUntil: string | null; methods: string[]; org: string | null; next: string | null; account: string; permissions?: string[] | null }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const finish = useFinishSignIn(next);
  const [view, setView] = useState<"notice" | "totp" | "codes">("notice");
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastOut = useRef<SignInStepOut | null>(null);
  const left = daysLeft(graceUntil);
  const target = next ?? homeFor(permissions);
  const passkeyOk = methods.includes("passkey");

  const transport = useMemo<TotpTransport>(
    () =>
      mode === "enforced"
        ? {
            start: async () => TotpStart.parse(await signInStep<unknown>("setup-totp-start", {})),
            confirm: async (code) => {
              const out = await signInStep<SignInStepOut>("setup-totp-confirm", { code, next });
              lastOut.current = out;
              return { recovery_codes: out.recovery_codes ?? [] };
            },
          }
        : { start: () => authSecurity.totpStart(), confirm: (code) => authSecurity.totpConfirm(code) },
    [mode, next],
  );

  const done = async () => {
    toast.success(t("auth.enrol.done"), { duration: 4000 });
    if (mode === "enforced" && lastOut.current) await finish({ ...lastOut.current, recovery_codes: undefined }, "local");
    else {
      router.replace(target);
      router.refresh();
    }
  };

  const addPasskey = async () => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "enforced") {
        const { options } = await signInStep<{ options: ServerOptions }>("setup-passkey-options", {});
        const made = await createPasskey(options);
        const out = await signInStep<SignInStepOut>("setup-passkey-verify", { credential: made.credential, name: defaultPasskeyName(made.aaguid, locale), next });
        lastOut.current = out;
        if (out.recovery_codes?.length) {
          setCodes(out.recovery_codes);
          setView("codes");
        } else await done();
      } else {
        const o = await authSecurity.registerOptions();
        const made = await createPasskey(o.options);
        const out = await authSecurity.registerVerify(o.challenge_token ?? "", made.credential, defaultPasskeyName(made.aaguid, locale));
        if (out.recovery_codes?.length) {
          setCodes(out.recovery_codes);
          setView("codes");
        } else await done();
      }
    } catch (e) {
      setError(t(passkeyErrorKey(passkeyErrorKind(e), "add")));
    } finally {
      setBusy(false);
    }
  };

  if (view === "codes") {
    return (
      <div className="auth-step-in flex flex-col gap-3" data-testid="enrol-codes">
        <h1 id="signin-title" className="type-large-title text-label-1">
          {t("auth.setup.step3")}
        </h1>
        <RecoveryCodes codes={codes} org={org} account={account} onFinish={() => void done()} />
      </div>
    );
  }

  if (view === "totp") {
    return (
      <div className="flex flex-col gap-4" data-testid="enrol-setup">
        <h1 id="signin-title" className="type-large-title text-label-1">
          {t("auth.setup.title")}
        </h1>
        <TotpSetup transport={transport} org={org} onDone={() => void done()} />
      </div>
    );
  }

  return (
    <div className="auth-step-in flex flex-col" data-testid="enrol-notice">
      <h1 id="signin-title" className="type-large-title text-label-1">
        {t("auth.enrol.title")}
      </h1>
      <p className="mt-2 type-callout text-label-2">{org ? t("auth.enrol.lead", { org }) : t("auth.enrol.leadNoOrg")}</p>
      <div className="mt-4">
        <Alert tone={mode === "enforced" ? "warning" : "info"} data-testid="enrol-deadline">
          {mode === "enforced" || left <= 0 ? t("auth.enrol.passed") : t("auth.enrol.deadline", { date: formatDeadline(graceUntil, locale) })}
        </Alert>
      </div>
      {error ? (
        <div className="mt-3">
          <Alert tone="error" data-testid="enrol-error">
            {error}
          </Alert>
        </div>
      ) : null}
      <Button type="button" size="lg" shape="rect" className="mt-5 w-full" onClick={() => setView("totp")} data-testid="enrol-now">
        {t("auth.enrol.now")}
      </Button>
      {mode === "grace" && left > 0 ? (
        <Button type="button" variant="ghost" size="lg" shape="rect" className="mt-2 w-full" onClick={() => (router.replace(target), router.refresh())} data-testid="enrol-later">
          {t("auth.enrol.later", { n: left })}
        </Button>
      ) : null}
      {passkeyOk ? (
        <div className="mt-5 flex flex-col gap-2 pt-4 hairline-t">
          <p className="type-footnote text-label-2">{t("auth.enrol.orPasskey")}</p>
          <BusyButton type="button" variant="secondary" size="lg" shape="rect" className="w-full" busy={busy} busyLabel={t("auth.passkey.busy")} icon={<KeyRound aria-hidden />} onClick={() => void addPasskey()} data-testid="enrol-passkey">
            {t("auth.enrol.addPasskey")}
          </BusyButton>
        </div>
      ) : null}
    </div>
  );
}
