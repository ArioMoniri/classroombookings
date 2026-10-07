"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { useContextRun } from "@/components/rooms/use-room-occupancy";
import { useRuns } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { Timetable } from "./timetable";

export function TimetablePage() {
  const { t } = useI18n();
  const params = useSearchParams();
  const runs = useRuns();
  const contextRun = useContextRun();
  const [runId, setRunId] = useState<number | null>(null);
  const effective = runId ?? contextRun;
  const finished = (runs.data ?? []).filter((r) => r.status !== "QUEUED" && r.status !== "RUNNING" && r.status !== "FAILED");
  return (
    <div className="flex min-h-[calc(100dvh-120px)] flex-col">
      <PageHeader
        title={t("grid.title")}
        actions={
          <NativeSelect aria-label={t("runs.run")} value={effective ?? ""} onChange={(e) => setRunId(Number(e.target.value))} className="w-64">
            {finished.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.term_code} · {t(`runs.status.${r.status}`)} · {r.hard_score ?? "—"}/100</option>)}
          </NativeSelect>
        }
      />
      {effective !== null ? (
        <Timetable runId={effective} week={params.get("week") ? Number(params.get("week")) : undefined} day={params.get("day") ? Number(params.get("day")) : undefined} zoom={params.get("zoom") === "week" ? "week" : "day"} className="min-h-0 flex-1" />
      ) : (
        <p className="text-sm text-muted-foreground">{t("grid.emptyRun")}</p>
      )}
    </div>
  );
}
