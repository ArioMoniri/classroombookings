"use client";
/**
 * Door 2 (docs/design/v2/sign-in.md §4.1 item 5, §5.4, §6.1, §6.3, §11): identifier + password for local and LDAP
 * accounts. One generic 401 string whatever the reason (no enumeration), both fields `aria-invalid`, password
 * cleared, identifier kept, focus on the alert; 429 shows the minutes and disables submit; status 0 the offline
 * string. Caps Lock footnote; `enterkeyhint` next / go; the submit is directly under the password.
 *
 * Motion (§10, "Local sign-in failed"): the alert enters with opacity + y −4 → 0 on springs.snappy and the field
 * group shakes once (280 ms, the transitions.dev shake already in ui/transitions); reduced motion: no shake, no
 * travel, a 100 ms opacity — the alert text, aria-invalid and focus carry the state.
 *
 * T-R1-09 (R1-A-27, R1-M-28, R1-A-28): an empty submit writes a message under each empty field ("Kullanıcı adı
 * veya e-posta gerekli", "Parola gerekli"), linked by aria-describedby and aria-invalid, and no alert; a refused
 * login moves focus to the alert (an effect, not a frame callback); the identifier field has inputmode=email; the
 * 429 lock belongs to the identifier it was earned for (the limit is per identifier), so typing another one
 * re-enables "Giriş yap".
 *
 * AUX-03/04 (docs/design/v3/auth.md §4.1–§4.3, §5): the password goes through the sign-in route handler
 * (`/api/auth/mfa/login`), which answers a session, a second step (→ `/login/verify`) or the enrolment the policy
 * requires (→ `/login/setup-2fa`); the challenge stays in its httpOnly cookie. With passwordless passkeys allowed
 * (`passkeySignIn`): the identifier offers passkeys through autofill (`username webauthn`, conditional `get()` while
 * the form is mounted, aborted on submit), the passkey button sits under the form (PasskeyDoor), and a successful
 * password sign-in tries a silent Conditional Create.
 */
import { Eye, EyeOff } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { IconButton } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import type { SignInStepOut } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { CREDENTIAL_FORM } from "./credential-form";
import { PasskeyDoor, tryConditionalCreate, usePasskeySignIn } from "./passkey-door";
import { LAST_METHOD_COOKIE, retryMinutes } from "./signin-model";
import { useFinishSignIn } from "./use-finish-sign-in";

type LocalError = { kind: "credentials" } | { kind: "rate"; minutes: number; until: number; identifier: string } | { kind: "offline" };

const normId = (v: string) => v.trim().toLocaleLowerCase("tr-TR");

type LoginOutcome = { ok: true; out: SignInStepOut } | { ok: false; status: number; retryAfter: string | null };

/** `POST /auth/login` through the sign-in route handler (it stores the JWT, or the challenge, in httpOnly cookies). */
async function postLogin(identifier: string, password: string, next: string | null): Promise<LoginOutcome> {
  let res: Response;
  try {
    res = await fetch("/api/auth/mfa/login", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ identifier: identifier.trim(), password, next }), credentials: "same-origin" });
  } catch {
    return { ok: false, status: 0, retryAfter: null };
  }
  if (!res.ok) return { ok: false, status: res.status, retryAfter: res.headers.get("retry-after") };
  const out = (await res.json().catch(() => null)) as SignInStepOut | null;
  return out ? { ok: true, out } : { ok: false, status: 502, retryAfter: null };
}

export function rememberMethod(method: "local" | "microsoft") {
  document.cookie = `${LAST_METHOD_COOKIE}=${method}; path=/; max-age=31536000; samesite=lax`;
}

export function LocalSignInForm({ next, primary, resetLink, lastMethodLocal, autoFocus, footnote, passkeySignIn = false, lastMethodPasskey = false }: { next: string | null; primary: boolean; resetLink: boolean; lastMethodLocal: boolean; autoFocus?: boolean; footnote?: string; passkeySignIn?: boolean; lastMethodPasskey?: boolean }) {
  const { t, locale } = useI18n();
  const reduce = useReduce();
  const finish = useFinishSignIn(next);
  const passkey = usePasskeySignIn(passkeySignIn, next);
  const { autofill } = passkey;
  // the identifier's passkey autofill runs while the form is mounted (door 2 open) and stops when it unmounts
  useEffect(() => autofill(), [autofill]);
  const ids = { error: useId(), caps: useId(), idRequired: useId(), pwRequired: useId() };
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<LocalError | null>(null);
  // the empty fields of the last submit (cleared as soon as the field gets a value)
  const [missing, setMissing] = useState<{ id: boolean; pw: boolean }>({ id: false, pw: false });
  const [now, setNow] = useState(() => Date.now());
  const alertRef = useRef<HTMLDivElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const idRef = useRef<HTMLInputElement>(null);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();
  // HB18-F02: no native submit before hydration (the button and Enter alike)
  const hydrated = useHydrated();

  useEffect(() => {
    if (autoFocus) idRef.current?.focus();
  }, [autoFocus]);

  // the 429 countdown updates once per minute, not per second (§11)
  const rateError = error?.kind === "rate" ? error : null;
  useEffect(() => {
    if (!rateError) return;
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    const done = window.setTimeout(() => setError(null), Math.max(0, rateError.until - Date.now()));
    return () => {
      window.clearInterval(id);
      window.clearTimeout(done);
    };
  }, [rateError]);
  // the lock is the identifier's, not the form's: another account can still sign in (T-R1-09)
  const rate = rateError && rateError.identifier === normId(identifier) ? rateError : null;
  const minutesLeft = rate ? Math.max(1, Math.ceil((rate.until - now) / 60_000)) : 0;

  // a refused login: the alert takes focus once it is in the tree (sign-in.md §6.1)
  useEffect(() => {
    if (error) alertRef.current?.focus();
  }, [error]);

  const fail = (e: LocalError) => {
    setNow(Date.now());
    setError(e);
    setPassword("");
    if (!reduce) shake();
    requestAnimationFrame(() => alertRef.current?.focus());
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || rate) return;
    const emptyId = !identifier.trim();
    const emptyPw = !password;
    if (emptyId || emptyPw) {
      setMissing({ id: emptyId, pw: emptyPw });
      if (error?.kind === "credentials") setError(null);
      (emptyId ? idRef : passwordRef).current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    passkey.abort();
    const out = await postLogin(identifier, password, next);
    if (!out.ok) {
      setBusy(false);
      if (out.status === 0 || out.status === 502 || out.status === 503 || out.status === 504) return fail({ kind: "offline" });
      if (out.status === 429) {
        const minutes = retryMinutes(out.retryAfter);
        return fail({ kind: "rate", minutes, until: Date.now() + minutes * 60_000, identifier: normId(identifier) });
      }
      return fail({ kind: "credentials" });
    }
    // §4.3 item 4: a silent passkey offer after a password sign-in (passwordless allowed only); never blocks
    if (passkeySignIn && out.out.status === "signed_in" && !out.out.password_change_required) void tryConditionalCreate((msg) => toast.success(msg, { duration: 4000 }), t, locale);
    // ~3 s greeting, gone before the first screen's own toasts (T-R1-06, R1-S-33); or the second step / enrolment
    await finish(out.out, "local");
    if (out.out.status !== "signed_in") setBusy(false);
  };

  // Caps Lock: the modifier state where the browser reports it, else the letter's case against Shift (a typed
  // upper-case letter without Shift, or a lower-case one with it, means the lock is on)
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    const state = typeof e.getModifierState === "function" ? e.getModifierState("CapsLock") : false;
    const letter = e.key.length === 1 && e.key.toLocaleLowerCase("tr-TR") !== e.key.toLocaleUpperCase("tr-TR");
    const byCase = letter && (e.key === e.key.toLocaleUpperCase("tr-TR")) !== e.shiftKey;
    setCaps(state || (letter ? byCase : false));
  };

  const message = error?.kind === "credentials" ? t("signin.local.credentials") : error?.kind === "offline" ? t("signin.local.offline") : rate ? t("signin.local.rateLimited", { n: minutesLeft }) : null;
  const invalid = error?.kind === "credentials" || undefined;
  const describedBy = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ") || undefined;

  return (
    <form {...CREDENTIAL_FORM} onSubmit={onSubmit} noValidate aria-describedby={message ? ids.error : undefined} className="flex flex-col" data-testid="login-form">
      {message ? (
        <motion.div
          key={error?.kind}
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reduce ? tween.reduced : springs.snappy}
          className="mb-4"
        >
          <div ref={alertRef} tabIndex={-1} id={ids.error} className="rounded-xl outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="login-error">
            <Alert tone="error" live="off">
              {message}
            </Alert>
          </div>
        </motion.div>
      ) : null}
      <div ref={shakeRef} className="t-input flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="identifier" className="type-callout font-semibold text-label-1">
            {t("signin.local.identifier")}
          </label>
          <Input
            ref={idRef}
            id="identifier"
            name="username"
            fieldSize="lg"
            autoComplete={passkeySignIn ? "username webauthn" : "username"}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            inputMode="email"
            enterKeyHint="next"
            placeholder={t("signin.local.identifierPlaceholder")}
            value={identifier}
            onChange={(e) => {
              setIdentifier(e.target.value);
              if (missing.id && e.target.value.trim()) setMissing((m) => ({ ...m, id: false }));
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !password && identifier.trim()) {
                e.preventDefault();
                passwordRef.current?.focus();
              }
            }}
            aria-invalid={invalid || missing.id || undefined}
            aria-describedby={describedBy(missing.id && ids.idRequired)}
            data-testid="login-identifier"
          />
          {missing.id ? (
            <p id={ids.idRequired} className="type-footnote text-status-infeasible-fg" data-testid="login-identifier-required">
              {t("signin.local.identifierRequired")}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor="password" className="type-callout font-semibold text-label-1">
              {t("signin.local.password")}
            </label>
            {resetLink ? (
              <Link href="/reset-password" className="-my-3 inline-flex min-h-11 items-center type-callout text-tint-text underline-offset-4 outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) pointer-fine:min-[600px]:min-h-0 pointer-fine:min-[600px]:my-0" data-testid="forgot-password">
                {t("signin.local.forgot")}
              </Link>
            ) : null}
          </div>
          <div className="relative">
            <Input
              ref={passwordRef}
              id="password"
              name="password"
              type={show ? "text" : "password"}
              fieldSize="lg"
              autoComplete="current-password"
              enterKeyHint="go"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (missing.pw && e.target.value) setMissing((m) => ({ ...m, pw: false }));
              }}
              onKeyDown={onKey}
              onKeyUp={onKey}
              aria-invalid={invalid || missing.pw || undefined}
              aria-describedby={describedBy(caps && ids.caps, missing.pw && ids.pwRequired)}
              className="pr-12"
              data-testid="login-password"
            />
            <IconButton
              type="button"
              label={show ? t("signin.local.hide") : t("signin.local.show")}
              aria-pressed={show}
              aria-controls="password"
              onClick={() => setShow((s) => !s)}
              className="absolute top-1/2 right-0 size-11 -translate-y-1/2 rounded-lg text-label-2 active:scale-100"
            >
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </IconButton>
          </div>
          {missing.pw ? (
            <p id={ids.pwRequired} className="type-footnote text-status-infeasible-fg" data-testid="login-password-required">
              {t("signin.local.passwordRequired")}
            </p>
          ) : null}
          {caps ? (
            <p id={ids.caps} className="type-footnote text-status-warning-fg" data-testid="caps-lock">
              {t("signin.local.capsLock")}
            </p>
          ) : null}
        </div>
      </div>
      <BusyButton
        type="submit"
        size="lg"
        shape="rect"
        variant={primary ? "default" : "secondary"}
        busy={busy}
        busyLabel={t("signin.local.busy")}
        disabled={Boolean(rate) || !hydrated}
        className={cn("mt-5 w-full")}
        data-testid="login-submit"
        data-primary={primary || undefined}
      >
        {t("signin.local.submit")}
      </BusyButton>
      <span role="status" className="sr-only">
        {busy ? t("signin.local.busy") : ""}
      </span>
      <PasskeyDoor ctl={passkey} />
      {footnote ? <p className="mt-3 type-footnote text-label-2" data-testid="login-no-account">{footnote}</p> : null}
      {lastMethodPasskey ? (
        <p className="mt-3 type-footnote text-label-3" data-testid="login-last-method">{t("auth.passkey.lastPasskey")}</p>
      ) : lastMethodLocal ? (
        <p className="mt-3 type-footnote text-label-3" data-testid="login-last-method">{t("signin.local.lastMethod")}</p>
      ) : null}
    </form>
  );
}
