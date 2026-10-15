"use client";
/**
 * The memory reset confirm (phase19-suggestions.md §6, motion.md §3.10 memory.reset-confirm): an alertdialog that
 * quotes the subject and states what is deleted and what is kept, a required reason, and for "Tümü" the typed
 * word SIFIRLA (or RESET; Turkish-aware casefold). A wrong word on Enter shakes the field once. A reset can be
 * undone for 30 days; the KVKK erasure variant deletes immediately and cannot be undone. planning.admin only.
 */
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Input, useShake } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { HttpError } from "@/lib/api/client";
import { useMemoryActions, type ResetRow, type ResetScope } from "@/lib/api/learning";
import { useI18n } from "@/lib/i18n/provider";
import { reasonOk, typedConfirmOk } from "./learning-model";

export function ResetDialog({ open, onOpenChange, scope, subject, onDone }: { open: boolean; onOpenChange: (v: boolean) => void; scope: ResetScope | "erase"; subject?: { id: number; label: string }; onDone?: (r: ResetRow) => void }) {
  const { t } = useI18n();
  const { reset, erase, undo } = useMemoryActions();
  const [reason, setReason] = useState("");
  const [word, setWord] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const { ref: wordRef, shake } = useShake<HTMLInputElement>();
  const needsWord = scope === "all" || scope === "erase";
  const ready = reasonOk(reason) && (!needsWord || typedConfirmOk(word)) && (scope === "all" || subject !== undefined);
  const busy = reset.isPending || erase.isPending;
  const label = subject?.label ?? "";

  const submit = async () => {
    if (needsWord && !typedConfirmOk(word)) {
      shake();
      setError(t("learning.reset.wrongWord"));
      return;
    }
    if (!ready) return;
    setError(null);
    try {
      const out = scope === "erase" ? await erase.mutateAsync({ instructorId: subject!.id, reason: reason.trim() }) : await reset.mutateAsync({ scope, value: scope === "all" ? null : subject!.id, reason: reason.trim() });
      onOpenChange(false);
      onDone?.(out);
      if (scope === "erase") toast.success(t("learning.erase.done", { label }));
      else
        // destructive: the undo stays 10 s (motion.md §3.10 memory.reset-done)
        toast.success(t("learning.reset.done"), { duration: 10_000, action: { label: t("common.undo"), onClick: () => void undo.mutateAsync(out.id).then(() => toast.success(t("learning.reset.undone"))) } });
    } catch (e) {
      setError(e instanceof HttpError ? e.message : String(e));
    }
  };

  const title = scope === "erase" ? t("learning.erase.title", { label }) : scope === "all" ? t("learning.reset.allTitle") : scope === "term" ? t("learning.reset.termTitle", { label }) : t("learning.reset.personTitle", { label });
  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={onOpenChange}
      alert
      initialFocus={reasonRef}
      title={title}
      description={scope === "erase" ? t("learning.erase.body") : t(scope === "term" ? "learning.reset.termBody" : "learning.reset.body")}
      testId="reset-dialog"
      footer={
        <>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button type="button" variant="destructive" onClick={() => void submit()} disabled={busy || !reasonOk(reason)} data-testid="reset-confirm" aria-busy={busy || undefined}>
            {busy ? t("busy.working") : scope === "erase" ? t("learning.erase.go") : t("learning.reset.go")}
          </Button>
        </>
      }
    >
      <p className="type-footnote text-label-2">{scope === "erase" ? t("learning.erase.kept") : t("learning.reset.kept")}</p>
      <p className="type-footnote text-label-2">{scope === "erase" ? t("learning.erase.noUndo") : t("learning.reset.undoWindow")}</p>
      <label className="flex flex-col gap-1">
        <span className="type-footnote font-semibold">{t("learning.reset.reason")}</span>
        <Textarea ref={reasonRef} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} required data-testid="reset-reason" />
      </label>
      {needsWord ? (
        <label className="flex flex-col gap-1">
          <span className="type-footnote font-semibold">{t("learning.reset.typeWord")}</span>
          <Input ref={wordRef} className="t-input" value={word} onChange={(e) => setWord(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void submit(); } }} autoComplete="off" aria-invalid={word.length > 0 && !typedConfirmOk(word) ? true : undefined} data-testid="reset-word" />
        </label>
      ) : null}
      {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
    </ResponsiveDialog>
  );
}
