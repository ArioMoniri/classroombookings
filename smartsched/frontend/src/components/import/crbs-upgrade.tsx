"use client";
/**
 * Import wizard › Legacy classroombookings (P18-LEGACY, admin persona M-14 / M-23 / M-25) on
 * `POST /crbs-upgrade` (`lib/api/crbs-upgrade.ts`):
 *
 * 1. Source: one or more SQL dumps (`mysqldump` or the CRBS install scripts; the default) or a live MySQL DSN,
 *    which the backend allows for administrators and allow-listed hosts only (read-only connection).
 * 2. Dry run: the mapping runs in a rolled-back transaction; the diff lists the SmartSched tables that change
 *    (before → after), what the importer creates / updates / skips, the CRBS source counts and the warnings.
 * 3. Confirm: the same mapping for real, tied to the reviewed dry run's fingerprint. A changed source (409) asks
 *    for a new dry run; nothing is written that nobody reviewed.
 * 4. Result: the committed report.
 *
 * The endpoint needs `planning.admin`; other planners see why the flow is closed instead of a 403.
 */
import { AlertTriangle, Database, FileCode2, ShieldAlert } from "lucide-react";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { HttpError } from "@/lib/api/client";
import { SQL_DUMP, changedTables, crbsUpgrade, importerRows, type UpgradeReport, type UpgradeSource } from "@/lib/api/crbs-upgrade";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { MagneticDrop, type UploadState } from "./magnetic-drop";
import type { FlowStep } from "./room-master-import";

type Mode = "dump" | "dsn";

/** the backend's reason, for the messages the UI can name */
function errorKey(e: unknown): { key: "dsnForbidden" | "dsnRefused" | "changed" | "locked" | "badDump" | "tooLarge" | "offline" | "unavailable" | "failed"; issues?: string[] } {
  if (!(e instanceof HttpError)) return { key: "failed" };
  // a dict detail ({message, issues, setting}) arrives as the whole body ({detail: {...}})
  const raw = e.detail as unknown;
  const detail = raw && typeof raw === "object" && "detail" in raw ? (raw as { detail: unknown }).detail : raw;
  if (e.status === 0) return { key: "offline" };
  if (e.status === 403) return { key: "dsnForbidden" };
  if (e.status === 413) return { key: "tooLarge" };
  if (e.status === 409 && /fingerprint|differs/i.test(e.message)) return { key: "changed" };
  if (e.status === 409 || e.status === 423) return { key: "locked" };
  if (e.status === 422 && detail && typeof detail === "object" && "issues" in detail) return { key: "dsnRefused", issues: ((detail as { issues?: unknown }).issues as string[] | undefined) ?? [] };
  if (e.status === 422 && /pymysql|connect|refused/i.test(e.message)) return { key: "unavailable" };
  if (e.status === 400 || e.status === 422) return { key: "badDump" };
  return { key: "failed" };
}

export function CrbsUpgrade({ onStep, onBack }: { onStep: (s: FlowStep) => void; onBack: () => void }) {
  const { t, n } = useI18n();
  const qc = useQueryClient();
  const { can } = usePermissions();
  const admin = can("planning.admin");
  const [mode, setMode] = useState<Mode>("dump");
  const [files, setFiles] = useState<File[]>([]);
  const [dsn, setDsn] = useState("");
  const [busy, setBusy] = useState<"dry" | "commit" | null>(null);
  const [error, setError] = useState<ReturnType<typeof errorKey> | null>(null);
  const [dry, setDry] = useState<{ report: UpgradeReport; source: UpgradeSource } | null>(null);
  const [result, setResult] = useState<UpgradeReport | null>(null);
  const [confirming, setConfirming] = useState(false);
  const diffRef = useRef<HTMLHeadingElement>(null);
  const resultRef = useRef<HTMLHeadingElement>(null);

  const source: UpgradeSource | null = mode === "dump" ? (files.length ? { kind: "dump", files } : null) : dsn.trim().length > 8 ? { kind: "dsn", dsn } : null;
  const upload: UploadState = busy === "dry" && mode === "dump" ? { phase: "processing" } : { phase: "idle" };

  const runDry = async () => {
    if (!source) return;
    setBusy("dry");
    setError(null);
    setResult(null);
    try {
      const report = await crbsUpgrade.dryRun(source);
      setDry({ report, source });
      onStep("preview");
      requestAnimationFrame(() => diffRef.current?.focus());
    } catch (e) {
      setError(errorKey(e));
    } finally {
      setBusy(null);
    }
  };

  const commit = async () => {
    if (!dry) return;
    setBusy("commit");
    setError(null);
    try {
      const report = await crbsUpgrade.commit(dry.source, dry.report.fingerprint);
      setResult(report);
      setConfirming(false);
      onStep("done");
      void qc.invalidateQueries();
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (e) {
      const err = errorKey(e);
      setError(err);
      setConfirming(false);
      if (err.key === "changed") setDry(null); // the reviewed diff no longer applies: dry-run again
    } finally {
      setBusy(null);
    }
  };

  const reset = () => {
    setDry(null);
    setResult(null);
    setError(null);
    onStep("upload");
  };

  if (!admin) {
    return (
      <Card className="max-w-3xl" data-testid="crbs-upgrade-admin-only">
        <CardContent className="flex items-start gap-3 py-5">
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-label-3" aria-hidden />
          <div className="space-y-2">
            <p className="text-[14px] font-medium text-label-1">{t("importFlows.crbs.adminOnly")}</p>
            <p className="text-[13px] text-label-2">{t("importFlows.crbs.adminOnlyHint")}</p>
            <Button variant="ghost" onClick={onBack}>{t("common.back")}</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const ErrorLine = error ? (
    <div role="alert" className="flex items-start gap-2 rounded-xl bg-status-infeasible/40 p-3 text-[13px] text-label-1" data-testid="crbs-upgrade-error">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-status-infeasible-fg" aria-hidden />
      <div>
        <p>{t(`importFlows.crbs.error.${error.key}`)}</p>
        {error.issues?.length ? (
          <ul className="mt-1 list-disc pl-4 text-[12.5px] text-label-2">
            {error.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  ) : null;

  if (result) {
    const tables = changedTables(result);
    return (
      <Card className="max-w-3xl" data-testid="crbs-upgrade-result">
        <CardHeader>
          <CardTitle>
            <h2 ref={resultRef} tabIndex={-1} className="outline-hidden">
              {t("importFlows.crbs.done")}
            </h2>
          </CardTitle>
          <p role="status" className="text-[13px] text-label-2">
            {t("importFlows.crbs.doneSummary", { rows: n(result.rows_new), tables: n(tables.length) })}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <DiffTable report={result} />
          <Button variant="outline" onClick={onBack}>{t("import.again")}</Button>
        </CardContent>
      </Card>
    );
  }

  if (dry) {
    const rep = dry.report;
    const tables = changedTables(rep);
    const entities = importerRows(rep);
    const skipped = Object.entries(rep.importer.skip_reasons ?? {});
    return (
      <Card className="max-w-4xl" data-testid="crbs-upgrade-diff">
        <CardHeader>
          <CardTitle>
            <h2 ref={diffRef} tabIndex={-1} className="outline-hidden">
              {t("importFlows.crbs.diffTitle")}
            </h2>
          </CardTitle>
          <p role="status" className="text-[13px] text-label-2" data-testid="crbs-upgrade-summary">
            {tables.length ? t("importFlows.crbs.diffSummary", { rows: n(rep.rows_new), tables: n(tables.length) }) : t("importFlows.crbs.nothing")}
          </p>
        </CardHeader>
        <CardContent className="space-y-5">
          <p className="text-[12.5px] text-label-3">{t("importFlows.crbs.dryNote")}</p>
          <DiffTable report={rep} />
          {entities.length ? (
            <section aria-labelledby="crbs-entities">
              <h3 id="crbs-entities" className="mb-2 text-[13px] font-semibold text-label-1">{t("importFlows.crbs.importer")}</h3>
              <ul className="grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
                {entities.map((e) => (
                  <li key={e.entity} className="flex justify-between gap-3">
                    <span className="font-mono text-[12.5px] text-label-2">{e.entity}</span>
                    <span className="tabular-nums text-label-1">{t("importFlows.crbs.createdUpdated", { c: n(e.created), u: n(e.updated) })}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {skipped.length ? (
            <p className="text-[13px] text-label-2">
              {t("importFlows.crbs.skipped", { n: n(rep.importer.rows_skipped_count ?? 0) })} {skipped.map(([reason, c]) => `${reason} (${n(c)})`).join(", ")}
            </p>
          ) : null}
          <details className="rounded-xl bg-fill-3 p-3 text-[13px]">
            <summary className="cursor-pointer font-medium text-label-1">{t("importFlows.crbs.sourceCounts", { n: n(Object.values(rep.source).reduce((a, b) => a + b, 0)) })}</summary>
            <ul className="mt-2 grid gap-x-6 gap-y-0.5 sm:grid-cols-3">
              {Object.entries(rep.source).map(([k, v]) => (
                <li key={k} className="flex justify-between gap-2">
                  <span className="font-mono text-[12px] text-label-2">{k}</span>
                  <span className="tabular-nums">{n(v)}</span>
                </li>
              ))}
            </ul>
          </details>
          {rep.warnings.length ? (
            <details className="rounded-xl bg-status-warning/30 p-3 text-[13px]" data-testid="crbs-upgrade-warnings">
              <summary className="cursor-pointer font-medium text-label-1">{t("importFlows.crbs.warnings", { n: n(rep.warnings.length) })}</summary>
              <ul className="mt-2 max-h-64 space-y-0.5 overflow-y-auto text-[12.5px] text-label-2">
                {rep.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          ) : null}
          {ErrorLine}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="ghost" onClick={reset} disabled={busy !== null}>{t("importFlows.crbs.changeSource")}</Button>
            <Button onClick={() => setConfirming(true)} disabled={busy !== null || !tables.length} data-testid="crbs-upgrade-confirm">
              {t("importFlows.crbs.apply")}
            </Button>
          </div>
        </CardContent>
        <Dialog open={confirming} onOpenChange={(o) => busy === null && setConfirming(o)}>
          <DialogContent className="sm:max-w-md" data-testid="crbs-upgrade-confirm-dialog">
            <DialogHeader>
              <DialogTitle>{t("importFlows.crbs.confirmTitle")}</DialogTitle>
              <DialogDescription>{t("importFlows.crbs.confirmBody", { rows: n(rep.rows_new), tables: n(tables.length) })}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={busy !== null}>{t("common.cancel")}</Button>
              <Button onClick={() => void commit()} {...busyProps(busy === "commit")} data-testid="crbs-upgrade-commit">
                <BusyLabel busy={busy === "commit"} label={t("importFlows.crbs.committing")}>{t("importFlows.crbs.commit")}</BusyLabel>
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </Card>
    );
  }

  return (
    <Card className="max-w-3xl" data-testid="crbs-upgrade">
      <CardHeader>
        <CardTitle>{t("importFlows.crbs.title")}</CardTitle>
        <p className="text-[13px] text-label-2">{t("importFlows.crbs.lead")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <SegmentedGlass
          size="sm"
          aria-label={t("importFlows.crbs.source")}
          value={mode}
          onValueChange={(v) => {
            setMode(v as Mode);
            setError(null);
          }}
          options={[
            { value: "dump", label: t("importFlows.crbs.dump") },
            { value: "dsn", label: t("importFlows.crbs.dsn") },
          ]}
        />
        {mode === "dump" ? (
          <MagneticDrop
            files={files}
            onFiles={(f) => {
              const ok = f.filter((x) => SQL_DUMP.test(x.name));
              setError(ok.length < f.length ? { key: "badDump" } : null);
              setFiles(ok);
            }}
            upload={upload}
            disabled={busy !== null}
            accept=".sql,.txt"
            multiple
            title={t("importFlows.crbs.drop")}
            hint={t("importFlows.crbs.dropHint")}
          />
        ) : (
          <div className="grid gap-1.5">
            <Label htmlFor="crbs-dsn" className="flex items-center gap-1.5">
              <Database className="size-3.5 text-label-3" aria-hidden />
              {t("import.dsn")}
            </Label>
            <Input id="crbs-dsn" placeholder="mysql://user:pass@host:3306/crbs" value={dsn} onChange={(e) => setDsn(e.target.value)} autoComplete="off" spellCheck={false} className="font-mono" data-testid="crbs-upgrade-dsn" />
            <p className="text-[12px] text-label-3">{t("importFlows.crbs.dsnHint")}</p>
          </div>
        )}
        {ErrorLine}
        <div className="flex items-center justify-between gap-2">
          <Button variant="ghost" onClick={onBack} disabled={busy !== null}>{t("common.back")}</Button>
          <Button onClick={() => void runDry()} {...busyProps(busy === "dry", !source)} data-testid="crbs-upgrade-dry-run">
            <BusyLabel busy={busy === "dry"} label={t("importFlows.crbs.reading")} icon={<FileCode2 aria-hidden />}>
              {t("importFlows.crbs.dryRun")}
            </BusyLabel>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DiffTable({ report }: { report: UpgradeReport }) {
  const { t, n } = useI18n();
  const rows = changedTables(report);
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto rounded-xl shadow-[inset_0_0_0_1px_var(--hairline)]">
      <table className="w-full min-w-[420px] text-left text-[13px]" data-testid="crbs-upgrade-tables">
        <caption className="sr-only">{t("importFlows.crbs.tablesCaption")}</caption>
        <thead className="text-[12px] text-label-3">
          <tr className="hairline-b">
            <th scope="col" className="px-3 py-2 font-medium">{t("importFlows.crbs.colTable")}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t("importFlows.crbs.colBefore")}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t("importFlows.crbs.colAfter")}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t("importFlows.crbs.colDelta")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.table} className="[&:not(:last-child)]:hairline-b" data-testid={`crbs-table-${r.table}`}>
              <th scope="row" className="px-3 py-1.5 font-mono text-[12.5px] font-normal text-label-1">{r.table}</th>
              <td className="px-3 py-1.5 text-right tabular-nums text-label-2">{n(r.before)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums text-label-1">{n(r.after)}</td>
              <td className="px-3 py-1.5 text-right font-medium tabular-nums text-tint-text">{r.delta > 0 ? `+${n(r.delta)}` : n(r.delta)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
