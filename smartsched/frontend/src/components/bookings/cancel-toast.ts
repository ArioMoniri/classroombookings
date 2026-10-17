/**
 * T-R2-16 (R2-S-22, R2-A-07 family): one wording for every cancel outcome, whatever the entry point (grid cell
 * sheet, My bookings row sheet, the bulk bar): "N rezervasyon iptal edildi", "· Gerekçe: …" when one was given,
 * "· N olduğu gibi kaldı" only when the bulk cancel really skipped some.
 */
import type { MessageKey } from "@/lib/i18n";

type T = (key: MessageKey, values?: Record<string, string | number>) => string;

export function cancelToastText(t: T, cancelled: number, opts: { reason?: string | null; skipped?: number } = {}): string {
  const reason = opts.reason?.trim() || null;
  let text = reason ? t("crbs.cancel.doneReason", { n: cancelled, reason }) : t("crbs.cancel.done", { n: cancelled });
  if (opts.skipped) text += ` · ${t("crbs.cancel.kept", { n: opts.skipped })}`;
  return text;
}
