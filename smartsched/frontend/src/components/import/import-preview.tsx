"use client";
/**
 * RF-06: the preview of a workbook import (`dry_run=true`, rf-b API.md §2). Nothing is written until "Uygula"
 * (`POST /imports/{id}/apply`, once). The diff reads in plain words: what is added, what changes, which of the
 * person's own edits are kept and where their edit and the file disagree (conflicts first, with "Sizin değeriniz /
 * Dosyadaki / Önceki içe aktarma"). The keep / take choice sits under "Gelişmiş" ("Düzenlemelerimi koru" default).
 * A refusal (already applied, file gone, term locked, …) is shown at the button in the server's words.
 */
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { serverMessage } from "@/lib/api/error-text";
import { diffTotals, importDiff, importPreviewApi, type ImportDiffRow, type OnConflict } from "@/lib/api/rf-admin";
import type { ImportJob } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { ParseWarningsTable, TruncatedWarnings } from "./parse-warnings-table";
import type { TermMismatch } from "./term-hint";

const ENTITIES = ["exam_requests", "meeting_requests", "sections", "rooms", "programs", "courses", "instructors", "constraints", "weeks", "blocks", "faculties"] as const;
const FIELDS = [
  "enrolment", "capacity", "exam_capacity", "archived", "name", "full_name", "title", "email", "label", "kind", "start_date", "date", "duration", "duration_min",
  "instructor_id", "room_id", "tags", "hardness", "params", "nl_text", "code", "weekly_hours", "class_year", "program_id", "course_id", "section_id", "period",
  "start_period", "building_id", "floor", "is_bookable", "enabled", "weight", "faculty_id", "is_evening", "t_hours", "u_hours", "l_hours", "credits", "ects",
  "status", "notes", "day", "week", "group",
] as const;

export function entityLabelKey(entity: string): MessageKey {
  return (ENTITIES as readonly string[]).includes(entity) ? (`rf.preview.entity.${entity}` as MessageKey) : "rf.preview.entity.other";
}
function fieldLabelKey(field: string | null | undefined): MessageKey {
  return field && (FIELDS as readonly string[]).includes(field) ? (`rf.preview.field.${field}` as MessageKey) : "rf.preview.otherField";
}

/** kinds whose apply takes `on_conflict` (planning and exam lists) */
const CONFLICT_KINDS = new Set(["planning-list", "exam-list"]);

export function ImportPreview({ job, onApplied, onCancel, termWarning = null }: { job: ImportJob; onApplied: (applied: ImportJob) => void; onCancel: () => void; /** PER-F04: the file names another term than the target */ termWarning?: TermMismatch | null }) {
  const { t, n, locale } = useI18n();
  const diff = importDiff(job);
  const [choice, setChoice] = useState<OnConflict>(diff?.on_conflict === "take" ? "take" : "keep");
  const [advanced, setAdvanced] = useState(false);
  const [showRows, setShowRows] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [termOk, setTermOk] = useState(false);
  const termBlocked = !!termWarning && !termOk;
  const errorRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // the preview replaces the upload card: focus moves to its heading, never to <body>
  useEffect(() => headingRef.current?.focus(), []);
  const advId = useId();
  const rowsId = useId();
  const warnId = useId();
  const applied = Boolean(job.summary.applied_job_id);
  const totals = diff ? diffTotals(diff) : null;
  const conflicts = (diff?.rows ?? []).filter((r) => r.change === "conflict");
  const others = (diff?.rows ?? []).filter((r) => r.change !== "conflict");
  const rebuilt = { from_audit: job.summary.rebuilt_import_values?.from_audit ?? 0, edited_unknown: job.summary.rebuilt_import_values?.edited_unknown ?? 0 };
  const warnings = job.summary.warnings_count ?? job.summary.warnings.length;
  const canChoose = CONFLICT_KINDS.has(job.kind) && (diff?.conflicts_total ?? 0) > 0;
  const original: OnConflict = diff?.on_conflict === "take" ? "take" : "keep";

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      // null: the preview's own choice; only a changed choice is sent
      const out = await importPreviewApi.apply(job.id, canChoose && choice !== original ? choice : null);
      onApplied(out);
    } catch (e) {
      setError(serverMessage(e, locale) ?? t("glass.import.failed"));
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  };

  const sentence = (key: MessageKey, value: number) => (value > 0 ? <li key={key}>{t(key, { n: n(value) })}</li> : null);
  const changes = totals ? totals.create + totals.update + totals.conflict : 0;

  return (
    <Card className="max-w-4xl" data-testid="import-preview">
      <CardHeader>
        <CardTitle>
          <h2 ref={headingRef} tabIndex={-1} className="outline-hidden">
            {t("rf.preview.title", { name: job.filename })}
          </h2>
        </CardTitle>
        <p className="type-callout text-label-2">{applied ? t("rf.preview.applied") : t("rf.preview.lead")}</p>
      </CardHeader>
      <CardContent className="space-y-5">
        {termWarning && !applied ? (
          <Alert tone="warning" data-testid="import-term-mismatch" title={termWarning.likely ? t("rf.preview.termMismatch", { file: termWarning.likely.name, target: termWarning.target }) : t("rf.preview.termMismatchUnknown", { target: termWarning.target })}>
            <p>{t("rf.preview.termMismatchHint")}</p>
            <label className="mt-2 flex min-h-11 cursor-pointer items-center gap-3">
              <input type="checkbox" checked={termOk} onChange={(e) => setTermOk(e.target.checked)} className="size-4 accent-(--tint)" data-testid="import-term-confirm" />
              <span className="type-callout font-medium">{t("rf.preview.termConfirm", { target: termWarning.target })}</span>
            </label>
          </Alert>
        ) : null}
        {diff && totals ? (
          <>
            <ul className="space-y-1 type-body text-label-1" data-testid="import-preview-summary" aria-live="polite">
              {changes === 0 ? <li>{t("rf.preview.nothing")}</li> : null}
              {sentence("rf.preview.created", totals.create)}
              {sentence("rf.preview.updated", totals.update)}
              {sentence(choice === "take" && canChoose ? "rf.preview.taken" : "rf.preview.kept", totals.conflict)}
              {sentence("rf.preview.unchanged", totals.unchanged)}
            </ul>
            <ul className="divide-y divide-hairline rounded-xl edge-hairline">
              {Object.entries(diff.counts).map(([entity, c]) => (
                <li key={entity} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-3 py-2 type-callout" data-testid={`import-preview-entity-${entity}`}>
                  <span className="font-medium text-label-1">{t(entityLabelKey(entity))}</span>
                  <span className="text-label-2 tabular-nums">{t("rf.preview.entityLine", { created: n(c.create), updated: n(c.update), conflict: n(c.conflict), unchanged: n(c.unchanged) })}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="type-callout text-label-2">{t("rf.preview.noDiff")}</p>
        )}

        {rebuilt.from_audit || rebuilt.edited_unknown ? (
          <p className="type-footnote text-label-2" data-testid="import-preview-rebuilt">
            {[rebuilt.from_audit ? t("rf.preview.rebuilt", { n: n(rebuilt.from_audit) }) : null, rebuilt.edited_unknown ? t("rf.preview.rebuiltUnknown", { n: n(rebuilt.edited_unknown) }) : null].filter(Boolean).join(" ")}
          </p>
        ) : null}

        {conflicts.length ? (
          <section aria-labelledby={`${advId}-c`} className="space-y-2">
            <h3 id={`${advId}-c`} className="type-headline text-label-1">{t("rf.preview.conflictsTitle")}</h3>
            <p className="type-callout text-label-2">{t("rf.preview.conflictsLead")}</p>
            <ul className="space-y-2">
              {conflicts.slice(0, 100).flatMap((r, ri) =>
                (r.conflicts.length ? r.conflicts : [{ field: null, planner: undefined, file: undefined, previous_import: undefined, resolution: null }]).map((c, ci) => (
                  <li key={`${ri}-${ci}`} className="rounded-xl bg-fill-3 px-3 py-2.5" data-testid={`import-conflict-${ri}`}>
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="type-callout font-medium text-label-1">
                        {t(entityLabelKey(r.entity))} · <span className="font-mono type-footnote text-label-2">{r.key ?? r.id}</span>
                      </span>
                      <span className={cn("inline-flex h-6 items-center rounded-full px-2 type-caption font-medium", choice === "take" && canChoose ? "bg-status-warning text-status-warning-fg" : "bg-tint-soft text-tint-text")}>
                        {choice === "take" && canChoose ? t("rf.preview.takenTag") : t("rf.preview.keptTag")}
                      </span>
                    </div>
                    <p className="mt-1 type-footnote text-label-2">{t(fieldLabelKey(c.field))}</p>
                    <dl className="mt-1 grid grid-cols-3 gap-2 type-callout">
                      {(
                        [
                          ["rf.preview.mine", c.planner],
                          ["rf.preview.file", c.file],
                          ["rf.preview.previous", c.previous_import],
                        ] as const
                      ).map(([k, v]) => (
                        <div key={k} className="min-w-0">
                          <dt className="type-footnote text-label-3">{t(k)}</dt>
                          {/* RF-C: an exam imported before RF-06 may have no previous value (null) */}
                          <dd className="truncate font-medium text-label-1 tabular-nums">{k === "rf.preview.previous" && (v === null || v === undefined) ? t("rf.preview.unknown") : valueText(v, t)}</dd>
                        </div>
                      ))}
                    </dl>
                  </li>
                )),
              )}
            </ul>
          </section>
        ) : null}

        {others.length ? (
          <div className="space-y-2">
            <Button variant="ghost" className="pointer-coarse:h-11" aria-expanded={showRows} aria-controls={rowsId} onClick={() => setShowRows((v) => !v)} data-testid="import-show-changes">
              <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", showRows && "rotate-180")} />
              {showRows ? t("rf.preview.hideChanges") : t("rf.preview.showChanges", { n: n(Math.max(0, (diff?.rows_total ?? 0) - conflicts.length)) })}
            </Button>
            <div id={rowsId} hidden={!showRows}>
              <ul className="divide-y divide-hairline rounded-xl edge-hairline type-callout">
                {others.slice(0, 200).map((r, i) => (
                  <ChangeRow key={i} row={r} />
                ))}
              </ul>
              {(diff?.rows_total ?? 0) - conflicts.length > Math.min(others.length, 200) ? (
                <p className="mt-2 type-footnote text-label-3">{t("rf.preview.more", { n: n((diff?.rows_total ?? 0) - conflicts.length - Math.min(others.length, 200)) })}</p>
              ) : null}
            </div>
          </div>
        ) : null}

        {warnings ? (
          <div className="space-y-2">
            <Button variant="ghost" className="pointer-coarse:h-11" aria-expanded={showWarnings} aria-controls={warnId} onClick={() => setShowWarnings((v) => !v)}>
              <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", showWarnings && "rotate-180")} />
              {showWarnings ? t("rf.preview.hideWarnings") : t("rf.preview.showWarnings", { n: n(warnings) })}
            </Button>
            <div id={warnId} hidden={!showWarnings} className="space-y-3">
              <TruncatedWarnings summary={job.summary} />
              <ParseWarningsTable warnings={job.summary.warnings} groups={job.summary.warning_groups} />
            </div>
          </div>
        ) : null}

        {canChoose && !applied ? (
          <div className="space-y-3">
            <Button variant="ghost" className="pointer-coarse:h-11" aria-expanded={advanced} aria-controls={advId} onClick={() => setAdvanced((v) => !v)} data-testid="import-advanced">
              <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", advanced && "rotate-180")} />
              {t("rf.preview.advanced")}
            </Button>
            {advanced ? (
              <fieldset id={advId} className="space-y-2 rounded-xl bg-fill-3 p-3">
                <legend className="mb-1 type-footnote font-medium text-label-2">{t("rf.preview.conflictChoice")}</legend>
                {(
                  [
                    ["keep", "rf.preview.keep", "rf.preview.keepHint"],
                    ["take", "rf.preview.take", "rf.preview.takeHint"],
                  ] as const
                ).map(([v, label, hint]) => (
                  <label key={v} className="flex min-h-11 cursor-pointer items-start gap-3 py-1">
                    <input type="radio" name={`${advId}-oc`} value={v} checked={choice === v} onChange={() => setChoice(v)} className="mt-1 size-4 accent-(--tint)" aria-labelledby={`${advId}-${v}-l`} aria-describedby={`${advId}-${v}`} />
                    <span>
                      <span id={`${advId}-${v}-l`} className="block type-callout font-medium text-label-1">{t(label)}</span>
                      <span id={`${advId}-${v}`} className="block type-footnote text-label-2">{t(hint)}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <div ref={errorRef} tabIndex={-1} className="outline-hidden">
            <Alert tone="error" data-testid="import-apply-error">{error}</Alert>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>{t("rf.preview.cancel")}</Button>
          {!applied ? (
            <Button onClick={() => void apply()} {...busyProps(busy, job.status !== "DONE" || termBlocked)} data-testid="import-apply">
              <BusyLabel busy={busy} label={t("rf.preview.applying")} icon={<Check aria-hidden />}>
                {t("rf.preview.apply")}
              </BusyLabel>
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function ChangeRow({ row }: { row: ImportDiffRow }) {
  const { t } = useI18n();
  return (
    <li className="px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className={cn("inline-flex h-5 items-center rounded-full px-2 type-caption font-medium", row.change === "create" ? "bg-tint-soft text-tint-text" : "bg-fill-2 text-label-2")}>
          {row.change === "create" ? t("rf.preview.changeCreate") : t("rf.preview.changeUpdate")}
        </span>
        <span className="text-label-2">{t(entityLabelKey(row.entity))}</span>
        <span className="font-mono type-footnote text-label-1">{row.key ?? row.id}</span>
      </div>
      {row.fields.length ? (
        <ul className="mt-1 space-y-0.5 type-footnote text-label-2">
          {row.fields.map((f, i) => (
            <li key={i}>
              <span className="text-label-3">{t(fieldLabelKey(f.field))}:</span> <span className="line-through decoration-label-3">{valueText(f.from, t)}</span> → <span className="font-medium text-label-1">{valueText(f.to, t)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** A diff value as a person reads it: Evet/Hayır, "boş", lists joined, no JSON braces for flat objects. */
export function valueText(v: unknown, t: ReturnType<typeof useI18n>["t"]): string {
  if (v === null || v === undefined || v === "") return t("rf.preview.empty");
  if (typeof v === "boolean") return v ? t("rf.preview.yes") : t("rf.preview.no");
  if (Array.isArray(v)) return v.length ? v.map((x) => valueText(x, t)).join(", ") : t("rf.preview.empty");
  if (typeof v === "object") {
    const parts = Object.entries(v as Record<string, unknown>).map(([, x]) => valueText(x, t));
    return parts.length ? parts.join(" · ") : t("rf.preview.empty");
  }
  return String(v);
}
