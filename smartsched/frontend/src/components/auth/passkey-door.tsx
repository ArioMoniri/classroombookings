"use client";
/**
 * Passkeys in door 2 (docs/design/v3/auth.md §4.1 item 5.4, §4.2, §4.6; AUX-03). Only when the institution allows
 * passwordless sign-in (`/org/public` → `passkeys.sign_in`, decided on the server so nothing shifts after the first
 * paint):
 * - the identifier field gets `autocomplete="username webauthn"` and a conditional `get()` runs while door 2 is open
 *   (`usePasskeySignIn().autofill`); it is aborted when the password form submits, when door 2 closes (unmount) and
 *   before the modal request;
 * - under the form, a hairline with "veya" and the secondary "Geçiş anahtarıyla giriş yap" (modal `get()`; the
 *   browser's own sheet offers this device, another device by QR code and security keys).
 * Picking a passkey signs in directly, with no second step (D3). Failures: `NotAllowedError` → a neutral notice
 * without a focus move; an unknown credential → the error with focus, and `signalUnknownCredential` so the password
 * manager hides it; switched off → the neutral `disabledOrg`; anything else → `failed` with focus.
 */
import { KeyRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { authSecurity, mfaErrorCode, signInStep, type SignInStepOut } from "@/lib/api/auth-security";
import { HttpError } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/provider";
import { defaultPasskeyName } from "@/components/profile/security/aaguid";
import { conditionalCreate, getPasskey, PasskeyError, signalUnknown, startConditionalGet, type ConditionalHandle, type ServerOptions } from "./passkey";
import { useFinishSignIn } from "./use-finish-sign-in";

export type PasskeyNotice = "cancelled" | "unknown" | "failed" | "disabledOrg" | null;

const rpIdOf = (options: ServerOptions | null): string | null => {
  const pk = (options as { publicKey?: { rpId?: unknown } } | null)?.publicKey;
  return typeof pk?.rpId === "string" ? pk.rpId : null;
};

async function loadOptions(signal?: AbortSignal): Promise<ServerOptions> {
  const out = await signInStep<{ options: ServerOptions }>("signin-passkey-options", {}, signal);
  return out.options;
}

export interface PasskeySignIn {
  enabled: boolean;
  busy: boolean;
  notice: PasskeyNotice;
  /** start the identifier autofill (door 2 open); returns the abort */
  autofill: () => () => void;
  /** abort a pending autofill request (password submit) */
  abort: () => void;
  /** the "Geçiş anahtarıyla giriş yap" button */
  signIn: () => Promise<void>;
}

export function usePasskeySignIn(enabled: boolean, next: string | null): PasskeySignIn {
  const finish = useFinishSignIn(next);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<PasskeyNotice>(null);
  const handle = useRef<ConditionalHandle | null>(null);
  const lastOptions = useRef<ServerOptions | null>(null);
  const [round, setRound] = useState(0);

  const verify = useCallback(
    async (credential: Record<string, unknown>) => {
      setBusy(true);
      setNotice(null);
      try {
        const out = await signInStep<SignInStepOut>("signin-passkey-verify", { credential, next });
        await finish(out, "passkey");
      } catch (e) {
        setBusy(false);
        const code = mfaErrorCode(e);
        if (code === "passkey_sign_in_off") setNotice("disabledOrg");
        else if (code === "passkey_invalid" || (e instanceof HttpError && e.status === 401)) {
          setNotice("unknown");
          const rpId = rpIdOf(lastOptions.current);
          if (rpId && typeof credential.id === "string") void signalUnknown(rpId, credential.id);
        } else setNotice("failed");
        setRound((r) => r + 1); // a fresh autofill challenge
      }
    },
    [finish, next],
  );

  const abort = useCallback(() => {
    handle.current?.abort();
    handle.current = null;
  }, []);

  const autofill = useCallback(() => {
    if (!enabled) return () => undefined;
    abort();
    handle.current = startConditionalGet(
      async (signal) => {
        const o = await loadOptions(signal);
        lastOptions.current = o;
        return o;
      },
      (credential) => void verify(credential),
      () => setRound((r) => r + 1),
    );
    return abort;
  }, [abort, enabled, verify]);

  const signIn = useCallback(async () => {
    abort();
    setBusy(true);
    setNotice(null);
    let credential: Record<string, unknown>;
    try {
      const options = await loadOptions();
      lastOptions.current = options;
      credential = await getPasskey(options);
    } catch (e) {
      setBusy(false);
      if (mfaErrorCode(e) === "passkey_sign_in_off") setNotice("disabledOrg");
      else setNotice(e instanceof PasskeyError && (e.kind === "cancelled" || e.kind === "aborted") ? "cancelled" : "failed");
      setRound((r) => r + 1);
      return;
    }
    await verify(credential);
  }, [abort, verify]);

  // restart the autofill after a failure (its challenge was used up)
  useEffect(() => {
    if (round === 0 || !enabled || busy) return;
    return autofill();
  }, [round, enabled, busy, autofill]);

  return { enabled, busy, notice, autofill, abort, signIn };
}

/** "veya" + the secondary passkey button, and the notice of the last attempt. */
export function PasskeyDoor({ ctl }: { ctl: PasskeySignIn }) {
  const { t } = useI18n();
  const alertRef = useRef<HTMLDivElement>(null);
  const focusing = ctl.notice === "unknown" || ctl.notice === "failed";
  useEffect(() => {
    if (focusing) alertRef.current?.focus();
  }, [focusing, ctl.notice]);
  if (!ctl.enabled) return null;
  return (
    <div className="mt-5 flex flex-col gap-4 [@media(max-height:960px)]:mt-3" data-testid="passkey-door">
      <div className="flex items-center gap-3 type-footnote text-label-3" aria-hidden>
        <span className="h-px flex-1 bg-(--hairline)" />
        {t("auth.passkey.or")}
        <span className="h-px flex-1 bg-(--hairline)" />
      </div>
      {ctl.notice ? (
        <div ref={alertRef} tabIndex={-1} className="rounded-xl outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid={`passkey-notice-${ctl.notice}`}>
          <Alert tone={focusing ? "error" : "neutral"} live={focusing ? "off" : "polite"}>
            {t(`auth.passkey.${ctl.notice}`)}
          </Alert>
        </div>
      ) : null}
      <BusyButton type="button" variant="secondary" size="lg" shape="rect" className="w-full" busy={ctl.busy} busyLabel={t("auth.passkey.busy")} onClick={() => void ctl.signIn()} icon={<KeyRound aria-hidden />} data-testid="passkey-signin">
        {t("auth.passkey.button")}
      </BusyButton>
    </div>
  );
}

/**
 * §4.3 item 4: after a password sign-in, ask the browser to save a passkey silently (Chrome Conditional Create). Only
 * with passwordless sign-in allowed; any failure (no capability, refused, server said no) is silent. The backend
 * accepts the registration without a password within 10 minutes of the sign-in (AU-B §4 re-auth window).
 */
export async function tryConditionalCreate(onSaved: (message: string) => void, t: ReturnType<typeof useI18n>["t"], locale = "tr"): Promise<boolean> {
  let token: string | undefined;
  const made = await conditionalCreate(async () => {
    const o = await authSecurity.registerOptions();
    token = o.challenge_token;
    return o.options;
  });
  if (!made || !token) return false;
  try {
    await authSecurity.registerVerify(token, made.credential, defaultPasskeyName(made.aaguid, locale));
    onSaved(t("auth.passkey.saved"));
    return true;
  } catch {
    return false;
  }
}
