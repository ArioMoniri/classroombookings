"use client";
/**
 * Owner decision 2026-10-17 (R1-S-37): an administrator's forced move on the published plan never edits it. The
 * server copies the active run into a new draft, applies the forced edit there and answers `draft_run_id`; the live
 * plan stays as published until the draft is published (Çalıştırmalar › taslak › Yayınla, with the forced-break tick).
 * This is the success message for that case: what happened, and a link to the draft.
 */
import Link from "next/link";
import { toast } from "sonner";
import { useI18n } from "@/lib/i18n/provider";

function DraftLink({ id }: { id: number }) {
  const { t } = useI18n();
  return (
    <Link href={`/runs/${id}`} className="inline-flex min-h-11 items-center font-medium text-tint underline underline-offset-2 md:min-h-0" data-testid="forced-draft-link">
      {t("calendar.move.draftOpen", { id })}
    </Link>
  );
}

/** The toast after a forced move went into draft `id`. */
export function toastForcedDraft(t: ReturnType<typeof useI18n>["t"], id: number): string {
  const msg = t("calendar.move.draftCreated", { id });
  toast.success(msg, { description: <DraftLink id={id} />, duration: 12000 });
  return msg;
}
