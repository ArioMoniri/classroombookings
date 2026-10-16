"use client";
/**
 * Reject an approval request (owner requirement 2026-10-15: the admin "puts reasons why they didn't"; F-01 S08).
 *
 * - A required reason code (radio rows ≥ 44 px: Oda uygun değil / Kapasite yetersiz / Rezervasyon kurallarına
 *   uygun değil / Diğer; backend `REASON_CODES`) and a required written reason ("Gerekçe", spaces and NBSP count
 *   as blank) with a character counter. Nothing is sent until both are there: the confirm is `aria-disabled`, and
 *   pressing it anyway shows the Turkish / English message next to the field that is missing (not only an outline).
 * - One dialog for one period, for a whole submission ("{n} saatin hepsini reddet", A-12) and for "reject and
 *   suggest another room" (the suggestion is named in the dialog).
 * - Desktop: a dialog; phone: a bottom sheet with the confirm in the sticky footer (MOBILE.md M-04, M-05, M-12).
 */
import { useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Textarea } from "@/components/ui/textarea";
import { REASON_CODES, REASON_MAX, type ReasonCode } from "@/lib/api/approval-first";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { rejectProblems } from "./approvals-model";
import { ResponsiveDialog } from "./responsive-dialog";

export interface RejectReason {
  reason_code: ReasonCode;
  reason: string;
}

export function RejectDialog({
  open,
  onOpenChange,
  room,
  count = 1,
  suggestion,
  initialText = "",
  busy = false,
  error,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  room: string;
  /** periods of the submission rejected together (A-12); 1 = this request only */
  count?: number;
  /** "reject and suggest": the room offered instead */
  suggestion?: string | null;
  /** the "Talep edene not" draft, carried over */
  initialText?: string;
  busy?: boolean;
  /** the backend's refusal, in the user's language */
  error?: string | null;
  onConfirm: (reason: RejectReason) => void;
}) {
  const { t } = useI18n();
  const [code, setCode] = useState<ReasonCode | null>(null);
  const [text, setText] = useState(initialText);
  const [tried, setTried] = useState(false);
  // a fresh draft every time the dialog opens (the note typed in the drawer is carried over)
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setCode(null);
      setText(initialText);
      setTried(false);
    }
  }
  const textRef = useRef<HTMLTextAreaElement>(null);
  const base = useId();
  const formId = `${base}-form`;
  const problems = rejectProblems({ code, text }, REASON_MAX);
  const invalid = Boolean(problems.code || problems.text);
  const codeErr = tried && problems.code ? t("approvals.reject.codeRequired") : null;
  const textErr = tried && problems.text ? t(problems.text === "tooLong" ? "approvals.reject.textTooLong" : "approvals.reject.textRequired", { max: REASON_MAX }) : null;
  const submit = () => {
    if (busy) return;
    if (invalid || !code) {
      setTried(true);
      // the first missing field gets focus, so a keyboard / screen-reader user hears the message
      if (problems.code) document.getElementById(`${base}-${REASON_CODES[0]}`)?.focus();
      else textRef.current?.focus();
      return;
    }
    onConfirm({ reason_code: code, reason: text.trim() });
  };
  const left = REASON_MAX - text.length;
  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={(o) => !busy && onOpenChange(o)}
      title={count > 1 ? t("approvals.reject.titleGroup", { n: count }) : t("approvals.reject.title", { room })}
      description={t("approvals.reject.lead")}
      testId="reject-dialog"
      footer={
        <>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("crbs.common.cancel")}
          </Button>
          <Button type="submit" form={formId} variant="destructive" aria-disabled={invalid || busy || undefined} aria-busy={busy || undefined} className="aria-disabled:opacity-45" data-testid="reject-confirm">
            <BusyLabel busy={busy} label={t("busy.rejecting")}>
              {count > 1 ? t("approvals.reject.confirmGroup", { n: count }) : t("approvals.reject.confirm")}
            </BusyLabel>
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {suggestion ? (
          <p className="rounded-xl bg-fill-3 px-3 py-2 type-callout text-label-1" data-testid="reject-suggestion">
            {t("approvals.reject.suggesting", { room: suggestion })}
          </p>
        ) : null}
        <fieldset aria-describedby={codeErr ? `${base}-code-err` : undefined} className="flex min-w-0 flex-col gap-1">
          <legend className="mb-1.5 type-headline text-label-1">
            {t("approvals.reject.codeLabel")} <span className="type-footnote font-normal text-label-3">{t("approvals.reject.required")}</span>
          </legend>
          <div role="radiogroup" aria-required="true" aria-invalid={codeErr ? true : undefined} aria-label={t("approvals.reject.codeLabel")} className="flex flex-col overflow-hidden rounded-xl bg-fill-3" data-testid="reject-codes">
            {REASON_CODES.map((c) => (
              <label
                key={c}
                htmlFor={`${base}-${c}`}
                className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 type-callout text-label-1 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none has-checked:bg-tint-soft has-focus-visible:outline-2 has-focus-visible:-outline-offset-2 has-focus-visible:outline-(--focus)"
                data-testid={`reject-code-${c}`}
              >
                <input id={`${base}-${c}`} type="radio" name={`${base}-code`} value={c} checked={code === c} onChange={() => setCode(c)} className="size-4 shrink-0 accent-(--accent) outline-hidden" />
                {t(`approvals.reasons.${c}`)}
              </label>
            ))}
          </div>
          {codeErr ? (
            <p id={`${base}-code-err`} role="alert" className="type-footnote text-status-infeasible-fg" data-testid="reject-code-error">
              {codeErr}
            </p>
          ) : null}
        </fieldset>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${base}-text`} className="type-headline text-label-1">
            {t("approvals.reject.textLabel")} <span className="type-footnote font-normal text-label-3">{t("approvals.reject.required")}</span>
          </label>
          <Textarea
            id={`${base}-text`}
            ref={textRef}
            rows={3}
            maxLength={REASON_MAX}
            value={text}
            onChange={(e) => setText(e.target.value)}
            // the phone keyboard pushes the sheet up: keep the field above it (M-12)
            onFocus={(e) => {
              const el = e.currentTarget;
              window.setTimeout(() => el.scrollIntoView?.({ block: "nearest" }), 300);
            }}
            placeholder={t("approvals.reject.textPlaceholder")}
            aria-required="true"
            aria-invalid={textErr ? true : undefined}
            aria-describedby={`${base}-count${textErr ? ` ${base}-text-err` : ""}`}
            className="text-base sm:text-[13px]"
            data-testid="reject-text"
          />
          <div className="flex items-start justify-between gap-3">
            {textErr ? (
              <p id={`${base}-text-err`} role="alert" className="type-footnote text-status-infeasible-fg" data-testid="reject-text-error">
                {textErr}
              </p>
            ) : (
              <span className="type-footnote text-label-3">{t("approvals.reject.textHint")}</span>
            )}
            <span id={`${base}-count`} className={cn("shrink-0 type-caption tabular-nums", left < 50 ? "text-status-warning-fg" : "text-label-3")} aria-live={left < 50 ? "polite" : "off"} data-testid="reject-count">
              {t("approvals.reject.counter", { n: text.length, max: REASON_MAX })}
            </span>
          </div>
        </div>
        {error ? (
          <p role="alert" className="rounded-xl bg-status-infeasible px-3 py-2 type-callout text-status-infeasible-fg" data-testid="reject-error">
            {error}
          </p>
        ) : null}
      </form>
    </ResponsiveDialog>
  );
}
