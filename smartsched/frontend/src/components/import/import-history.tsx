"use client";
/**
 * RF-08: the import history on /import. Each row says who imported (a person's name, "İlk kurulum (sistem)" for the
 * deploy seed, "Sistem (komut satırı)" for a CLI import), whether it was a preview and if it was applied, opens the
 * report (counts, the reason of a failed job, the skipped rows and warnings) and downloads the workbook
 * (`GET /imports/{id}/file`, planners only; a failed CLI job has no file).
 */
import { ChevronDown, Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { importPreviewApi } from "@/lib/api/rf-admin";
import type { ImportJob } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { ParseWarningsTable, TruncatedWarnings } from "./parse-warnings-table";

const KIND_LABEL: Record<string, MessageKey> = {
  "planning-list": "import.planning",
  "exam-list": "import.exam",
  "weekly-grid": "import.grid",
  "room-master": "importFlows.roomMaster.kind",
  crbs: "import.crbs",
};

/** who imported, in plain words */
export function actorText(job: ImportJob, t: ReturnType<typeof useI18n>["t"]): string {
  if (job.source === "seed") return t("rf.history.seed");
  if (job.source === "cli") return t("rf.history.cli");
  if (job.created_by_name) return t("rf.history.by", { name: job.created_by_name });
  if (job.actor === "system") return t("rf.history.system");
  return t("rf.history.unknown");
}

export function ImportHistory({ jobs, onOpenPreview, limit = 8 }: { jobs: ImportJob[]; onOpenPreview?: (job: ImportJob) => void; limit?: number }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState<number | null>(null);
  // E2EA-F05: older jobs (the seed imports among them) stay reachable, one step of `limit` at a time
  const [shown, setShown] = useState(limit);
  const focusId = useRef<number | null>(null);
  useEffect(() => {
    if (focusId.current == null) return;
    document.querySelector<HTMLElement>(`[data-testid="import-history-report-${focusId.current}"]`)?.focus();
    focusId.current = null;
  }, [shown]);
  const rest = jobs.length - shown;
  const when = new Intl.DateTimeFormat(locale, { timeZone: "Europe/Istanbul", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  if (!jobs.length) return null;
  return (
    <Card className="mt-6 max-w-3xl" data-testid="import-history">
      <CardHeader>
        <CardTitle>
          <h2>{t("rf.history.title")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="type-callout">
          {jobs.slice(0, shown).map((j) => {
            const preview = Boolean(j.summary.dry_run);
            const failed = j.status === "FAILED";
            const running = j.status === "QUEUED" || j.status === "RUNNING";
            const date = new Date(j.created_at);
            const isOpen = open === j.id;
            const tag = failed ? t("rf.history.failed") : running ? t("rf.history.running") : preview ? (j.summary.applied_job_id ? t("rf.history.previewApplied") : t("rf.history.preview")) : j.summary.preview_of ? t("rf.history.fromPreview") : null;
            return (
              <li key={j.id} className="py-2.5 [&:not(:last-child)]:hairline-b" data-testid={`import-history-${j.id}`}>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-label-1">{j.filename || t(KIND_LABEL[j.kind] ?? "import.title")}</p>
                    <p className="type-footnote text-label-2">
                      {[t(KIND_LABEL[j.kind] ?? "import.title"), actorText(j, t), Number.isNaN(date.getTime()) ? null : when.format(date)].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  {tag ? (
                    <span className={cn("inline-flex h-6 shrink-0 items-center rounded-full px-2 type-caption font-medium", failed ? "bg-status-infeasible text-status-infeasible-fg" : "bg-fill-2 text-label-2")}>{tag}</span>
                  ) : null}
                  <div className="flex shrink-0 items-center gap-1">
                    {preview && !j.summary.applied_job_id && j.status === "DONE" && onOpenPreview ? (
                      <Button variant="outline" size="sm" className="pointer-coarse:h-11" onClick={() => onOpenPreview(j)} data-testid={`import-history-open-${j.id}`}>
                        {t("rf.preview.open")}
                      </Button>
                    ) : null}
                    <Button variant="ghost" size="sm" className="pointer-coarse:h-11" aria-expanded={isOpen} aria-controls={`import-history-detail-${j.id}`} aria-label={t("rf.history.reportNamed", { name: j.filename })} onClick={() => setOpen(isOpen ? null : j.id)} data-testid={`import-history-report-${j.id}`}>
                      <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", isOpen && "rotate-180")} />
                      {t("rf.history.report")}
                    </Button>
                    {!failed && !running ? (
                      <a href={importPreviewApi.fileUrl(j.id)} download className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "pointer-coarse:h-11")} aria-label={`${t("rf.history.download")}: ${j.filename}`} data-testid={`import-history-download-${j.id}`}>
                        <Download aria-hidden />
                        {t("rf.history.download")}
                      </a>
                    ) : null}
                  </div>
                </div>
                {isOpen ? <HistoryDetail job={j} /> : null}
              </li>
            );
          })}
        </ul>
        {rest > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 pointer-coarse:h-11"
            onClick={() => {
              focusId.current = jobs[shown]?.id ?? null;
              setShown(shown + limit);
            }}
            data-testid="import-history-more"
          >
            {t("rf.history.more", { n: rest })}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function HistoryDetail({ job }: { job: ImportJob }) {
  const { t, n } = useI18n();
  return (
    <div id={`import-history-detail-${job.id}`} className="mt-2 space-y-3 rounded-xl bg-fill-3 p-3" data-testid={`import-history-detail-${job.id}`}>
      {job.error ? <p className="type-callout text-status-infeasible-fg">{t("rf.history.error", { error: job.error })}</p> : null}
      <p className="type-callout text-label-1 tabular-nums">
        {t("rf.history.counts", { rows: n(job.summary.rows), created: n(job.summary.created), updated: n(job.summary.updated), skipped: n(job.summary.skipped) })}
      </p>
      <TruncatedWarnings summary={job.summary} />
      {job.summary.warnings.length ? <ParseWarningsTable warnings={job.summary.warnings} groups={job.summary.warning_groups} /> : <p className="type-footnote text-label-2">{t("rf.history.noWarnings")}</p>}
    </div>
  );
}
