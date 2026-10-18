"use client";
/**
 * The second step (`/login/verify`, docs/design/v3/auth.md §5; AUX-04), in the same sheet as the password. The
 * challenge token is in the route handler's httpOnly cookie, never in the URL. Order (also at 390 with the keypad):
 * title, account line + "Farklı bir hesap", lead, the 6 slots (focus on arrival), "Bu cihazı {n} gün hatırla" (off by
 * default; hidden when the policy sets 0), "Doğrula" (also automatic on the sixth digit), "Başka bir yöntem".
 *
 * States (§5.4): a wrong code clears the slots, shakes once and keeps focus; from the 2nd wrong code the clock hint;
 * 5 failures, an expired challenge or the lockout send the person back to `/login` with the notice; a wrong recovery
 * code keeps the field; offline keeps the slots. Motion: the step enters side by side (220 ms); "Doğrula" →
 * "Doğrulanıyor…" → "Doğrulandı ✓" (text swap + success check), then navigation after 240 ms (at once under reduced
 * motion).
 */
import { Check, KeyRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Checkbox } from "@/components/ui/checkbox";
import { mfaErrorCode, retryAfterSeconds, signInStep, type SignInStepOut } from "@/lib/api/auth-security";
import { HttpError } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { firstMethod } from "./mfa-model";
import { OtherMethods, type MfaView } from "./other-methods";
import { OtpInput, type OtpState } from "./otp-input";
import { getPasskey, PasskeyError, type ServerOptions } from "./passkey";
import { RecoveryCodeField } from "./recovery-code-field";
import { rich } from "./signin-shell";
import { useFinishSignIn } from "./use-finish-sign-in";
import "./auth.css";

export const MAX_TRIES = 5;

export function MfaStep({ methods, masked, next, rememberDays, contact }: { methods: string[]; masked: string | null; next: string | null; rememberDays: number; contact?: string | null }) {
  const { t } = useI18n();
  const router = useRouter();
  const reduce = useReduce();
  const finish = useFinishSignIn(next);
  const [view, setView] = useState<MfaView>(firstMethod(methods));
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [state, setState] = useState<OtpState>("idle");
  const [error, setError] = useState<"wrong" | "recoveryWrong" | "offline" | "passkey" | "passkeyCancelled" | "recoveryEmpty" | null>(null);
  const [fails, setFails] = useState(0);
  const [errorKey, setErrorKey] = useState(0);
  const otpRef = useRef<HTMLInputElement>(null);
  const rcRef = useRef<HTMLInputElement>(null);
  const leadId = useId();
  const rememberId = useId();
  const rememberHint = useId();

  useEffect(() => {
    if (view === "totp") otpRef.current?.focus();
    if (view === "recovery") rcRef.current?.focus();
  }, [view]);

  const back = (notice: "tooMany" | "expired" | "locked", minutes?: number) => {
    void signInStep("cancel").catch(() => undefined);
    router.replace(`/login?method=local&mfa=${notice}${minutes ? `&min=${minutes}` : ""}`);
  };

  const succeed = async (out: SignInStepOut, method: "local" | "passkey" = "local") => {
    setDone(true);
    setState("success");
    await new Promise((r) => setTimeout(r, reduce ? 0 : 240));
    await finish(out, method);
  };

  const refused = (e: unknown, kind: "code" | "recovery" | "passkey") => {
    setBusy(false);
    const c = mfaErrorCode(e);
    const status = e instanceof HttpError ? e.status : 0;
    if (c === "mfa_locked" || status === 429) return back("locked", Math.max(1, Math.ceil((retryAfterSeconds(e) ?? 900) / 60)));
    if (c === "challenge_expired") return back("expired");
    if (status === 0 || status >= 500) {
      setError("offline");
      return;
    }
    const n = fails + 1;
    setFails(n);
    if (n >= MAX_TRIES) return back("tooMany");
    if (kind === "code") {
      setError("wrong");
      setState("error");
      setErrorKey((k) => k + 1);
      setCode("");
      otpRef.current?.focus();
    } else if (kind === "recovery") {
      setError("recoveryWrong");
      rcRef.current?.focus();
    } else setError("passkey");
  };

  const submitCode = async (value: string) => {
    if (busy || done || value.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      const out = await signInStep("verify", { method: "totp", code: value, trust_device: remember, next });
      await succeed(out);
    } catch (e) {
      refused(e, "code");
    }
  };

  const submitRecovery = async () => {
    if (busy || done) return;
    if (!recovery.trim()) {
      setError("recoveryEmpty");
      rcRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await signInStep("verify", { method: "recovery", code: recovery, trust_device: remember, next });
      await succeed(out);
    } catch (e) {
      refused(e, "recovery");
    }
  };

  const runPasskey = async () => {
    if (busy || done) return;
    setBusy(true);
    setError(null);
    let credential: Record<string, unknown>;
    try {
      const { options } = await signInStep<{ options: ServerOptions }>("passkey-options", {});
      credential = await getPasskey(options);
    } catch (e) {
      setBusy(false);
      if (e instanceof PasskeyError) setError(e.kind === "cancelled" || e.kind === "aborted" ? "passkeyCancelled" : "passkey");
      else refused(e, "passkey");
      return;
    }
    try {
      const out = await signInStep("passkey-verify", { credential, trust_device: remember, next });
      await succeed(out, "passkey");
    } catch (e) {
      refused(e, "passkey");
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (view === "totp") void submitCode(code);
    else if (view === "recovery") void submitRecovery();
    else void runPasskey();
  };

  const otherAccount = () => {
    void signInStep("cancel").finally(() => router.replace("/login?method=local"));
  };

  const codeMessage = error === "wrong" ? (fails >= 2 ? `${t("auth.mfa.wrong")} ${t("auth.mfa.clock")}` : t("auth.mfa.wrong")) : undefined;
  const label = done ? t("auth.mfa.verified") : t("auth.mfa.verify");

  return (
    <form onSubmit={onSubmit} noValidate className="auth-step-in flex flex-col" data-testid="mfa-step">
      <h1 id="signin-title" className="type-large-title text-label-1">
        {t("auth.mfa.title")}
      </h1>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 type-callout text-label-2" data-testid="mfa-account">
        {masked ? <span>{rich(t("auth.mfa.signingInAs"), { masked })}</span> : null}
        <Link
          href="/login?method=local"
          onClick={(e) => {
            e.preventDefault();
            otherAccount();
          }}
          className="-my-3 inline-flex min-h-11 items-center text-tint-text underline-offset-4 outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)"
          data-testid="mfa-other-account"
        >
          {t("auth.mfa.otherAccount")}
        </Link>
      </div>
      <p id={leadId} className="mt-4 type-callout text-label-1">
        {view === "passkey" ? t("auth.mfa.leadPasskey") : view === "totp" ? t("auth.mfa.lead") : null}
      </p>

      {error === "offline" || error === "passkey" || error === "passkeyCancelled" ? (
        <div className="mt-3">
          <Alert tone={error === "passkeyCancelled" ? "neutral" : "error"} data-testid={`mfa-error-${error}`}>
            {error === "offline" ? t("auth.mfa.offline") : error === "passkeyCancelled" ? t("auth.passkey.cancelled") : t("auth.passkey.failed")}
          </Alert>
        </div>
      ) : null}

      <div className="mt-4">
        {view === "totp" ? (
          <OtpInput ref={otpRef} id="mfa-code" value={code} onChange={(v) => (setCode(v), error === "wrong" && setState("idle"))} onComplete={(v) => void submitCode(v)} state={done ? "success" : state} message={codeMessage} errorKey={errorKey} describedBy={leadId} autoFocus disabled={done} data-testid="mfa-otp" />
        ) : view === "recovery" ? (
          <RecoveryCodeField ref={rcRef} id="mfa-recovery" value={recovery} onChange={(v) => (setRecovery(v), setError(null))} invalid={error === "recoveryWrong" || error === "recoveryEmpty"} message={error === "recoveryWrong" ? t("auth.mfa.recoveryWrong") : error === "recoveryEmpty" ? t("auth.mfa.recoveryEmpty") : undefined} autoFocus data-testid="mfa-recovery" />
        ) : null}
      </div>

      {rememberDays > 0 ? (
        <div className="mt-4 flex flex-col gap-0.5">
          <label htmlFor={rememberId} className="flex min-h-11 cursor-pointer items-center gap-3 type-callout text-label-1 pointer-coarse:min-h-12">
            <Checkbox id={rememberId} checked={remember} onCheckedChange={(v) => setRemember(Boolean(v))} aria-describedby={rememberHint} data-testid="mfa-remember" />
            {t("auth.mfa.remember", { n: rememberDays })}
          </label>
          <p id={rememberHint} className="type-footnote text-label-2 pl-7 pointer-coarse:pl-14">
            {t("auth.mfa.rememberHint")}
          </p>
        </div>
      ) : null}

      <BusyButton type="submit" size="lg" shape="rect" className="mt-5 w-full" busy={busy && !done} busyLabel={t("auth.mfa.verifying")} icon={done ? <Check aria-hidden className="auth-check size-4" /> : view === "passkey" ? <KeyRound aria-hidden /> : undefined} data-testid="mfa-submit">
        <span key={label} className="auth-text-swap">
          {view === "passkey" && !done ? t("auth.mfa.usePasskey") : label}
        </span>
      </BusyButton>
      <span role="status" className="sr-only">
        {busy && !done ? t("auth.mfa.verifying") : done ? t("auth.mfa.verified") : ""}
      </span>

      <OtherMethods
        methods={methods}
        view={view}
        contact={contact}
        onPick={(v) => {
          setError(null);
          setState("idle");
          if (v === "passkey") {
            setView("passkey");
            void runPasskey();
          } else setView(v);
        }}
      />
    </form>
  );
}
