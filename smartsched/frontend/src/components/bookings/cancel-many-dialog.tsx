"use client";
/** Cancel several bookings at once (CRBS `cancel_multi`): from /my-bookings and from the grid's multi-select. */
import { useState } from "react";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import { BOOKING_KEYS, crbs, crbsError, useCrbsMutation } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, ConfirmDialog, Field } from "@/components/admin/kit";
import { bookingErrorMessage } from "./booking-errors";

export function CancelManyDialog({ ids, open, onOpenChange, onDone, description }: { ids: number[]; open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void; description?: string }) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const m = useCrbsMutation(() => crbs.bookings.cancelMany(ids, reason.trim() || null), BOOKING_KEYS);
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("crbs.mine.cancelManyTitle", { n: ids.length })}
      description={description ?? t("crbs.mine.cancelManyBody")}
      confirmLabel={t("crbs.cancel.confirm")}
      destructive
      busy={m.isPending}
      onConfirm={() =>
        m.mutate(undefined, {
          onSuccess: (res) => {
            toast.success(t("crbs.mine.cancelManyDone", { n: res.cancelled.length, skipped: res.skipped.length }));
            setReason("");
            onDone();
          },
          onError: (e) => setError(bookingErrorMessage(crbsError(e), t)),
        })
      }
    >
      <Field label={t("crbs.cancel.reason")} htmlFor="cancel-many-reason" hint={t("crbs.cancel.reasonHint")}>
        <Textarea id="cancel-many-reason" rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </ConfirmDialog>
  );
}
