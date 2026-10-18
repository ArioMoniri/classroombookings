"use client";
/**
 * One set-password form for the local invite, the reset code and the admin-sent link (docs/design/v3/auth.md §4.5,
 * D12; AUX-05). One field with show/hide (no repeat field), `autocomplete=new-password` with `passwordrules`, a
 * hidden username field so password managers save the pair, the length hint and a live counter below the minimum,
 * and errors linked with aria-describedby. "Parolayı kaydet ve giriş yap" signs in: the backend answers a session
 * through the same gate as the password step (AU-B API.md §7), so a second step or the enrolment follows when needed.
 * The minimum is 12, or 8 when the account has 2FA (owner Q2; the backend says `min_length` on a refusal).
 */
import { Eye, EyeOff } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { IconButton } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { mfaErrorCode, signInStep, type SignInStepOut } from "@/lib/api/auth-security";
import { refusalBody } from "@/lib/api/error-text";
import { HttpError } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/provider";
import { rich } from "./signin-shell";
import { useFinishSignIn } from "./use-finish-sign-in";
import "./auth.css";

/** A few of the most common passwords (NIST: refuse values from breach corpuses); the backend has the last word. */
const COMMON = new Set(["123456789012", "password1234", "qwertyuiop12", "parola123456", "sifre1234567", "111111111111", "123123123123", "abc123456789", "iloveyou1234", "1q2w3e4r5t6y", "galatasaray1", "fenerbahce19", "besiktas1903", "trabzonspor6"]);

export type PasswordProblem = "short" | "blocklist" | "username" | null;

export function passwordProblem(pw: string, min: number, username?: string | null): PasswordProblem {
  if (pw.length < min) return "short";
  const low = pw.toLocaleLowerCase("tr-TR");
  const user = (username ?? "").split("@")[0]?.toLocaleLowerCase("tr-TR") ?? "";
  if (user.length >= 3 && low.includes(user)) return "username";
  if (COMMON.has(low)) return "blocklist";
  return null;
}

export function SetPasswordForm({ mode, token, username, org, minLength = 12, next = null, title = true }: { mode: "reset" | "invite"; token: string; username?: string | null; org?: string | null; minLength?: number; next?: string | null; title?: boolean }) {
  const { t } = useI18n();
  const finish = useFinishSignIn(next);
  const ids = { pw: useId(), hint: useId(), err: useId(), count: useId() };
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  const [min, setMin] = useState(minLength);
  const [problem, setProblem] = useState<PasswordProblem | "expired" | null>(null);
  const [busy, setBusy] = useState(false);
  const [signedOutDone, setSignedOutDone] = useState(false);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const p = passwordProblem(pw, min, username);
    if (p) {
      setProblem(p);
      shake();
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const out = await signInStep<SignInStepOut & { ok?: boolean }>(mode === "reset" ? "reset-confirm" : "invite-password", { token, password: pw, identifier: username ?? undefined, next });
      if (out.status === "none") {
        setSignedOutDone(true);
        setBusy(false);
        return;
      }
      await finish(out, "local");
    } catch (err) {
      setBusy(false);
      const code = mfaErrorCode(err);
      if (code === "password_too_short") {
        const need = refusalBody(err)?.min_length;
        if (typeof need === "number") setMin(need);
        setProblem("short");
      } else if (code === "password_common" || code === "password_breached") setProblem("blocklist");
      else if (code === "invalid_code" || code === "invite_invalid" || (err instanceof HttpError && (err.status === 400 || err.status === 404 || err.status === 410))) setProblem("expired");
      else setProblem("expired");
      shake();
    }
  };

  if (signedOutDone) {
    return (
      <Alert tone="success" data-testid="set-password-done">
        {t("crbs.reset.done")}
      </Alert>
    );
  }

  const message = problem === "short" ? t("auth.setPassword.short", { n: min }) : problem === "blocklist" ? t("auth.setPassword.blocklist") : problem === "username" ? t("auth.setPassword.username") : problem === "expired" ? t("auth.setPassword.expired") : null;
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4" data-testid="set-password-form">
      {title ? (
        <div className="flex flex-col gap-1.5">
          <h2 className="type-title-3 text-label-1">{t("auth.setPassword.title")}</h2>
          {username ? <p className="type-callout text-label-2">{rich(t("auth.setPassword.lead", { org: org ?? "" }).replace(/^\s+/, ""), { username })}</p> : null}
        </div>
      ) : null}
      {/* password managers save the pair */}
      <input type="text" name="username" autoComplete="username" value={username ?? ""} readOnly hidden />
      {problem === "expired" ? (
        <Alert tone="error" data-testid="set-password-expired">
          {message}
        </Alert>
      ) : null}
      <div ref={shakeRef} className="t-input flex flex-col gap-1.5">
        <label htmlFor={ids.pw} className="type-callout font-semibold text-label-1">
          {t("auth.setPassword.field")}
        </label>
        <div className="relative">
          <Input
            id={ids.pw}
            name="new-password"
            type={show ? "text" : "password"}
            fieldSize="lg"
            autoComplete="new-password"
            enterKeyHint="go"
            minLength={min}
            // eslint-disable-next-line react/no-unknown-property -- Safari's password-rules hint for generated passwords
            {...{ passwordrules: `minlength: ${min};` }}
            value={pw}
            onChange={(e) => {
              setPw(e.target.value);
              if (problem && problem !== "expired") setProblem(null);
            }}
            aria-invalid={(problem && problem !== "expired") || undefined}
            aria-describedby={[ids.hint, pw.length > 0 && pw.length < min ? ids.count : null, problem && problem !== "expired" ? ids.err : null].filter(Boolean).join(" ")}
            className="pr-12"
            data-testid="set-password-input"
          />
          <IconButton type="button" label={show ? t("signin.local.hide") : t("signin.local.show")} aria-pressed={show} aria-controls={ids.pw} onClick={() => setShow((s) => !s)} className="absolute top-1/2 right-0 size-11 -translate-y-1/2 rounded-lg text-label-2 active:scale-100">
            <span key={show ? "h" : "s"} className="auth-icon-swap">
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </span>
          </IconButton>
        </div>
        <p id={ids.hint} className="type-footnote text-label-2">
          {t("auth.setPassword.hint", { n: min })}
        </p>
        {pw.length > 0 && pw.length < min ? (
          <p id={ids.count} className="type-footnote tabular-nums text-label-3" aria-live="off" data-testid="set-password-count">
            {pw.length}/{min}
          </p>
        ) : null}
        {problem && problem !== "expired" ? (
          <p id={ids.err} className="type-footnote text-status-infeasible-fg" data-testid="set-password-error">
            {message}
          </p>
        ) : null}
      </div>
      <BusyButton type="submit" size="lg" shape="rect" className="w-full" busy={busy} busyLabel={t("auth.setPassword.busy")} data-testid="set-password-submit">
        {t("auth.setPassword.submit")}
      </BusyButton>
    </form>
  );
}
