"use client";
/**
 * The 6-digit code input (docs/design/v3/auth.md §10.4, D5; AUX-02). Built on `input-otp` (guilhermerodz, MIT;
 * components/ui/SOURCES.md): ONE real `<input>` (inputmode numeric, autocomplete one-time-code, maxlength 6), drawn
 * as 6 slots grouped 3 + 3, so screen readers hear one field named "Doğrulama kodu", there is one tab stop, and iOS /
 * Android offer the code from Messages or the password manager. Paste strips spaces, hyphens and other non-digits
 * ("123 456", "123-456"); `onComplete` fires on the sixth digit.
 *
 * Slots: 44 × 52 on fine pointers, 48 × 56 on coarse ones, radius 10, gap 8, 16 between the groups; digits 24 px /
 * 600 tabular. The active slot carries the focus ring and a 2 × 24 px caret that blinks in 1 s steps (steady under
 * reduced motion, auth.css); the caret and ring jump without animation. Error: every slot gets the error edge, the
 * message sits under the slots (aria-describedby) and the group shakes once (the shipped transitions.dev shake,
 * `.t-input`, no-op under reduced motion) each time `errorKey` changes. Success: the success edge and a polite
 * "✓ Doğrulandı". The input widens behind the last slot when a password-manager badge shows (input-otp
 * `pushPasswordManagerStrategy`). Forced colours: ButtonBorder / Highlight.
 */
import { OTPInput, REGEXP_ONLY_DIGITS, type SlotProps } from "input-otp";
import { Check } from "lucide-react";
import { forwardRef, useEffect, useId, type ReactNode } from "react";
import { useShake } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import "./auth.css";

export type OtpState = "idle" | "error" | "success";

export interface OtpInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  onComplete?: (code: string) => void;
  state?: OtpState;
  /** the message under the slots (error text, or a note); linked with aria-describedby */
  message?: ReactNode;
  /** extra description ids (e.g. the lead sentence) */
  describedBy?: string;
  /** change it to shake the group once (each failed submit) */
  errorKey?: number;
  disabled?: boolean;
  autoFocus?: boolean;
  /** visible label; default "Doğrulama kodu" */
  label?: string;
  /** hide the visible label (the page title already names the field); the accessible name stays */
  hideLabel?: boolean;
  name?: string;
  className?: string;
  "data-testid"?: string;
}

export const OTP_LENGTH = 6;

/** Paste: keep the digits only, at most 6 ("123 456" → "123456"). */
export const otpPaste = (pasted: string) => pasted.replace(/\D+/g, "").slice(0, OTP_LENGTH);

function Slot({ slot, state }: { slot: SlotProps; state: OtpState }) {
  return (
    <div
      data-otp-slot
      data-state={state}
      data-active={slot.isActive || undefined}
      className={cn(
        "relative flex w-11 h-13 pointer-coarse:w-12 pointer-coarse:h-14 items-center justify-center rounded-[10px] bg-fill-3 shadow-(--edge-control) text-2xl font-semibold tabular-nums text-label-1",
        "forced-colors:border forced-colors:border-[ButtonBorder]",
        slot.isActive && "z-10 bg-(--mat-thick) outline-2 outline-offset-0 outline-(--focus) ring-3 ring-[color-mix(in_oklab,var(--focus)_22%,transparent)] forced-colors:outline-[Highlight]",
        state === "error" && "ring-1 ring-inset ring-(--status-infeasible-border)",
        state === "success" && "ring-1 ring-inset ring-(--status-feasible-border)",
      )}
    >
      {slot.char}
      {slot.hasFakeCaret ? (
        <span aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="auth-caret h-6 w-0.5 rounded-full bg-tint forced-colors:bg-[Highlight]" />
        </span>
      ) : null}
    </div>
  );
}

export const OtpInput = forwardRef<HTMLInputElement, OtpInputProps>(function OtpInput(
  { id, value, onChange, onComplete, state = "idle", message, describedBy, errorKey, disabled, autoFocus, label, hideLabel, name = "otp", className, "data-testid": testId },
  ref,
) {
  const { t } = useI18n();
  const auto = useId();
  const inputId = id ?? `otp-${auto}`;
  const hintId = `${inputId}-hint`;
  const msgId = `${inputId}-msg`;
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();

  useEffect(() => {
    if (errorKey && state === "error") shake();
  }, [errorKey, state, shake]);

  const described = [describedBy, hintId, message ? msgId : null].filter(Boolean).join(" ");
  return (
    <div className={cn("flex flex-col gap-1.5", className)} data-testid={testId}>
      <label htmlFor={inputId} className={cn("type-callout font-semibold text-label-1", hideLabel && "sr-only")}>
        {label ?? t("auth.otp.label")}
      </label>
      <span id={hintId} className="sr-only">
        {t("auth.otp.hint")}
      </span>
      <div ref={shakeRef} className="t-input w-fit max-w-full">
        <OTPInput
          ref={ref}
          id={inputId}
          name={name}
          value={value}
          onChange={(v) => onChange(v.replace(/\D+/g, "").slice(0, OTP_LENGTH))}
          onComplete={(code: string) => onComplete?.(code)}
          maxLength={OTP_LENGTH}
          pattern={REGEXP_ONLY_DIGITS}
          pasteTransformer={otpPaste}
          inputMode="numeric"
          autoComplete="one-time-code"
          enterKeyHint="done"
          autoFocus={autoFocus}
          disabled={disabled}
          pushPasswordManagerStrategy="increase-width"
          aria-invalid={state === "error" || undefined}
          aria-describedby={described || undefined}
          // 16 px on phones (iOS zoom); the real input is transparent over the slots
          className="text-base disabled:cursor-not-allowed"
          containerClassName="flex items-center gap-4 has-disabled:opacity-50"
          render={({ slots }) => (
            <>
              <div data-otp-group className="flex gap-2">
                {slots.slice(0, 3).map((s, i) => (
                  <Slot key={i} slot={s} state={state} />
                ))}
              </div>
              <div data-otp-group className="flex gap-2">
                {slots.slice(3).map((s, i) => (
                  <Slot key={i + 3} slot={s} state={state} />
                ))}
              </div>
            </>
          )}
        />
      </div>
      {message ? (
        <p id={msgId} className={cn("type-footnote", state === "error" ? "text-status-infeasible-fg" : "text-label-2")} data-testid={testId ? `${testId}-message` : undefined}>
          {message}
        </p>
      ) : null}
      {state === "success" ? (
        <p role="status" className="flex items-center gap-1 type-footnote font-medium text-status-feasible-fg">
          <Check aria-hidden className="auth-check size-4 stroke-[2.5]" />
          {t("auth.otp.verified")}
        </p>
      ) : null}
    </div>
  );
});
