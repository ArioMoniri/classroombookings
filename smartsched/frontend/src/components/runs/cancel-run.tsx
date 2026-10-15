"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Square } from "lucide-react";
import { toast } from "sonner";
import { BusyButton } from "@/components/ui/busy-label";
import { HttpError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { qk } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";

/** Stop a QUEUED / RUNNING run (`POST /runs/{id}/cancel` → CANCELLED). The run and its audit stay. */
export function CancelRunButton({ runId, className }: { runId: number; className?: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.runs.cancel(runId),
    onSuccess: () => toast.success(t("runs.cancelled")),
    onError: (e) => toast.error(t("runs.cancelFailed"), { description: e instanceof HttpError ? e.message : undefined }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: qk.run(runId) });
      void qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  return (
    <BusyButton size="sm" variant="outline" className={className} busy={cancel.isPending} busyLabel={t("runs.cancelling")} icon={<Square aria-hidden />} onClick={() => cancel.mutate()} data-testid="run-cancel">
      {" "}{t("runs.cancelRun")}
    </BusyButton>
  );
}
