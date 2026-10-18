"use client";
/**
 * E2EA-F11 / E2EA2-F07 (FIX-K): "Öğrenci sayısı" in the class inspector, so a phone (no grid cell) and the exam side
 * (no other screen wrote an exam's head count) can change it. A − / + stepper (44 px on touch) around a numeric
 * input (16 px on touch) and one "Kaydet"; the value is the request's (PUT /requests/meetings|exams/{id}) and takes
 * effect on the next run, like the desktop grid cell.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Minus, Plus } from "lucide-react";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Button, IconButton } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import type { ClassKind } from "@/lib/api/classes";
import { api } from "@/lib/api/endpoints";
import { serverMessage } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";

const TOUCH = "pointer-coarse:min-h-11 pointer-coarse:min-w-11";

export function EnrolmentField({ kind, requestId, value, readOnly = false }: { kind: ClassKind; requestId: number; value: number | null | undefined; readOnly?: boolean }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState(value == null ? "" : String(value));
  const [saved, setSaved] = useState(value ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const parsed = text.trim() === "" ? null : Number(text.trim());
  const valid = parsed === null || (Number.isInteger(parsed) && parsed >= 0);
  const dirty = parsed !== saved;
  const step = (d: 1 | -1) => {
    const base = valid && parsed !== null ? parsed : (saved ?? 0);
    setText(String(Math.max(0, base + d)));
    setError(null);
  };
  const save = async () => {
    if (!valid) {
      setError(t("classes.insp.enrolmentBad"));
      inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (kind === "exams") await api.requests.updateExam(requestId, { enrolment: parsed });
      else await api.requests.updateMeeting(requestId, { enrolment: parsed });
      setSaved(parsed);
      toast.success(t("classes.edit.saved"), { description: t("classes.edit.nextRun"), duration: 3000 });
      void qc.invalidateQueries({ queryKey: ["classes"] });
      void qc.invalidateQueries({ queryKey: ["requests"] });
    } catch (e) {
      setError(serverMessage(e, locale) ?? t("classes.edit.failed", { reason: "" }));
    } finally {
      setBusy(false);
      // Kaydet disables itself once the value is saved: focus stays on the field (never <body>)
      inputRef.current?.focus();
    }
  };
  if (readOnly) return null;
  return (
    <div className="flex flex-col gap-1" data-testid="inspector-enrolment">
      <label htmlFor={`${id}-n`} className="type-footnote text-label-2">
        {t("classes.insp.enrolment")}
      </label>
      <div className="flex items-center gap-1.5">
        <IconButton variant="outline" size="sm" className={TOUCH} label={t("classes.insp.enrolmentLess")} onClick={() => step(-1)} disabled={busy}>
          <Minus aria-hidden />
        </IconButton>
        <Input
          ref={inputRef}
          id={`${id}-n`}
          inputMode="numeric"
          autoComplete="off"
          value={text}
          onChange={(e) => (setText(e.target.value), setError(null))}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void save();
            }
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-err` : undefined}
          className="w-20 text-center tabular-nums pointer-coarse:min-h-11"
        />
        <IconButton variant="outline" size="sm" className={TOUCH} label={t("classes.insp.enrolmentMore")} onClick={() => step(1)} disabled={busy}>
          <Plus aria-hidden />
        </IconButton>
        <Button size="sm" className="pointer-coarse:h-11" onClick={() => void save()} {...busyProps(busy, !dirty)} focusableWhenDisabled>
          <BusyLabel busy={busy} label={t("busy.saving")}>
            {t("classes.insp.enrolmentSave")}
          </BusyLabel>
        </Button>
      </div>
      {error ? (
        <p id={`${id}-err`} role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
