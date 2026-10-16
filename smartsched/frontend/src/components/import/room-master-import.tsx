"use client";
/**
 * Import wizard › Room master (ROADMAP P19-I7, admin persona M-24): upload `room_master.csv`, review the diff
 * against the stored rooms, then apply it with `POST /imports/room-master` and read the importer's report.
 *
 * The diff is computed in the browser (`room-master-model.ts`, the importer's rules); a `.xlsx` room master has
 * no preview here (its first sheet is read on the server) and goes straight to the confirm step. Values the
 * room master sets are never overwritten by a later workbook import (backend `custom_fields.master`).
 */
import { Check } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HttpError } from "@/lib/api/client";
import { useRooms } from "@/lib/api/hooks";
import type { ImportJob, Term } from "@/lib/api/schemas";
import { uploadImportWithProgress } from "@/lib/api/shell-extra";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { MagneticDrop, type UploadState } from "./magnetic-drop";
import { ParseWarningsTable } from "./parse-warnings-table";
import { diffCounts, diffRoomMaster, parseRoomMaster, type DiffRow, type DiffStatus, type MasterParse } from "./room-master-model";

const FIELD: Record<string, MessageKey> = {
  capacity: "importFlows.roomMaster.field.capacity",
  exam_capacity: "importFlows.roomMaster.field.exam_capacity",
  tags: "importFlows.roomMaster.field.tags",
  building: "importFlows.roomMaster.field.building",
  floor: "importFlows.roomMaster.field.floor",
  bookable: "importFlows.roomMaster.field.bookable",
};
const STATUS: Record<DiffStatus, MessageKey> = {
  changed: "importFlows.roomMaster.status.changed",
  same: "importFlows.roomMaster.status.same",
  unmatched: "importFlows.roomMaster.status.unmatched",
  duplicate: "importFlows.roomMaster.status.duplicate",
};

export type FlowStep = "upload" | "preview" | "done";

export function RoomMasterImport({ term, onStep, onBack }: { term: Pick<Term, "id" | "code" | "start_date"> | null; onStep: (s: FlowStep) => void; onBack: () => void }) {
  const { t, n } = useI18n();
  const qc = useQueryClient();
  const rooms = useRooms();
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<MasterParse | null>(null);
  const [readError, setReadError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadState>({ phase: "idle" });
  const [job, setJob] = useState<ImportJob | null>(null);
  const [showSame, setShowSame] = useState(false);
  const resultRef = useRef<HTMLHeadingElement>(null);
  const busy = upload.phase === "uploading" || upload.phase === "processing";
  const xlsx = !!file && /\.(xlsx|xlsm)$/i.test(file.name);
  const step: FlowStep = job ? "done" : parsed || xlsx ? "preview" : "upload";

  const diff = useMemo<DiffRow[]>(() => (parsed && rooms.data ? diffRoomMaster(parsed.rows, rooms.data) : []), [parsed, rooms.data]);
  const counts = diffCounts(diff);

  const choose = async (files: File[]) => {
    const f = files[0] ?? null;
    setReadError(null);
    setParsed(null);
    setUpload({ phase: "idle" });
    if (f && !/\.(csv|txt|xlsx|xlsm)$/i.test(f.name)) {
      setReadError(t("importFlows.roomMaster.onlyCsv"));
      setFile(null);
      return;
    }
    setFile(f);
    if (!f) return onStep("upload");
    if (/\.(xlsx|xlsm)$/i.test(f.name)) return onStep("preview");
    try {
      const buf = await f.arrayBuffer();
      let text: string;
      try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(buf);
      } catch {
        text = new TextDecoder("windows-1254").decode(buf); // Turkish Excel's "CSV" export, like the backend
      }
      setParsed(parseRoomMaster(text));
      onStep("preview");
    } catch {
      setReadError(t("importFlows.roomMaster.unreadable"));
    }
  };

  const apply = async () => {
    if (!file) return;
    // the room master is not per term; the shared upload helper still sends a term field, which the API ignores
    const target = term ?? { id: 0, code: "", start_date: "" };
    setUpload({ phase: "uploading", pct: 0 });
    try {
      const j = await uploadImportWithProgress("room-master", file, target, {
        onProgress: ({ loaded, total }) => {
          const pct = total ? Math.round((loaded / total) * 100) : 0;
          setUpload(pct >= 100 ? { phase: "processing" } : { phase: "uploading", pct });
        },
      });
      setUpload({ phase: "done" });
      setJob(j);
      onStep("done");
      void qc.invalidateQueries({ queryKey: ["rooms"] });
      void qc.invalidateQueries({ queryKey: ["imports"] });
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (e) {
      const status = e instanceof HttpError ? e.status : 0;
      setUpload({ phase: "error", message: status === 413 ? t("glass.import.tooLarge") : status === 0 ? t("glass.auth.offline") : status === 403 ? t("importFlows.roomMaster.forbidden") : status === 400 || status === 422 ? t("importFlows.roomMaster.refused") : t("glass.import.failed") });
    }
  };

  if (step === "done" && job) {
    return (
      <Card className="max-w-3xl" data-testid="room-master-result">
        <CardHeader>
          <CardTitle>
            <h2 ref={resultRef} tabIndex={-1} className="outline-hidden">
              {t("importFlows.roomMaster.applied")}
            </h2>
          </CardTitle>
          <p role="status" className="type-callout text-label-2">
            {t("importFlows.roomMaster.appliedSummary", { rows: n(job.summary.rows), updated: n(job.summary.updated), created: n(job.summary.created) })}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {job.summary.warnings.length ? <ParseWarningsTable warnings={job.summary.warnings} /> : <p className="type-callout text-label-2">{t("import.noWarnings")}</p>}
          <Button variant="outline" onClick={onBack}>{t("import.again")}</Button>
        </CardContent>
      </Card>
    );
  }

  const visible = showSame ? diff : diff.filter((d) => d.status !== "same");
  return (
    <Card className="max-w-4xl" data-testid="room-master-import">
      <CardHeader>
        <CardTitle>{t("importFlows.roomMaster.title")}</CardTitle>
        <p className="type-callout text-label-2">{t("importFlows.roomMaster.lead")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <MagneticDrop files={file ? [file] : []} onFiles={(f) => void choose(f)} upload={upload} disabled={busy} accept=".csv,.txt,.xlsx,.xlsm" title={t("importFlows.roomMaster.drop")} hint={t("importFlows.roomMaster.dropHint")} />
        {readError ? <p role="alert" className="type-callout text-status-infeasible-fg">{readError}</p> : null}

        {step === "preview" && parsed ? (
          <section aria-labelledby="rm-diff" className="space-y-3" data-testid="room-master-diff">
            <h3 id="rm-diff" className="type-body font-semibold text-label-1">{t("importFlows.roomMaster.diffTitle")}</h3>
            {rooms.isLoading ? <p className="type-callout text-label-2">{t("importFlows.roomMaster.loadingRooms")}</p> : null}
            <p className="type-callout text-label-2" role="status" data-testid="room-master-counts">
              {t("importFlows.roomMaster.counts", { changed: n(counts.changed), same: n(counts.same), unmatched: n(counts.unmatched), errors: n(parsed.errors.length) })}
            </p>
            {parsed.errors.length ? (
              <ul className="space-y-1 rounded-xl bg-status-warning/40 p-3 type-callout text-label-1" data-testid="room-master-errors">
                {parsed.errors.slice(0, 50).map((e, i) => (
                  <li key={i}>
                    {e.line ? `${t("importFlows.roomMaster.line", { line: e.line })}: ` : null}
                    {e.message}
                    {e.value ? ` (${e.value})` : null}
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="overflow-x-auto rounded-xl edge-hairline">
              <table className="w-full min-w-[560px] text-left type-callout">
                <caption className="sr-only">{t("importFlows.roomMaster.diffTitle")}</caption>
                <thead className="type-footnote text-label-3">
                  <tr className="hairline-b">
                    <th scope="col" className="px-3 py-2 font-medium">{t("importFlows.roomMaster.colLine")}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t("importFlows.roomMaster.colRoom")}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t("importFlows.roomMaster.colStatus")}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t("importFlows.roomMaster.colChanges")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.slice(0, 400).map((d) => (
                    <tr key={d.line} className="align-top [&:not(:last-child)]:hairline-b" data-testid={`rm-row-${d.status}`}>
                      <td className="px-3 py-2 text-label-3 tabular-nums">{d.line}</td>
                      <td className="px-3 py-2 font-medium text-label-1">{d.room?.display_name ?? d.code}</td>
                      <td className="px-3 py-2">
                        <span className={cn("inline-flex h-5 items-center rounded-full px-2 type-caption font-medium", d.status === "changed" ? "bg-tint-soft text-tint-text" : d.status === "unmatched" ? "bg-status-warning text-status-warning-fg" : "bg-fill-2 text-label-2")}>{t(STATUS[d.status])}</span>
                      </td>
                      <td className="px-3 py-2 text-label-2">
                        {d.changes.length ? (
                          <ul className="space-y-0.5">
                            {d.changes.map((c) => (
                              <li key={c.field}>
                                <span className="text-label-3">{t(FIELD[c.field]!)}:</span> <span className="line-through decoration-label-3">{c.from}</span> → <span className="font-medium text-label-1">{c.to}</span>
                              </li>
                            ))}
                          </ul>
                        ) : d.status === "unmatched" ? (
                          t("importFlows.roomMaster.unmatchedHint")
                        ) : d.status === "duplicate" ? (
                          t("importFlows.roomMaster.duplicateHint")
                        ) : (
                          "–"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {counts.same ? (
              <Button variant="ghost" size="sm" onClick={() => setShowSame((v) => !v)} aria-pressed={showSame}>
                {showSame ? t("importFlows.roomMaster.hideSame") : t("importFlows.roomMaster.showSame", { n: n(counts.same) })}
              </Button>
            ) : null}
          </section>
        ) : null}
        {step === "preview" && xlsx ? <p className="type-callout text-label-2" data-testid="room-master-xlsx">{t("importFlows.roomMaster.xlsxNoPreview")}</p> : null}

        <div className="flex items-center justify-between gap-2">
          <Button variant="ghost" onClick={onBack} disabled={busy}>{t("common.back")}</Button>
          <Button onClick={() => void apply()} {...busyProps(busy, step !== "preview" || (!!parsed && parsed.rows.length === 0))} data-testid="room-master-apply">
            <BusyLabel busy={busy} label={upload.phase === "processing" ? t("glass.import.reading") : t("import.importing")} icon={<Check aria-hidden />}>
              {t("importFlows.roomMaster.apply")}
            </BusyLabel>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
