"use client";
/**
 * The recovery-code field (docs/design/v3/auth.md §5.3, §10.3; AUX-02): one text field, monospace, capital letters
 * on phones (`autocapitalize=characters`), no autocorrect or spellcheck; the value is normalised as it is typed or
 * pasted (case, spaces and hyphens ignored, O → 0, I/L → 1, `XXXX-XXXX-XXXX-XXXX`), like the backend (AU-B §4).
 * No automatic submit: the person checks the code and presses "Doğrula".
 */
import { forwardRef, useId, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { normalizeRecoveryCode } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export interface RecoveryCodeFieldProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
  message?: ReactNode;
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
  "data-testid"?: string;
}

export const RecoveryCodeField = forwardRef<HTMLInputElement, RecoveryCodeFieldProps>(function RecoveryCodeField({ id, value, onChange, invalid, message, disabled, autoFocus, className, "data-testid": testId }, ref) {
  const { t } = useI18n();
  const auto = useId();
  const inputId = id ?? `rc-${auto}`;
  const hintId = `${inputId}-hint`;
  const msgId = `${inputId}-msg`;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="type-callout font-semibold text-label-1">
        {t("auth.recovery.label")}
      </label>
      <p id={hintId} className="type-footnote text-label-2">
        {t("auth.recovery.hint")}
      </p>
      <Input
        ref={ref}
        id={inputId}
        name="recovery_code"
        fieldSize="lg"
        value={value}
        onChange={(e) => onChange(normalizeRecoveryCode(e.target.value))}
        autoComplete="off"
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        enterKeyHint="go"
        maxLength={24}
        placeholder="XXXX-XXXX-XXXX-XXXX"
        disabled={disabled}
        autoFocus={autoFocus}
        aria-invalid={invalid || undefined}
        aria-describedby={[hintId, message ? msgId : null].filter(Boolean).join(" ")}
        className="font-mono tracking-wider pointer-coarse:h-12"
        data-testid={testId}
      />
      {message ? (
        <p id={msgId} className={cn("type-footnote", invalid ? "text-status-infeasible-fg" : "text-label-2")}>
          {message}
        </p>
      ) : null}
    </div>
  );
});
