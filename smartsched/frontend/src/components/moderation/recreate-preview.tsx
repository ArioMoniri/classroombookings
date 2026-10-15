"use client";
/**
 * /moderation/recreate/[runId], step B of "Planı yeniden oluştur" (moderation spec §5.4, motion.md §3.9): the
 * preview diff of a re-solve against its base run as the primary view (Taşınan · Yeni yerleşen · Yerleşemeyen
 * with reasons · Değişmeyen), an optional calendar compare mode, pin / prefer / unlock edits written to THIS
 * draft child run (never the published run) followed by "Yeniden çalıştır" (pin-and-re-run only: no partial
 * publish), and "Onayla ve yayınla" through the existing publish guard, whose 409 reasons are shown verbatim.
 */
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarRange, CheckCircle2, Ellipsis, Pin, RefreshCw, Star, Table2, Unlock } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { Progress } from "@/components/ui/progress";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { useRun } from "@/lib/api/hooks";
import { moderationApi, refusal, useDiff, useRunRules, type DiffOut } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { CompareCalendar } from "./compare-calendar";
import { ModTable, type ModColumn } from "./mod-table";
import { DIFF_GROUPS, canPublish, diffCount, diffRows, isDraftChild, pairText, type DiffGroup, type DiffRow } from "./moderation-model";

type Action = "pin" | "prefer" | "unlock";

export function RecreatePreview({ runId }: { runId: number }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const qc = useQueryClient();
  const reduce = useReduce();
  const { can } = usePermissions();
  const canEdit = can("planning.edit");
  const diffQ = useDiff(runId);
  const runQ = useRun(runId);
  const baseQ = useRun(diffQ.data?.base_run_id ?? null);
  const rules = useRunRules(diffQ.data?.ready ? runId : null);
  const d = diffQ.data;
  const [group, setGroup] = useState<DiffGroup>("moved");
  const [mode, setMode] = useState<"table" | "calendar">("table");
  const [confirm, setConfirm] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [edited, setEdited] = useState<number[]>([]);
  const [busyRow, setBusyRow] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");

  const rows = useMemo(() => (d?.ready ? diffRows(d, lang) : null), [d, lang]);
  const ownEdits = useMemo(() => (rules.data ?? []).filter((r) => r.source_ref && typeof r.source_ref === "object" && "moderation" in r.source_ref), [rules.data]);
  const editedIds = useMemo(() => [...new Set([...edited, ...ownEdits.map((r) => Number((r.source_ref as { moderation?: { request_id?: number } }).moderation?.request_id)).filter(Number.isFinite)])], [edited, ownEdits]);
  const baseIsPublished = baseQ.data?.is_active ?? false;

  // preview ready → announce the counts once (live region, motion.md §3.9 recreate-ready)
  const said = useRef(false);
  useEffect(() => {
    if (d?.ready && d.counts && !said.current) {
      said.current = true;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one announcement when the server finishes
      setAnnounce(t("moderation.preview.ready", { moved: d.counts.moved, newly: d.counts.newly_placed, unplaceable: d.counts.unplaceable }));
    }
  }, [d, t]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.altKey) return;
      if (!e.metaKey && !e.ctrlKey && /^[1-4]$/.test(e.key)) {
        setGroup(DIFF_GROUPS[Number(e.key) - 1]!);
      } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canPublish(d) && canEdit) {
        e.preventDefault();
        setConfirm(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [d, canEdit]);

  const act = async (row: DiffRow, action: Action) => {
    setBusyRow(row.requestId);
    try {
      const out = await moderationApi.matchingAction(row.requestId, { run_id: runId, action });
      setEdited((e) => [...new Set([...e, row.requestId])]);
      await qc.invalidateQueries({ queryKey: ["moderation", "run-rules", runId] });
      toast.success(`${row.label}: ${t(`moderation.preview.done.${action}`)} · ${pairText(out.effective, lang)}`);
    } catch (e) {
      const r = refusal(e, lang);
      toast.error([r.message, ...r.issues].join(" · "));
    } finally {
      setBusyRow(null);
    }
  };

  const rerun = async () => {
    if (!d) return;
    setRerunning(true);
    try {
      const out = await moderationApi.resolve(runQ.data?.term_id ?? 0, { base_run_id: runId, changed_request_ids: editedIds, mode: editedIds.length ? "repair" : "full" });
      router.push(`/moderation/recreate/${out.run_id}`);
    } catch (e) {
      toast.error(refusal(e, lang).message);
      setRerunning(false);
    }
  };

  // ------------------------------------------------------------------ running / failed
  if (diffQ.isError) {
    return (
      <EmptyState title={t("moderation.preview.errorTitle")} description={refusal(diffQ.error, lang).message} actions={<Button variant="outline" render={<Link href="/moderation?tab=matchings" />} nativeButton={false}>{t("moderation.preview.back")}</Button>} />
    );
  }
  if (!d || !d.ready) {
    const run = runQ.data;
    const phase = run?.stats?.phase;
    return (
      <div className="flex max-w-xl flex-col gap-3" data-testid="preview-running">
        <BackLink />
        <h1 className="type-large-title">{t("moderation.preview.title")}</h1>
        <p className="type-callout text-label-2" role="status">
          {t("moderation.preview.running", { id: runId })}
          {typeof phase === "string" ? ` · ${phase}` : ""}
        </p>
        {/* real progress from the run, never faked (motion skill §6) */}
        <Progress value={run?.progress ?? 0} aria-label={t("moderation.preview.progress")} />
        <p className="type-footnote text-label-2">{t("moderation.preview.keepWorking")}</p>
      </div>
    );
  }
  const failed = !["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"].includes(d.status);
  const c = d.counts!;
  const list = group === "unchanged" ? [] : rows![group];
  const draft = isDraftChild(d) && canEdit;

  const columns: ModColumn<DiffRow>[] = [
    { id: "course", header: t("moderation.col.course"), width: "minmax(9rem,1fr)", cell: (r) => r.label },
    { id: "before", header: t("moderation.preview.before"), width: "minmax(12rem,1.5fr)", cell: (r) => r.before },
    { id: "after", header: t("moderation.preview.after"), width: "minmax(12rem,1.5fr)", cell: (r) => (r.group === "newly_placed" ? <span>{r.after} <span className="ml-1 rounded-full bg-fill-2 px-1.5 type-caption">{t("moderation.preview.newTag")}</span></span> : r.after) },
    { id: "reason", header: t("moderation.col.reason"), width: "minmax(14rem,2fr)", cell: (r) => <span className="text-label-2" title={r.reason}>{r.group === "unplaceable" ? "✕ " : ""}{r.reason || "—"}</span> },
    ...(draft
      ? [
          {
            id: "act",
            header: <span className="sr-only">{t("common.actions")}</span>,
            width: "3rem",
            cell: (r: DiffRow) => (
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("moderation.preview.rowActions", { label: r.label })} disabled={busyRow === r.requestId} data-testid="diff-row-actions" />}>
                  <Ellipsis aria-hidden />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {r.group === "moved" ? <DropdownMenuItem onClick={() => void act(r, "pin")}><Pin aria-hidden />{t("moderation.preview.pin")}</DropdownMenuItem> : null}
                  {r.from || r.to ? <DropdownMenuItem onClick={() => void act(r, "prefer")}><Star aria-hidden />{t("moderation.preview.prefer")}</DropdownMenuItem> : null}
                  <DropdownMenuItem onClick={() => void act(r, "unlock")}><Unlock aria-hidden />{t("moderation.preview.unlock")}</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ),
          } satisfies ModColumn<DiffRow>,
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-3" data-testid="recreate-preview">
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      <BackLink />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="type-large-title">{t("moderation.preview.title")}</h1>
          <p className="type-callout text-label-2">
            {baseIsPublished ? t("moderation.preview.against", { base: d.base_run_id }) : t("moderation.preview.againstPreview", { base: d.base_run_id })}
            {" · "}
            <span data-testid="preview-state">{d.is_active ? `✓ ${t("moderation.preview.published")}` : t("moderation.preview.notPublished")}</span>
          </p>
        </div>
        <SegmentedControl<"table" | "calendar">
          aria-label={t("moderation.preview.mode")}
          size="sm"
          value={mode}
          onValueChange={setMode}
          options={[
            { value: "table", label: t("moderation.preview.table"), icon: <Table2 aria-hidden /> },
            { value: "calendar", label: t("moderation.preview.calendar"), icon: <CalendarRange aria-hidden /> },
          ]}
        />
      </div>
      {failed ? <p role="alert" className="type-callout text-status-infeasible-fg">{t("moderation.preview.failed", { status: d.status })}</p> : null}
      {/* summary: static on arrival, no count-up (motion.md §3.9) */}
      <dl className="flex flex-wrap gap-x-5 gap-y-1 type-callout" data-testid="diff-summary">
        <div className="flex gap-1"><dt>{t("moderation.diff.moved")}</dt><dd className="font-semibold tabular-nums" data-testid="count-moved">{n(c.moved)}</dd></div>
        <div className="flex gap-1"><dt>{t("moderation.diff.unchanged")}</dt><dd className="font-semibold tabular-nums" data-testid="count-unchanged">{n(c.unchanged)}</dd></div>
        <div className="flex gap-1"><dt>{t("moderation.diff.newly_placed")}</dt><dd className="font-semibold tabular-nums">{n(c.newly_placed)}</dd></div>
        <div className="flex gap-1"><dt>{t("moderation.diff.unplaceable")}</dt><dd className="font-semibold tabular-nums">{n(c.unplaceable)}{c.newly_unplaced ? ` (${t("moderation.diff.newlyUnplaced", { n: n(c.newly_unplaced) })})` : ""}</dd></div>
        <div className="flex gap-1"><dt>{t("moderation.diff.people")}</dt><dd className="font-semibold tabular-nums">{n(c.affected_people)}</dd></div>
        <div className="flex gap-1"><dt>{t("moderation.diff.hard")}</dt><dd className="font-semibold tabular-nums">{d.scores?.hard?.before ?? "—"} → {d.scores?.hard?.after ?? "—"}</dd></div>
        <div className="flex gap-1"><dt>{t("moderation.diff.soft")}</dt><dd className="font-semibold tabular-nums">{d.scores?.soft?.before ?? "—"} → {d.scores?.soft?.after ?? "—"}</dd></div>
      </dl>
      {c.moved_outside_scope ? <p className="type-footnote text-label-2">{t("moderation.diff.outside", { n: n(c.moved_outside_scope), unexplained: n(c.moved_unexplained) })}</p> : null}

      {mode === "calendar" ? (
        <CompareCalendar diff={d} />
      ) : (
        <>
          <div className="overflow-x-auto">
            <SegmentedControl<DiffGroup>
              aria-label={t("moderation.preview.groups")}
              value={group}
              onValueChange={setGroup}
              options={DIFF_GROUPS.map((g) => ({ value: g, label: <span className="whitespace-nowrap">{t(`moderation.diff.${g}`)} <span className="tabular-nums text-label-3">{n(diffCount(d, g))}</span></span> }))}
            />
          </div>
          <motion.div key={group} initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={reduce ? tween.reduced : springs.smooth}>
            {group === "unchanged" ? (
              <p className="type-callout text-label-2" data-testid="unchanged-note">{t("moderation.diff.unchangedNote", { n: n(c.unchanged) })}</p>
            ) : (
              <ModTable rows={list} columns={columns} getId={(r) => r.requestId} caption={t("moderation.caption.diff", { n: n(list.length), group: t(`moderation.diff.${group}`) })} testId="diff-table" rowTestId="diff-row" empty={<p className="type-callout text-label-2" data-testid="diff-empty">{t("moderation.diff.empty")}</p>} />
            )}
          </motion.div>
        </>
      )}

      {draft ? (
        <section className="flex flex-col gap-1 border-t border-hairline pt-3" data-testid="draft-edits">
          <h2 className="type-headline">{t("moderation.preview.edits", { n: n(ownEdits.length) })}</h2>
          {ownEdits.length ? (
            <ul className="type-footnote text-label-2">
              {ownEdits.map((r) => <li key={r.id}>{r.nl_text ?? r.kind} · {r.hardness === "hard" ? t("moderation.preview.hard") : t("moderation.preview.soft")}</li>)}
            </ul>
          ) : (
            <p className="type-footnote text-label-2">{t("moderation.preview.editsHint")}</p>
          )}
        </section>
      ) : null}

      <div className="sticky bottom-3 z-10 flex flex-wrap items-center justify-end gap-2 rounded-2xl glass-chrome px-3 py-2">
        <Button variant="ghost" render={<Link href="/moderation?tab=matchings" />} nativeButton={false}>{t("moderation.preview.discard")}</Button>
        {draft ? (
          <Button variant="outline" onClick={() => void rerun()} disabled={rerunning || editedIds.length === 0} data-testid="preview-rerun" aria-busy={rerunning || undefined}>
            <RefreshCw aria-hidden />
            {rerunning ? t("busy.working") : t("moderation.preview.rerun", { n: n(editedIds.length) })}
          </Button>
        ) : null}
        {canEdit && !d.is_active ? (
          <Button onClick={() => setConfirm(true)} disabled={!canPublish(d)} aria-keyshortcuts="Meta+Enter" data-testid="preview-publish">
            {t("moderation.preview.publish")}
          </Button>
        ) : null}
        {d.is_active ? <span className="inline-flex items-center gap-1 type-callout text-status-feasible-fg"><CheckCircle2 className="size-4" aria-hidden />{t("moderation.preview.published")}</span> : null}
      </div>
      {!canEdit ? <p className="type-footnote text-label-3">{t("moderation.publishNeedsEdit")}</p> : null}
      <PublishDialog open={confirm} onOpenChange={setConfirm} diff={d} onPublished={() => void qc.invalidateQueries()} />
    </div>
  );
}

function BackLink() {
  const { t } = useI18n();
  return (
    <Button variant="ghost" size="sm" className="self-start" render={<Link href="/moderation?tab=matchings" />} nativeButton={false}>
      <ArrowLeft aria-hidden />
      {t("moderation.title")}
    </Button>
  );
}

/** "Onayla ve yayınla": an alertdialog with the counts; "Vazgeç" has the default focus (spec §11) */
export function PublishDialog({ open, onOpenChange, diff, onPublished }: { open: boolean; onOpenChange: (v: boolean) => void; diff: DiffOut; onPublished: () => void }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const cancel = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; issues: string[]; scopeReduction: boolean } | null>(null);
  const [confirmScope, setConfirmScope] = useState(false);
  const c = diff.counts!;
  const publish = async () => {
    setBusy(true);
    setError(null);
    try {
      await moderationApi.activate(diff.run_id, confirmScope);
      toast.success(t("moderation.preview.publishedToast", { id: diff.run_id }));
      onOpenChange(false);
      onPublished();
    } catch (e) {
      setError(refusal(e, lang));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setError(null); }}>
      <DialogContent role="alertdialog" initialFocus={cancel} className="sm:max-w-md" data-testid="publish-dialog">
        <DialogHeader>
          <DialogTitle>{t("moderation.publish.title")}</DialogTitle>
          <DialogDescription>{t("moderation.publish.body")}</DialogDescription>
        </DialogHeader>
        <table className="w-full type-callout">
          <tbody>
            {([["moved", c.moved], ["newly_placed", c.newly_placed], ["unplaceable", c.unplaceable], ["people", c.affected_people]] as const).map(([k, v]) => (
              <tr key={k} className="border-b border-hairline">
                <th scope="row" className="py-1 text-left font-normal text-label-2">{t(`moderation.diff.${k}`)}</th>
                <td className="py-1 text-right font-semibold tabular-nums">{n(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {error ? (
          <div role="alert" className="flex flex-col gap-1 rounded-xl border border-status-infeasible-border bg-status-infeasible p-3 type-footnote text-status-infeasible-fg" data-testid="publish-refused">
            <p className="font-semibold">{error.message}</p>
            {error.issues.length ? <ul className="list-disc pl-4">{error.issues.map((i) => <li key={i}>{i}</li>)}</ul> : null}
            {error.scopeReduction ? (
              <label className="mt-1 flex items-center gap-2 text-label-1">
                <input type="checkbox" checked={confirmScope} onChange={(e) => setConfirmScope(e.target.checked)} className="accent-(--accent)" />
                {t("moderation.publish.confirmScope")}
              </label>
            ) : null}
          </div>
        ) : null}
        <DialogFooter>
          <Button ref={cancel} variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button onClick={() => void publish()} disabled={busy || (error?.scopeReduction === true && !confirmScope)} data-testid="publish-confirm" aria-busy={busy || undefined}>
            {busy ? t("busy.working") : t("moderation.publish.go")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
