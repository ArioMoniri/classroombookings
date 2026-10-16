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
 */
import { Eye, EyeOff } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { applySessionLanguage } from "@/components/bookings/use-booking-format";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { IconButton } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { MeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { homeFor, LAST_METHOD_COOKIE, retryMinutes } from "./signin-model";

type LocalError = { kind: "credentials" } | { kind: "rate"; minutes: number; until: number } | { kind: "offline" };

type LoginOutcome = { ok: true; user: MeFull | null; mustChangePassword: boolean } | { ok: false; status: number; retryAfter: string | null };

/** `POST /auth/login` through the proxy (it stores the JWT in the httpOnly cookie and returns `/auth/me`). */
async function postLogin(identifier: string, password: string): Promise<LoginOutcome> {
  const id = identifier.trim();
  const body = id.includes("@") ? { email: id, password } : { username: id, password };
  let res: Response;
  try {
    res = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body), credentials: "same-origin" });
  } catch {
    return { ok: false, status: 0, retryAfter: null };
  }
  if (!res.ok) return { ok: false, status: res.status, retryAfter: res.headers.get("retry-after") };
  const out = (await res.json().catch(() => null)) as { user?: unknown; password_change_required?: boolean } | null;
  const parsed = MeFull.safeParse(out?.user);
  const user = parsed.success ? parsed.data : null;
  return { ok: true, user, mustChangePassword: Boolean(out?.password_change_required) || Boolean(user?.force_password_reset) };
}

export function rememberMethod(method: "local" | "microsoft") {
  document.cookie = `${LAST_METHOD_COOKIE}=${method}; path=/; max-age=31536000; samesite=lax`;
}

export function LocalSignInForm({ next, primary, resetLink, lastMethodLocal, autoFocus, footnote }: { next: string | null; primary: boolean; resetLink: boolean; lastMethodLocal: boolean; autoFocus?: boolean; footnote?: string }) {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const reduce = useReduce();
  const ids = { error: useId(), caps: useId() };
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<LocalError | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const alertRef = useRef<HTMLDivElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const idRef = useRef<HTMLInputElement>(null);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();

  useEffect(() => {
    if (autoFocus) idRef.current?.focus();
  }, [autoFocus]);

  // the 429 countdown updates once per minute, not per second (§11)
  const rate = error?.kind === "rate" ? error : null;
  useEffect(() => {
    if (!rate) return;
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    const done = window.setTimeout(() => setError(null), Math.max(0, rate.until - Date.now()));
    return () => {
      window.clearInterval(id);
      window.clearTimeout(done);
    };
  }, [rate]);
  const minutesLeft = rate ? Math.max(1, Math.ceil((rate.until - now) / 60_000)) : 0;

  const fail = (e: LocalError) => {
    setError(e);
    setPassword("");
    if (!reduce) shake();
    requestAnimationFrame(() => alertRef.current?.focus());
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || rate) return;
    if (!identifier.trim() || !password) {
      (identifier.trim() ? passwordRef : idRef).current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    const out = await postLogin(identifier, password);
    if (!out.ok) {
      setBusy(false);
      if (out.status === 0 || out.status === 502 || out.status === 503 || out.status === 504) return fail({ kind: "offline" });
      if (out.status === 429) {
        const minutes = retryMinutes(out.retryAfter);
        return fail({ kind: "rate", minutes, until: Date.now() + minutes * 60_000 });
      }
      return fail({ kind: "credentials" });
    }
    rememberMethod("local");
    const target = next ?? homeFor(out.user?.permissions);
    if (out.mustChangePassword) {
      router.replace(`/login/change-password?next=${encodeURIComponent(target)}`);
      return;
    }
    if (out.user) await applySessionLanguage(out.user.id, locale, setLocale);
    const name = out.user?.full_name?.split(" ")[0];
    toast.success(name ? t("glass.auth.welcome", { name }) : t("signin.title"));
    router.replace(target);
    router.refresh();
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (typeof e.getModifierState === "function") setCaps(e.getModifierState("CapsLock"));
  };

  const message = error?.kind === "credentials" ? t("signin.local.credentials") : error?.kind === "offline" ? t("signin.local.offline") : rate ? t("signin.local.rateLimited", { n: minutesLeft }) : null;
  const invalid = error?.kind === "credentials" || undefined;

  return (
    <form onSubmit={onSubmit} noValidate aria-describedby={message ? ids.error : undefined} className="flex flex-col" data-testid="login-form">
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
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="next"
            placeholder={t("signin.local.identifierPlaceholder")}
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !password) {
                e.preventDefault();
                passwordRef.current?.focus();
              }
            }}
            aria-invalid={invalid}
            data-testid="login-identifier"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor="password" className="type-callout font-semibold text-label-1">
              {t("signin.local.password")}
            </label>
            {resetLink ? (
              <Link href="/reset-password" className="-my-3 inline-flex min-h-11 items-center type-callout text-tint-text underline-offset-4 outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) min-[600px]:min-h-0 min-[600px]:my-0" data-testid="forgot-password">
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
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={onKey}
              onKeyUp={onKey}
              aria-invalid={invalid}
              aria-describedby={caps ? ids.caps : undefined}
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
        disabled={Boolean(rate)}
        className={cn("mt-5 w-full")}
        data-testid="login-submit"
        data-primary={primary || undefined}
      >
        {t("signin.local.submit")}
      </BusyButton>
      <span role="status" className="sr-only">
        {busy ? t("signin.local.busy") : ""}
      </span>
      {footnote ? <p className="mt-3 type-footnote text-label-2" data-testid="login-no-account">{footnote}</p> : null}
      {lastMethodLocal ? <p className="mt-3 type-footnote text-label-3" data-testid="login-last-method">{t("signin.local.lastMethod")}</p> : null}
    </form>
  );
}
