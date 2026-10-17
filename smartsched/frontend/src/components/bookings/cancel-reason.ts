/**
 * The cancel reason of a booking as the reader should see it: a person's words as typed, or a *code* the backend
 * writes (`replaced_by_series:<id>`, T-R2-17 / R2-M-18; `undo_of:<audit id>`, T-R2-31) rendered in the UI language.
 */
import type { MessageKey } from "@/lib/i18n";

type T = (key: MessageKey, values?: Record<string, string | number>) => string;

export function cancelReasonText(reason: string | null | undefined, t: T): string | null {
  if (!reason) return null;
  const series = /^replaced_by_series:(\d+)$/.exec(reason);
  if (series) return t("crbs.cancel.replacedBySeries", { id: Number(series[1]) });
  const undo = /^undo_of:(\d+)$/.exec(reason);
  if (undo) return t("wave1.audit.reasonUndoOf", { id: Number(undo[1]) });
  return reason;
}
