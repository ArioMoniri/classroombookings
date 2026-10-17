"use client";
/**
 * /bookings/conflicts/[run] — the P2 conflict resolver after publishing (planning.edit; keeping a clashing booking
 * needs planning.admin). One card per group (a series is one card), ranked options with the backend's reasons, a scope
 * for series, a reason for cancel / keep. "Önerilenleri uygula" asks the backend for its suggestions (`auto`), fills
 * the decisions and opens the review; the review runs a dry run first, so the counts shown are what `apply` will do.
 * Apply is all or nothing: a 409 `invalid_items` lands next to the rows it names and nothing changes.
 *
 * Motion: the result summary and the inline problems enter with opacity + 4 px on springs.smooth (≤ 300 ms); reduced
 * motion keeps a 100 ms fade (motion.md: "did it work"). Sheets and dialogs use the design system's own transitions.
 */
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CalendarClock, CheckCircle2, DoorOpen, Repeat, RotateCw, ShieldAlert, Wand2, XCircle } from "lucide-react";
import { useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, Loading, NoAccess, PageTitle } from "@/components/admin/kit";
import { ResponsiveDialog } from "@/components/approvals/responsive-dialog";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { applyProblems, conflictsApi, useApplyConflicts, useConflictPlan, useConflictSummary, useDetectConflicts, type ApplyItem, type ApplyResult, type ConflictGroup, type ConflictOption, type Problem, type ResolveScope } from "@/lib/api/booking-conflicts";
import { usePermissions } from "@/lib/api/shell-extra";
import { errorText, pickLang, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { pick, springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { applyAuto, buildItems, choosableOptions, dayMonth, EMPTY_DECISION, groupTime, initialState, needsReason, optionOf, problemsByGroup, progress, rowIssue, scopesFor, summarise, type Decision, type ResolverState } from "./resolver-model";

const OPTION_ICON: Record<ConflictOption["kind"], typeof DoorOpen> = { move_room: DoorOpen, move_period: CalendarClock, move_day: CalendarClock, cancel: XCircle, override: ShieldAlert };
const SCOPE_KEY: Record<ResolveScope, MessageKey> = { one: "resolver.scope.one", future: "resolver.scope.future", all: "resolver.scope.all" };

function useEnter() {
  const reduce = useReduce();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 4 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0 },
    transition: pick(reduce, springs.smooth, tween.reduced),
  };
}

export function ResolverView({ runId }: { runId: number }) {
  const { t, locale } = useI18n();
  const { can, me } = usePermissions();
  const planner = can("planning.edit");
  const isAdmin = can("planning.admin");
  const plan = useConflictPlan(planner ? runId : null);
  const summary = useConflictSummary(planner);
  const apply = useApplyConflicts(runId);
  const detect = useDetectConflicts(runId);
  const [state, setState] = useState<ResolverState | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [review, setReview] = useState<{ items: ApplyItem[]; dry: ApplyResult | null; unresolved: Map<number, { tr: string; en: string } | null>; auto: boolean } | null>(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const enter = useEnter();

  const data = plan.data;
  // the decisions belong to the plan that was loaded: a refetch with other groups starts over
  const planKey = data ? data.groups.map((g) => `${g.key}:${g.conflicts.length}`).join("|") : "";
  const [seenKey, setSeenKey] = useState("");
  if (data && planKey !== seenKey) {
    setSeenKey(planKey);
    setState(initialState(data));
  }
  const s = state ?? initialState(data);
  const byGroup = useMemo(() => problemsByGroup(data, problems), [data, problems]);
  const items = useMemo(() => (data ? buildItems(data, s) : []), [data, s]);
  const prog = progress(data, s);
  const blocked = data ? data.groups.some((g) => !s.split[g.key] && rowIssue(g, s.groups[g.key] ?? EMPTY_DECISION, isAdmin)) || data.groups.some((g) => s.split[g.key] && g.conflicts.some((c) => rowIssue(g, s.perConflict[c.conflict_id] ?? EMPTY_DECISION, isAdmin))) : false;

  if (!me) return <Loading />;
  if (!planner) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("resolver.noAccess")} />;

  const setGroup = (key: string, patch: Partial<Decision>) => setState({ ...s, groups: { ...s.groups, [key]: { ...(s.groups[key] ?? EMPTY_DECISION), ...patch } } });
  const setConflict = (id: number, patch: Partial<Decision>) => setState({ ...s, perConflict: { ...s.perConflict, [id]: { ...(s.perConflict[id] ?? EMPTY_DECISION), ...patch } } });
  const setSplit = (key: string, on: boolean) => setState({ ...s, split: { ...s.split, [key]: on } });

  const fail = (e: unknown) => {
    const found = applyProblems(e);
    setProblems(found);
    setFailure(errorText(wave1Error(e), locale));
    setReview(null);
  };

  const openReview = async (list: ApplyItem[], unresolved: Map<number, { tr: string; en: string } | null> = new Map(), auto = false) => {
    setProblems([]);
    setFailure(null);
    setResult(null);
    setReview({ items: list, dry: null, unresolved, auto });
    if (!list.length) return;
    try {
      const dry = await conflictsApi.apply(runId, list, true);
      setReview((r) => (r ? { ...r, dry } : r));
    } catch (e) {
      fail(e);
    }
  };

  const suggest = async () => {
    if (!data) return;
    setAutoBusy(true);
    try {
      const auto = await conflictsApi.auto(runId);
      const { state: next, unresolved } = applyAuto(data, auto, s);
      setState(next);
      await openReview(buildItems(data, next), unresolved, true);
    } catch (e) {
      fail(e);
    } finally {
      setAutoBusy(false);
    }
  };

  const confirm = () => {
    if (!review) return;
    apply.mutate(
      { items: review.items, dryRun: false },
      {
        onSuccess: (res) => {
          setReview(null);
          setResult(res);
          setProblems([]);
          setFailure(null);
          toast.success(t("resolver.applied", { n: res.resolved.length }));
        },
        onError: fail,
      },
    );
  };

  const stale = plan.isError && wave1Error(plan.error).code === "plan_stale";
  const current = summary.data?.runs.find((r) => r.run_id !== runId);

  return (
    <div className="flex max-w-4xl flex-col gap-5" data-testid="resolver">
      <PageTitle
        title={t("resolver.title")}
        subtitle={data?.open ? t("resolver.subtitle", { n: data.open, series: data.groups.filter((g) => g.kind === "series").length }) : undefined}
        actions={
          data && data.groups.length ? (
            <>
              <Button variant="outline" size="sm" onClick={() => detect.mutate(undefined, { onSuccess: (r) => toast.success(t("resolver.detected", { n: r.open })), onError: (e) => toast.error(errorText(wave1Error(e), locale)) })} {...busyProps(detect.isPending)} data-testid="resolver-detect">
                <BusyLabel busy={detect.isPending} label={t("busy.checking")} icon={<RotateCw aria-hidden />}>
                  {t("resolver.detect")}
                </BusyLabel>
              </Button>
              <Button size="sm" onClick={() => void suggest()} {...busyProps(autoBusy)} data-testid="resolver-auto">
                <BusyLabel busy={autoBusy} label={t("busy.working")} icon={<Wand2 aria-hidden />}>
                  {t("resolver.auto")}
                </BusyLabel>
              </Button>
            </>
          ) : null
        }
      />

      <AnimatePresence initial={false}>
        {result ? (
          <motion.div key="result" {...enter}>
            <ResultCard result={result} />
          </motion.div>
        ) : null}
        {failure ? (
          <motion.div key="failure" {...enter}>
            <Alert tone="error" title={t("resolver.failedTitle")} testId="resolver-failure">
              {failure}
            </Alert>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {plan.isLoading ? <Loading /> : null}
      {stale ? (
        <Alert tone="warning" title={t("resolver.staleTitle")} testId="resolver-stale" action={current ? <Button size="sm" variant="outline" render={<Link href={`/bookings/conflicts/${current.run_id}`} />} nativeButton={false}>{t("resolver.openCurrent")}</Button> : undefined}>
          {errorText(wave1Error(plan.error), locale)}
        </Alert>
      ) : plan.isError ? (
        <Alert tone="error">{errorText(wave1Error(plan.error), locale)}</Alert>
      ) : null}

      {data && !data.groups.length ? (
        <Card className="items-start gap-2 px-4 py-6" data-testid="resolver-empty">
          <p className="flex items-center gap-2 type-headline text-label-1">
            <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden />
            {t("resolver.emptyTitle")}
          </p>
          <p className="type-callout text-label-2">{t("resolver.empty")}</p>
          <Button variant="outline" size="sm" render={<Link href="/bookings" />} nativeButton={false}>
            {t("resolver.backToBookings")}
          </Button>
        </Card>
      ) : null}

      {data?.groups.length ? (
        <>
          {!isAdmin ? <p className="type-footnote text-label-3">{t("resolver.overrideAdminOnly")}</p> : null}
          <ol className="flex flex-col gap-3" aria-label={t("resolver.listLabel")}>
            {data.groups.map((g) => (
              <li key={g.key}>
                <GroupCard
                  group={g}
                  decision={s.groups[g.key] ?? EMPTY_DECISION}
                  split={!!s.split[g.key]}
                  perConflict={s.perConflict}
                  isAdmin={isAdmin}
                  problems={byGroup.get(g.key) ?? []}
                  onDecision={(p) => setGroup(g.key, p)}
                  onSplit={(on) => setSplit(g.key, on)}
                  onConflict={setConflict}
                />
              </li>
            ))}
          </ol>
          {byGroup.get("_")?.length ? <ProblemList problems={byGroup.get("_")!} /> : null}
          <div className="sticky bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-20 lg:bottom-4">
            <Card variant="glass" className="flex-row flex-wrap items-center justify-between gap-3 px-4 py-3" data-testid="resolver-bar">
              <p className="type-callout text-label-2" aria-live="polite">
                {t("resolver.progress", { decided: prog.decided, total: prog.total })}
              </p>
              <Button onClick={() => void openReview(items)} {...busyProps(false, !items.length || blocked)} data-testid="resolver-apply">
                {t("resolver.review", { n: items.length })}
              </Button>
            </Card>
          </div>
        </>
      ) : null}

      <ReviewDialog
        review={review}
        groups={data?.groups ?? []}
        busy={apply.isPending}
        onCancel={() => setReview(null)}
        onConfirm={confirm}
      />
    </div>
  );
}

function ProblemList({ problems }: { problems: Problem[] }) {
  const { t, locale } = useI18n();
  const enter = useEnter();
  return (
    <motion.div {...enter}>
      <Alert tone="error" title={t("resolver.problemsTitle")} testId="resolver-problems">
        <ul className="list-disc pl-4">
          {problems.map((p, i) => (
            <li key={`${p.conflict_id ?? "x"}-${p.code}-${i}`}>{locale === "tr" ? p.message_tr : p.message_en}</li>
          ))}
        </ul>
      </Alert>
    </motion.div>
  );
}

function optionLabel(o: ConflictOption, locale: string, t: (k: MessageKey, v?: Record<string, string | number>) => string): string {
  const text = pickLang(o.reason, locale);
  if (text) return text;
  return t(`resolver.option.${o.kind}` as MessageKey);
}

function GroupCard({
  group: g,
  decision,
  split,
  perConflict,
  isAdmin,
  problems,
  onDecision,
  onSplit,
  onConflict,
}: {
  group: ConflictGroup;
  decision: Decision;
  split: boolean;
  perConflict: Record<number, Decision>;
  isAdmin: boolean;
  problems: Problem[];
  onDecision: (p: Partial<Decision>) => void;
  onSplit: (on: boolean) => void;
  onConflict: (id: number, p: Partial<Decision>) => void;
}) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const headingId = useId();
  const splitId = useId();
  const reasonId = useId();
  const options = choosableOptions(g, isAdmin);
  const chosen = optionOf(g, decision.optionId);
  const scopes = scopesFor(g, chosen);
  const issue = rowIssue(g, decision, isAdmin);
  const first = g.conflicts[0]!;
  const held = first.held;
  const dates = g.conflicts.map((c) => c.date);
  return (
    <Card className={cn("gap-3 px-4 py-4", problems.length && "edge-control")} data-testid={`resolver-group-${g.key}`} aria-labelledby={headingId}>
      <div className="flex flex-col gap-1">
        <h2 id={headingId} className="flex flex-wrap items-center gap-x-2 gap-y-1 type-headline text-label-1">
          {g.kind === "series" ? <Repeat className="size-4 text-label-3" aria-hidden /> : <CalendarClock className="size-4 text-label-3" aria-hidden />}
          <span>{g.room}</span>
          <span className="type-callout font-normal text-label-2">· {groupTime(g)}</span>
          <span className="rounded-full bg-fill-2 px-2 py-0.5 type-caption text-label-2">
            {g.kind === "series" ? t("resolver.series", { n: g.conflicts.length }) : g.requested ? t("resolver.request") : t("resolver.single")}
          </span>
        </h2>
        <p className="type-callout text-label-2">
          {[first.user, first.notes].filter(Boolean).join(" · ")}
        </p>
        <p className="type-footnote text-label-2">
          {held?.label ? t("resolver.heldBy", { label: held.label }) : t("resolver.heldByClass")}
          {" · "}
          {g.kind === "series" ? dates.map(dayMonth).join(", ") : fmt.long(first.date)}
        </p>
        {g.no_room_reason ? <p className="type-footnote text-status-warning-fg">{pickLang(g.no_room_reason, locale)}</p> : null}
      </div>

      {g.kind === "series" ? (
        <div className="flex min-h-11 items-center gap-3">
          <Switch id={splitId} checked={split} onCheckedChange={onSplit} data-testid={`resolver-split-${g.key}`} />
          <Label htmlFor={splitId} className="type-callout text-label-1">
            {t("resolver.split")}
          </Label>
        </div>
      ) : null}

      {split ? (
        <ul className="flex flex-col gap-2" aria-label={t("resolver.perDate")}>
          {g.conflicts.map((c) => {
            const d = perConflict[c.conflict_id] ?? EMPTY_DECISION;
            const o = optionOf(g, d.optionId);
            const iss = rowIssue(g, d, isAdmin);
            const selId = `rs-${c.conflict_id}`;
            return (
              <li key={c.conflict_id} className="flex flex-col gap-2 rounded-lg bg-fill-3 p-2.5 sm:flex-row sm:items-center">
                <label htmlFor={selId} className="w-28 shrink-0 type-callout font-medium text-label-1 tabular-nums">
                  {fmt.short(c.date)}
                </label>
                <NativeSelect id={selId} className="min-w-0 flex-1" value={d.optionId ?? ""} onChange={(e) => onConflict(c.conflict_id, { optionId: e.target.value || null })} data-testid={`resolver-date-${c.conflict_id}`}>
                  <option value="">{t("resolver.undecided")}</option>
                  {options
                    .filter((x) => x.kind !== "move_day" || x.dates.length === 1)
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {optionLabel(x, locale, t)}
                      </option>
                    ))}
                </NativeSelect>
                {needsReason(o) || o?.kind === "cancel" ? (
                  <Textarea aria-label={t("resolver.reason")} className="min-h-11 flex-1" rows={1} value={d.reason} placeholder={o?.kind === "cancel" ? (o.default_reason ?? "") : t("resolver.reasonRequired")} onChange={(e) => onConflict(c.conflict_id, { reason: e.target.value })} />
                ) : null}
                {iss ? <p className="type-footnote text-status-infeasible-fg">{t(`resolver.issue.${iss}`)}</p> : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <fieldset className="min-w-0 flex flex-col gap-1">
          <legend className="mb-1 type-footnote font-medium text-label-2">{t("resolver.options")}</legend>
          {options.map((o, i) => {
            const Icon = OPTION_ICON[o.kind];
            const id = `${g.key}-${o.id}`;
            return (
              <label key={o.id} htmlFor={id} className={cn("flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 hover:bg-fill-3 has-checked:bg-tint-soft")} data-testid={`resolver-option-${g.key}-${o.id}`}>
                <input id={id} type="radio" name={`opt-${g.key}`} value={o.id} checked={decision.optionId === o.id} onChange={() => onDecision({ optionId: o.id, scope: scopesFor(g, o).includes(decision.scope) ? decision.scope : "one" })} className="mt-1 size-4 shrink-0 accent-(--accent)" />
                <Icon className="mt-0.5 size-4 shrink-0 text-label-3" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block type-callout text-label-1">{optionLabel(o, locale, t)}</span>
                  <span className="flex flex-wrap gap-x-2 type-footnote text-label-3">
                    {i === 0 && o.kind.startsWith("move_") ? <span className="font-medium text-tint-text">{t("resolver.best")}</span> : null}
                    {o.capacity ? <span>{t("crbs.grid.seats", { n: o.capacity })}</span> : null}
                    {o.kind === "override" ? <span>{t("resolver.overrideHint")}</span> : null}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>
      )}

      {!split && chosen ? (
        <div className="flex flex-col gap-3">
          {scopes.length > 1 ? (
            <div className="flex flex-col gap-1.5">
              <span className="type-footnote font-medium text-label-2" id={`${headingId}-scope`}>
                {t("resolver.scopeLabel")}
              </span>
              <SegmentedControl
                aria-labelledby={`${headingId}-scope`}
                size="sm"
                value={decision.scope}
                onValueChange={(v) => onDecision({ scope: v as ResolveScope })}
                options={scopes.map((x) => ({ value: x, label: t(SCOPE_KEY[x]), testId: `resolver-scope-${g.key}-${x}` }))}
              />
            </div>
          ) : null}
          {chosen.kind === "cancel" || chosen.kind === "override" ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor={reasonId} className="type-footnote font-medium text-label-2">
                {chosen.kind === "override" ? t("resolver.reasonOverride") : t("resolver.reasonCancel")}
              </label>
              <Textarea id={reasonId} rows={2} value={decision.reason} maxLength={500} placeholder={chosen.kind === "cancel" ? (chosen.default_reason ?? "") : t("resolver.reasonRequired")} onChange={(e) => onDecision({ reason: e.target.value })} aria-invalid={issue === "reason" || undefined} data-testid={`resolver-reason-${g.key}`} />
              {chosen.kind === "cancel" ? <p className="type-footnote text-label-3">{t("resolver.cancelNotice")}</p> : null}
            </div>
          ) : null}
          {issue ? (
            <p className="type-footnote text-status-infeasible-fg" role="alert">
              {t(`resolver.issue.${issue}`)}
            </p>
          ) : null}
        </div>
      ) : null}

      <AnimatePresence initial={false}>{problems.length ? <ProblemList key="p" problems={problems} /> : null}</AnimatePresence>
    </Card>
  );
}

function ResultCard({ result }: { result: ApplyResult }) {
  const { t } = useI18n();
  const r = summarise(result);
  const rows: { key: MessageKey; n: number; testId: string }[] = [
    { key: "resolver.result.moved", n: r.moved, testId: "moved" },
    { key: "resolver.result.cancelled", n: r.cancelled, testId: "cancelled" },
    { key: "resolver.result.kept", n: r.kept, testId: "kept" },
    { key: "resolver.result.notified", n: r.notified, testId: "notified" },
    { key: "resolver.result.unnotified", n: r.unnotified, testId: "unnotified" },
  ];
  return (
    <Alert tone="success" title={t("resolver.result.title")} testId="resolver-result">
      <ul className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">
        {rows.map((x) => (
          <li key={x.testId} data-testid={`resolver-result-${x.testId}`}>
            <span className="font-semibold tabular-nums">{x.n}</span> {t(x.key)}
          </li>
        ))}
      </ul>
      {r.unnotified ? <p className="mt-1 type-footnote">{t("resolver.result.unnotifiedHint")}</p> : null}
    </Alert>
  );
}

function ReviewDialog({
  review,
  groups,
  busy,
  onCancel,
  onConfirm,
}: {
  review: { items: ApplyItem[]; dry: ApplyResult | null; unresolved: Map<number, { tr: string; en: string } | null>; auto: boolean } | null;
  groups: ConflictGroup[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const confirmRef = useRef<HTMLButtonElement>(null);
  const lines = (review?.items ?? []).map((i) => {
    const g = groups.find((x) => x.conflicts.some((c) => c.conflict_id === i.conflict_id));
    const c = g?.conflicts.find((x) => x.conflict_id === i.conflict_id);
    const o = g ? g.options.find((x) => (i.option_id ? x.id === i.option_id : x.kind === i.action)) : undefined;
    return { i, g, c, o };
  });
  const dry = review?.dry ? summarise(review.dry) : null;
  return (
    <ResponsiveDialog
      open={!!review}
      onOpenChange={(o) => !o && !busy && onCancel()}
      title={review?.auto ? t("resolver.reviewAutoTitle") : t("resolver.reviewTitle")}
      description={t("resolver.reviewLead")}
      testId="resolver-review"
      initialFocus={confirmRef}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {t("crbs.common.cancel")}
          </Button>
          <Button ref={confirmRef} onClick={onConfirm} {...busyProps(busy, !review?.items.length || !review?.dry)} data-testid="resolver-confirm">
            <BusyLabel busy={busy} label={t("busy.saving")}>
              {t("resolver.confirm", { n: review?.items.length ?? 0 })}
            </BusyLabel>
          </Button>
        </>
      }
    >
      {review && !review.items.length ? <p className="type-callout text-label-2">{t("resolver.reviewNothing")}</p> : null}
      {dry ? (
        <p className="type-callout text-label-1" data-testid="resolver-dry">
          {t("resolver.dry", { moved: dry.moved, cancelled: dry.cancelled, kept: dry.kept })}
        </p>
      ) : review?.items.length ? (
        <Loading label={t("resolver.checking")} className="py-2" />
      ) : null}
      <ul className="flex flex-col gap-1.5">
        {lines.map(({ i, g, c, o }) => (
          <li key={`${i.conflict_id}-${i.scope}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg bg-fill-3 px-3 py-2 type-callout">
            <span className="font-medium text-label-1">{g?.room}</span>
            <span className="text-label-2 tabular-nums">{c ? `${fmt.short(c.date)} · ${c.time}` : ""}</span>
            {i.scope !== "one" ? <span className="rounded-full bg-fill-2 px-2 type-caption text-label-2">{t(SCOPE_KEY[i.scope])}</span> : null}
            <ArrowRight className="size-3.5 text-label-3" aria-hidden />
            <span className="min-w-0 text-label-1">{o ? optionLabel(o, locale, t) : i.action}</span>
          </li>
        ))}
      </ul>
      {review?.unresolved.size ? (
        <div className="flex flex-col gap-1">
          <p className="type-footnote font-medium text-label-2">{t("resolver.unresolved", { n: review.unresolved.size })}</p>
          <ul className="list-disc pl-4 type-footnote text-label-2">
            {[...review.unresolved.entries()].map(([id, reason]) => {
              const g = groups.find((x) => x.conflicts.some((c) => c.conflict_id === id));
              const c = g?.conflicts.find((x) => x.conflict_id === id);
              return (
                <li key={id}>
                  {g?.room} {c ? fmt.short(c.date) : ""}: {reason ? pickLang(reason, locale) : t("resolver.noSuggestion")}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </ResponsiveDialog>
  );
}
