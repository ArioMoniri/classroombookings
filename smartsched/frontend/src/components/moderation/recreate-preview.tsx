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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { Progress } from "@/components/ui/progress";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useRun } from "@/lib/api/hooks";
import { isResponseShapeError } from "@/lib/api/error-text";
import { moderationApi, refusal, useDiff, usePeople, useRunRules, type DiffOut } from "@/lib/api/moderation";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { CompareCalendar } from "./compare-calendar";
import { RECREATE_STARTED_TOAST } from "./recreate-sheet";
import { ResponsiveDialog } from "./responsive-dialog";
import { usePhone } from "./use-media";
import { ModTable, type ModColumn } from "./mod-table";
import { DIFF_GROUPS, baselineOptions, canPublish, chainText, diffCount, diffRows, isDraftChild, notifyTargets, pairText, type DiffGroup, type DiffRow } from "./moderation-model";

type Action = "pin" | "prefer" | "unlock";

export function RecreatePreview({ runId }: { runId: number }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const qc = useQueryClient();
  const reduce = useReduce();
  const { can } = usePermissions();
  const canEdit = can("planning.edit");
  // the baseline (compare_to): the server's fixed one (the published run that started the chain) unless picked
  const [compareTo, setCompareTo] = useState<number | null>(null);
  const defaultQ = useDiff(runId);
  const pickedQ = useDiff(compareTo !== null && defaultQ.data?.ready ? runId : null, compareTo);
  const diffQ = compareTo !== null && pickedQ.data ? pickedQ : defaultQ;
  const fixed = { current: defaultQ.data?.compare_to_run_id ?? null };
  const runQ = useRun(runId);
  const rules = useRunRules(diffQ.data?.ready ? runId : null);
  const d = diffQ.data;
  const [group, setGroup] = useState<DiffGroup>("moved");
  const [chosenMode, setMode] = useState<"table" | "calendar">("table");
  const phone = usePhone();
  // the calendar compare is a tablet / desktop view; phones get the grouped list (owner requirement 2026-10-15)
  const mode = phone ? "table" : chosenMode;
  const [confirm, setConfirm] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [edited, setEdited] = useState<number[]>([]);
  const [busyRow, setBusyRow] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");

  const rows = useMemo(() => (d?.ready ? diffRows(d, lang) : null), [d, lang]);
  const ownEdits = useMemo(() => (rules.data ?? []).filter((r) => r.source_ref && typeof r.source_ref === "object" && "moderation" in r.source_ref), [rules.data]);
  const editedIds = useMemo(() => [...new Set([...edited, ...ownEdits.map((r) => Number((r.source_ref as { moderation?: { request_id?: number } }).moderation?.request_id)).filter(Number.isFinite)])], [edited, ownEdits]);

  // preview ready → announce the counts once (live region, motion.md §3.9 recreate-ready)
  const said = useRef(false);
  useEffect(() => {
    if (d?.ready && d.counts && !said.current) {
      said.current = true;
      setAnnounce(t("moderation.preview.ready", { moved: d.counts.moved, newly: d.counts.newly_placed, unplaceable: d.counts.unplaceable }));
    }
  }, [d, t]);
  // the "Yeniden çözüm #n başladı" toast sits bottom-right, exactly over the sticky footer's "Onayla ve yayınla", and
  // Sonner pauses its expiry under a resting pointer: it goes the moment this page shows the run (T-R2-23 / e2e gate)
  useEffect(() => {
    toast.dismiss(RECREATE_STARTED_TOAST);
  }, [runId]);

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
      const out = await moderationApi.resolve(runQ.data?.term_id ?? 0, { base_run_id: runId, changed_request_ids: editedIds, mode: editedIds.length ? "repair" : "full", ...(compareTo !== null ? { compare_to: compareTo } : {}) });
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
            {t("moderation.preview.compared", { basis: t(`moderation.preview.basis.${d.compared_to}`), id: d.compare_to_run_id ?? d.base_run_id })}
            {" · "}
            <span data-testid="preview-state">{d.is_active ? `✓ ${t("moderation.preview.published")}` : t("moderation.preview.notPublished")}</span>
          </p>
        </div>
        {!phone ? <SegmentedControl<"table" | "calendar">
          aria-label={t("moderation.preview.mode")}
          size="sm"
          value={mode}
          onValueChange={setMode}
          options={[
            { value: "table", label: t("moderation.preview.table"), icon: <Table2 aria-hidden /> },
            { value: "calendar", label: t("moderation.preview.calendar"), icon: <CalendarRange aria-hidden /> },
          ]}
        /> : null}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center" data-testid="baseline">
        <label className="flex flex-col gap-1 type-footnote text-label-2 sm:flex-row sm:items-center sm:gap-2">
          {t("moderation.preview.compareTo")}
          <NativeSelect className="sm:w-72" value={String(compareTo ?? "")} onChange={(e) => setCompareTo(e.target.value ? Number(e.target.value) : null)} data-testid="baseline-select">
            <option value="">{t("moderation.preview.baselineDefault", { id: fixed.current ?? d.compare_to_run_id ?? d.base_run_id })}</option>
            {baselineOptions(d, fixed.current).filter((id) => id !== fixed.current).map((id) => (
              <option key={id} value={id}>{id === d.base_run_id ? t("moderation.preview.baselineParent", { id }) : t("moderation.preview.baselineStep", { id })}</option>
            ))}
          </NativeSelect>
        </label>
        <p className="type-caption text-label-3" data-testid="chain">{t("moderation.preview.chain", { chain: chainText(d) })}</p>
        {pickedQ.isFetching ? <span className="type-caption text-label-3">{t("busy.loading")}</span> : null}
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
              <ModTable rows={list} columns={columns} getId={(r) => r.requestId} caption={t("moderation.caption.diff", { n: n(list.length), group: t(`moderation.diff.${group}`) })} testId="diff-table" rowTestId="diff-row" mobile={phone} card={(r) => (
                <div className="flex flex-col gap-0.5 rounded-xl border border-hairline bg-card p-3">
                  <div className="flex items-center justify-between gap-2"><span className="type-headline">{r.label}</span>{draft ? columns[columns.length - 1]!.cell(r) : null}</div>
                  <span className="type-footnote text-label-2">{r.before} → {r.after}</span>
                  {r.reason ? <span className="type-footnote text-label-2">{r.group === "unplaceable" ? "✕ " : ""}{r.reason}</span> : null}
                </div>
              )} empty={<p className="type-callout text-label-2" data-testid="diff-empty">{t("moderation.diff.empty")}</p>} />
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
      <PublishDialog open={confirm} onOpenChange={setConfirm} diff={d} termId={runQ.data?.term_id ?? null} onPublished={() => void qc.invalidateQueries()} />
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
export function PublishDialog({ open, onOpenChange, diff, termId, onPublished }: { open: boolean; onOpenChange: (v: boolean) => void; diff: DiffOut; termId: number | null; onPublished: () => void }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const cancel = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; issues: string[]; scopeReduction: boolean } | null>(null);
  const [confirmScope, setConfirmScope] = useState(false);
  // round-1 R1-S-04: classes that lose their room with this plan are listed and need an explicit tick
  const losses = diff.unplaceable.filter((u) => u.was_placed);
  const [lossesOk, setLossesOk] = useState(false);
  // "Akademisyenlere bildir" (P19-M-09 / T3): one digest per affected academician with a linked account
  const [notify, setNotify] = useState(true);
  const people = usePeople(open ? termId : null);
  const targets = notifyTargets(diff.affected_instructor_ids, people.data?.items ?? []);
  const c = diff.counts!;
  const published = (notified: number | null) => {
    toast.success(t("moderation.preview.publishedToast", { id: diff.run_id }));
    if (typeof notified === "number") toast.success(t("moderation.publish.notified", { n: n(notified) }));
    onOpenChange(false);
    onPublished(); // the diff and run queries refetch: the preview state reads "✓ Yayında" from the server
  };
  const publish = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await moderationApi.activate(diff.run_id, confirmScope, notify && targets.linked.length > 0);
      published(out.notified ?? null);
    } catch (e) {
      // T-R2-23 (R2-M-02): the server answered 2xx, so the plan IS published; only the client's schema disagreed
      // with the body. Treat it as done and let the refetch show the server's state, never zod's English text.
      if (isResponseShapeError(e)) published(null);
      else setError(refusal(e, lang));
    } finally {
      setBusy(false);
    }
  };
  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={(o) => { onOpenChange(o); if (!o) setError(null); }}
      alert
      initialFocus={cancel}
      title={t("moderation.publish.title")}
      description={t("moderation.publish.body")}
      testId="publish-dialog"
      footer={
        <>
          <Button ref={cancel} variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button onClick={() => void publish()} disabled={busy || (error?.scopeReduction === true && !confirmScope) || (losses.length > 0 && !lossesOk)} data-testid="publish-confirm" aria-busy={busy || undefined}>
            {busy ? t("busy.working") : t("moderation.publish.go")}
          </Button>
        </>
      }
    >
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
      {losses.length ? (
        <section className="flex flex-col gap-1.5 rounded-xl border border-status-warning-border bg-status-warning p-3" data-testid="publish-losses">
          <p className="type-callout font-semibold text-status-warning-fg">
            {lang === "tr" ? `${n(losses.length)} ders dersliğini kaybediyor:` : `${n(losses.length)} classes lose their room:`}
          </p>
          <ul className="max-h-40 list-disc overflow-y-auto pl-5 type-footnote text-label-1">
            {losses.slice(0, 20).map((u) => (
              <li key={u.request_id}>
                <span className="font-medium">{u.label}</span>
                {u.from?.when ? <span className="text-label-2"> · {lang === "tr" ? u.from.when.tr : u.from.when.en} {u.from.rooms.join(" + ")}</span> : null}
                <span className="text-label-2"> · {lang === "tr" ? u.reason.text.tr : u.reason.text.en}</span>
              </li>
            ))}
            {losses.length > 20 ? <li className="text-label-2">{t("moderation.changes.more", { n: n(losses.length - 20) })}</li> : null}
          </ul>
          <label className="flex min-h-11 items-center gap-2 type-callout text-label-1">
            <input type="checkbox" checked={lossesOk} onChange={(e) => setLossesOk(e.target.checked)} className="accent-(--accent)" data-testid="publish-losses-ack" />
            {lang === "tr" ? "Bu derslerin dersliksiz kalmasını onaylıyorum" : "I confirm these classes lose their room"}
          </label>
        </section>
      ) : null}
      <section className="flex flex-col gap-1.5 rounded-xl border border-hairline p-3" data-testid="notify-people">
        <label className="flex min-h-11 items-center gap-2 type-callout font-semibold">
          <Switch checked={notify && targets.linked.length > 0} disabled={!targets.linked.length} onCheckedChange={setNotify} data-testid="notify-toggle" />
          {t("moderation.publish.notify")}
        </label>
        {people.isLoading ? (
          <p className="type-footnote text-label-3">{t("busy.loading")}</p>
        ) : targets.linked.length ? (
          <>
            <p className="type-footnote text-label-2">{t("moderation.publish.notifyWho", { n: n(targets.linked.length) })}</p>
            <ul className="flex flex-wrap gap-x-2 gap-y-0.5 type-footnote" data-testid="notify-list">
              {targets.linked.slice(0, 12).map((p) => <li key={p.id}>{p.label}</li>)}
              {targets.linked.length > 12 ? <li className="text-label-2">{t("moderation.changes.more", { n: n(targets.linked.length - 12) })}</li> : null}
            </ul>
          </>
        ) : (
          <p className="type-footnote text-label-2">{t("moderation.publish.notifyNone")}</p>
        )}
        {targets.unlinked > 0 ? <p className="type-caption text-label-3">{t("moderation.publish.notifyUnlinked", { n: n(targets.unlinked) })}</p> : null}
        <p className="type-caption text-label-3">{t("moderation.publish.notifyHint")}</p>
      </section>
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
    </ResponsiveDialog>
  );
}
