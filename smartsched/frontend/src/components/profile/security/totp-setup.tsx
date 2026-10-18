"use client";
/**
 * Turn on the authenticator app (docs/design/v3/auth.md §6.3; AUX-06, also the enrolment of §5.6). Two views:
 * - steps 1–2 together: the QR (black on white with a 4-module quiet zone, also in dark mode), the account line,
 *   "QR kodunu tarayamıyor musunuz?" → the 32-character key in 8 groups with "Kopyala", and the code field. On phones (< 1024 px) "Uygulamada aç"
 *   (`otpauth://`) leads, the key follows, and the QR sits behind a disclosure (you cannot scan your own screen);
 * - step 3: the recovery codes (RecoveryCodes).
 * 2FA is on once the code verifies; the pending set-up expires after `expires_in` (15 min): "Kurulum süresi doldu;
 * yeniden başlayın." with a new key. The transport differs: Profil (signed in, re-authenticated) or the enrolment
 * the policy forces (the setup token in the route handler's cookie).
 */
import { Check, ChevronDown, Copy, ExternalLink } from "lucide-react";
import QRCode from "qrcode";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, buttonVariants } from "@/components/ui/button";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { OtpInput, type OtpState } from "@/components/auth/otp-input";
import { mfaErrorCode, type TotpStart } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { RecoveryCodes } from "./recovery-codes";
import "@/components/auth/auth.css";

export interface TotpTransport {
  start: () => Promise<TotpStart>;
  confirm: (code: string) => Promise<{ recovery_codes?: string[] }>;
}

export type SetupStep = "connect" | "codes";

/** "ABCD EFGH …": the key in groups of 4. */
export const groupKey = (secret: string) => (secret.match(/.{1,4}/g) ?? []).join(" ");

export function TotpSetup({ transport, org, onStep, onDone, finishLabel }: { transport: TotpTransport; org?: string | null; onStep?: (s: SetupStep) => void; onDone: (codes: string[]) => void; finishLabel?: string }) {
  const { t } = useI18n();
  const wide = useMediaQuery("(min-width: 1024px)");
  const [data, setData] = useState<TotpStart | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [expired, setExpired] = useState(false);
  const [code, setCode] = useState("");
  const [state, setState] = useState<OtpState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [errorKey, setErrorKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [showQr, setShowQr] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [copied, setCopied] = useState(false);
  const otpRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const keyId = useId();

  const start = useCallback(async () => {
    setLoadError(false);
    setExpired(false);
    setData(null);
    setCode("");
    setState("idle");
    setMessage(null);
    try {
      setData(await transport.start());
    } catch (e) {
      if (mfaErrorCode(e) === "enrolment_expired") setExpired(true);
      else setLoadError(true);
    }
  }, [transport]);

  useEffect(() => {
    void start();
  }, [start]);

  // the pending set-up ends after expires_in (15 min): nothing expires while typing, the message says so after
  useEffect(() => {
    if (!data || codes) return;
    const id = window.setTimeout(() => setExpired(true), Math.max(1, data.expires_in) * 1000);
    return () => window.clearTimeout(id);
  }, [data, codes]);

  useEffect(() => {
    if (!data) return;
    let live = true;
    QRCode.toDataURL(data.otpauth_uri, { margin: 4, width: 352, errorCorrectionLevel: "M", color: { dark: "#000000", light: "#ffffff" } })
      .then((url) => live && setQr(url))
      .catch(() => live && setQr(null));
    return () => {
      live = false;
    };
  }, [data]);

  useEffect(() => {
    onStep?.(codes ? "codes" : "connect");
    if (codes) headingRef.current?.focus();
  }, [codes, onStep]);

  const confirm = async (value: string) => {
    if (busy || value.length !== 6) return;
    setBusy(true);
    setMessage(null);
    try {
      const out = await transport.confirm(value);
      setState("success");
      const next = out.recovery_codes ?? [];
      const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      window.setTimeout(() => setCodes(next), reduce ? 0 : 240);
    } catch (e) {
      const c = mfaErrorCode(e);
      if (c === "enrolment_expired") setExpired(true);
      else {
        setState("error");
        setMessage(t("auth.mfa.wrong"));
        setErrorKey((k) => k + 1);
        setCode("");
        otpRef.current?.focus();
      }
    } finally {
      setBusy(false);
    }
  };

  const copyKey = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.secret);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the key stays selectable on screen */
    }
  };

  if (codes) {
    return (
      <div className="auth-step-in flex flex-col gap-3" data-testid="setup-step-3">
        <h3 ref={headingRef} tabIndex={-1} className="type-headline text-label-1 outline-hidden">
          {t("auth.setup.step3")}
        </h3>
        <RecoveryCodes codes={codes} org={org} account={data?.account ?? ""} onFinish={() => onDone(codes)} finishLabel={finishLabel} />
      </div>
    );
  }

  if (expired || loadError) {
    return (
      <div className="flex flex-col gap-3" data-testid="setup-expired">
        <Alert tone={expired ? "warning" : "error"}>{expired ? t("auth.setup.expired") : t("auth.security.loadFailed")}</Alert>
        <Button type="button" variant="secondary" shape="rect" onClick={() => void start()} data-testid="setup-restart">
          {t("auth.setup.restart")}
        </Button>
      </div>
    );
  }

  const qrImage = qr ? (
    // eslint-disable-next-line @next/next/no-img-element -- a data URL drawn here; black on white in both themes
    <img src={qr} alt={t("auth.setup.qrAlt")} width={176} height={176} className="size-44 shrink-0 rounded-lg bg-white forced-colors:border forced-colors:border-[CanvasText]" data-testid="setup-qr" />
  ) : (
    <div aria-hidden className="size-44 shrink-0 rounded-lg bg-fill-3" />
  );

  const keyBlock = data ? (
    <div className="flex flex-col gap-1.5">
      <span id={keyId} className="type-footnote font-semibold text-label-2">
        {t("auth.setup.key")}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <code aria-labelledby={keyId} className="max-w-[20ch] rounded-lg bg-fill-3 px-3 py-2 font-mono type-callout tracking-wider break-words text-label-1 select-all" data-testid="setup-key">
          {groupKey(data.secret)}
        </code>
        <Button type="button" variant="secondary" shape="rect" size="md" onClick={() => void copyKey()} data-testid="setup-key-copy">
          <span key={copied ? "c" : "n"} className="auth-icon-swap">
            {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
          </span>
          <span key={copied ? "tc" : "tn"} className="auth-text-swap">
            {copied ? t("auth.setup.copied") : t("auth.setup.copy")}
          </span>
        </Button>
      </div>
      <span role="status" className="sr-only">
        {copied ? t("auth.setup.copied") : ""}
      </span>
    </div>
  ) : null;

  return (
    <div className="auth-step-in flex flex-col gap-5" data-testid="setup-step-12">
      <section className="flex flex-col gap-3">
        <h3 className="type-headline text-label-1">1 · {t("auth.setup.step1")}</h3>
        <p className="type-callout text-label-2">{wide ? t("auth.setup.step1Text") : t("auth.setup.step1Phone")}</p>
        {data ? <p className="type-footnote text-label-2">{`SmartSched (${data.issuer}) · ${data.account}`}</p> : null}
        {wide ? (
          <div className="flex flex-col gap-3">
            {qrImage}
            {/* §6.3: the key is behind "QR kodunu tarayamıyor musunuz?" (Panel reveal) */}
            <Button type="button" variant="ghost" shape="rect" aria-expanded={showKey} aria-controls={`${keyId}-panel`} onClick={() => setShowKey((v) => !v)} className="w-fit" data-testid="setup-cant-scan">
              {t("auth.setup.cantScan")}
              <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast) motion-reduce:transition-none", showKey && "rotate-180")} />
            </Button>
            {showKey ? (
              <div id={`${keyId}-panel`} className="auth-panel-in">
                {keyBlock}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {data ? (
              <a href={data.otpauth_uri} className={cn(buttonVariants({ variant: "default", size: "lg", shape: "rect" }), "w-full")} data-testid="setup-open-app">
                <ExternalLink aria-hidden />
                {t("auth.setup.openInApp")}
              </a>
            ) : null}
            {keyBlock}
            <Button type="button" variant="ghost" shape="rect" aria-expanded={showQr} onClick={() => setShowQr((v) => !v)} className="w-fit" data-testid="setup-show-qr">
              {t("auth.setup.showQr")}
            </Button>
            {showQr ? <div className="auth-panel-in">{qrImage}</div> : null}
          </div>
        )}
      </section>
      <section className="flex flex-col gap-3">
        <h3 className="type-headline text-label-1">2 · {t("auth.setup.step2")}</h3>
        <p id={`${keyId}-s2`} className="type-callout text-label-2">
          {t("auth.setup.step2Text")}
        </p>
        <OtpInput ref={otpRef} value={code} onChange={(v) => (setCode(v), state === "error" && setState("idle"))} onComplete={(v) => void confirm(v)} state={state} message={message} errorKey={errorKey} describedBy={`${keyId}-s2`} disabled={!data} data-testid="setup-otp" />
        <BusyButton type="button" size="lg" shape="rect" className="w-full" busy={busy} busyLabel={t("auth.mfa.verifying")} disabled={code.length !== 6 || state === "success"} onClick={() => void confirm(code)} data-testid="setup-verify">
          {state === "success" ? t("auth.mfa.verified") : t("auth.mfa.verify")}
        </BusyButton>
      </section>
    </div>
  );
}
