"use client";
/**
 * /programs/new and /programs/new/[draftId] (docs/design/v2/phase19-program-wizard.md, motion.md §3.11): create a
 * programme with no file to import. The landing lists "Taslaklarım" (server drafts, resumable on any device,
 * "kaldığınız yer: Kohortlar") and "Oluşturulanlar" (committed programmes, with their 30-day undo). A draft is
 * a vertical rail of the eight server steps (✓ / ⚠ n / ✕ n / –) with the autosave line, the step content and a
 * preview column; on phones a compact "6/8 · Odalar" stepper that opens the step list as a bottom sheet, and a
 * floating Geri / Devam capsule. Nothing touches the term until the last step commits the draft.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ListOrdered, Plus, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { Alert } from "@/components/ui/alert";
import { Button, IconButton } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useRooms, useTerms } from "@/lib/api/hooks";
import { dk, draftsApi, useDraftList, type CommitOut, type DraftListItem, type DraftOut, type DraftPrecheck, type Validation } from "@/lib/api/program-drafts";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce, useReducedTransparency } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { CommittedView, GenerateStep, StepGlyph, statusWord } from "./generate-step";
import { CohortsStep, ConstraintsStep, CoursesStep, InstructorsStep, ProgramStep, RoomsStep, SectionsStep } from "./steps";
import { errorText, useWizard, type SaveState } from "./use-wizard";
import { STEPS, newPayload, parseStep, stepState, type Payload, type Step } from "./wizard-model";

function relTime(at: string, locale: string): string {
  const s = Math.round((Date.now() - new Date(at).getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale === "tr" ? "tr" : "en", { numeric: "auto" });
  return s < 60 ? rtf.format(0, "minute") : s < 3600 ? rtf.format(-Math.round(s / 60), "minute") : s < 86_400 ? rtf.format(-Math.round(s / 3600), "hour") : rtf.format(-Math.round(s / 86_400), "day");
}

export function SaveStatus({ save, onRetry }: { save: SaveState; onRetry: () => void }) {
  const { t, locale } = useI18n();
  // text swap only: a ✓ animation on every 800 ms save would be motion on a frequent action (motion.md §3.11)
  const warn = save.kind === "error" || save.kind === "offline";
  return (
    <p role="status" aria-live="polite" className={cn("type-footnote", warn ? "text-status-warning-fg" : "text-label-2")} data-testid="save-status" data-state={save.kind}>
      {save.kind === "saving" ? t("programWizard.save.saving")
        : save.kind === "offline" ? t("programWizard.save.offline")
        : save.kind === "readonly" ? t(`programWizard.save.readonly.${save.status}`)
        : save.kind === "error" ? (
          <>
            {t("programWizard.save.error")} <Button variant="link" size="xs" onClick={onRetry}>{t("common.retry")}</Button>
            <span className="block text-label-2">{save.message}</span>
          </>
        ) : save.kind === "saved" ? t("programWizard.save.saved", { when: relTime(save.at, locale) })
        : t("programWizard.save.server")}
    </p>
  );
}

function railLine(t: ReturnType<typeof useI18n>["t"], n: (v: number) => string, step: Step, p: Payload, v: Validation): string | undefined {
  const s = v.summary;
  switch (step) {
    case "program": return p.program.name || undefined;
    case "courses": return s.courses ? t("programWizard.rail.courses", { n: n(s.courses), ects: n(s.ects) }) : undefined;
    case "sections": return s.sections ? t("programWizard.rail.sections", { n: n(s.sections), joint: n(s.joint_links) }) : undefined;
    case "instructors": return s.people ? t("programWizard.rail.people", { n: n(s.people), fresh: n(s.new_people) }) : undefined;
    case "cohorts": return s.cohorts ? t("programWizard.rail.cohorts", { n: n(s.cohorts) }) : undefined;
    case "rooms": return s.weekly_hours ? t("programWizard.rail.hours", { n: n(s.weekly_hours) }) : undefined;
    default: return undefined;
  }
}

function StepList({ p, v, step, go }: { p: Payload; v: Validation; step: Step; go: (s: Step) => void }) {
  const { t, n } = useI18n();
  const reduce = useReduce();
  const solid = useReducedTransparency();
  return (
    <ol className="flex flex-col gap-0.5">
      {STEPS.map((s, i) => {
        const st = stepState(v, s);
        const on = s === step;
        const word = statusWord(t, st);
        const line = railLine(t, n, s, p, v);
        return (
          <li key={s}>
            <Button
              variant="ghost"
              className="relative h-auto min-h-11 w-full justify-start rounded-xl px-2.5 py-2 text-left"
              aria-current={on ? "step" : undefined}
              aria-label={`${i + 1}. ${t(`programWizard.step.${s}`)}, ${word}`}
              aria-keyshortcuts={`Alt+${i + 1}`}
              onClick={() => go(s)}
              data-testid={`rail-${s}`}
              data-status={st?.status ?? "empty"}
            >
              {/* rail pill: one element that glides to the step (pattern 2); reduced motion: jumps */}
              {on ? <motion.span layoutId="wizard-rail" aria-hidden className={cn("absolute inset-0 -z-10 rounded-xl bg-tint-soft", solid && "border border-hairline-strong")} transition={reduce ? { duration: 0 } : springs.glassMorph} /> : null}
              <StepGlyph status={st?.status} />
              <span className="flex min-w-0 flex-col">
                <span className="type-callout whitespace-normal text-label-1">{i + 1} {t(`programWizard.step.${s}`)}</span>
                {line ? <span className="truncate type-caption text-label-2">{line}</span> : null}
                {st && (st.status === "error" || st.status === "warning") ? <span className="type-caption text-label-2">{word}</span> : null}
              </span>
            </Button>
          </li>
        );
      })}
    </ol>
  );
}

function Preview({ p, v, termCode }: { p: Payload; v: Validation; termCode: string }) {
  const { t, n } = useI18n();
  const s = v.summary;
  return (
    <div className="flex flex-col gap-1" data-testid="wizard-preview">
      <p className="type-headline">{p.program.name || t("programWizard.preview.noName")}</p>
      <p className="type-footnote text-label-2">{[termCode, p.program.faculty_name].filter(Boolean).join(" · ")}</p>
      <p className="type-callout tabular-nums">{t("programWizard.preview.counts", { courses: n(s.courses), sections: n(s.sections), people: n(s.people), hours: n(s.weekly_hours) })}</p>
      {s.joint_links ? <p className="type-footnote text-label-2">{t("programWizard.preview.joint", { n: n(s.joint_links) })}</p> : null}
      {s.new_people ? <p className="type-footnote text-label-2">{t("programWizard.preview.newPeople", { n: n(s.new_people) })}</p> : null}
      <p className="type-footnote text-label-2">{p.program.evening ? t("programWizard.preview.evening") : t("programWizard.preview.day")}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ landing (drafts + committed) */

function DraftRow({ d, onDelete }: { d: DraftListItem; onDelete?: () => void }) {
  const { t, locale } = useI18n();
  const step = parseStep(d.step);
  const when = d.updated_at ? new Date(d.updated_at).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" }) : null;
  return (
    <li className="flex flex-wrap items-center gap-2 border-b border-hairline py-2 type-callout" data-testid="draft-row" data-draft-id={d.id}>
      <span className="min-w-0 flex-1">
        <span className="font-semibold">{d.title || t("programWizard.preview.noName")}</span>
        <span className="block type-footnote text-label-2">
          {[d.term_code, d.status === "draft" ? t("programWizard.resumeAt", { step: t(`programWizard.step.${step}`) }) : t(`programWizard.status.${d.status}`), t("programWizard.landing.rowCounts", { courses: d.summary.courses, sections: d.summary.sections }), when].filter(Boolean).join(" · ")}
        </span>
      </span>
      <Button size="sm" variant="secondary" className="max-md:h-11" render={<Link href={`/programs/new/${d.id}${d.status === "draft" ? `?step=${step}` : ""}`} />} nativeButton={false} data-testid="draft-open">
        {d.status === "draft" ? t("programWizard.resume") : t("programWizard.landing.view")}
      </Button>
      {onDelete ? <IconButton size="sm" className="max-md:size-11" label={t("programWizard.forget", { name: d.title || "—" })} onClick={onDelete}><Trash2 aria-hidden /></IconButton> : null}
    </li>
  );
}

function Landing() {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const qc = useQueryClient();
  const terms = useTerms();
  const drafts = useDraftList("draft");
  const committed = useDraftList("committed");
  const sorted = useMemo(() => [...(terms.data ?? [])].sort((a, b) => (b.start_date ?? "").localeCompare(a.start_date ?? "")), [terms.data]);
  const [termId, setTermId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const chosen = termId || (sorted[0] ? String(sorted[0].id) : "");
  const start = async () => {
    if (!chosen) return;
    setBusy(true);
    try {
      const d = await draftsApi.create(Number(chosen), newPayload() as unknown as Record<string, unknown>, "program");
      void qc.invalidateQueries({ queryKey: ["program-drafts", "list"] });
      router.push(`/programs/new/${d.id}?step=program`);
    } catch (e) {
      toast.error(errorText(e, lang));
      setBusy(false);
    }
  };
  const remove = async (d: DraftListItem) => {
    try {
      await draftsApi.remove(d.id);
      void qc.invalidateQueries({ queryKey: ["program-drafts", "list"] });
      toast.success(t("programWizard.landing.deleted", { name: d.title || "—" }));
    } catch (e) {
      toast.error(errorText(e, lang));
    }
  };
  return (
    <div className="flex max-w-3xl flex-col gap-6" data-testid="wizard-landing">
      <PageHeader title={t("programWizard.title")} subtitle={t("programWizard.subtitle")} />
      <p className="type-callout text-label-2">{t("programWizard.intro")}</p>
      <section aria-labelledby="new-title" className="flex flex-col gap-2 rounded-2xl border border-hairline p-4">
        <h2 id="new-title" className="type-headline">{t("programWizard.landing.newTitle")}</h2>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-col gap-1 type-callout">
            {t("programWizard.term.label")}
            <NativeSelect className="sm:w-56" value={chosen} onChange={(e) => setTermId(e.target.value)} data-testid="wizard-term">
              {sorted.map((x) => <option key={x.id} value={x.id}>{x.code}{x.name && x.name !== x.code ? ` · ${x.name}` : ""}</option>)}
            </NativeSelect>
          </label>
          <Button onClick={() => void start()} disabled={!chosen || busy} aria-busy={busy || undefined} data-testid="wizard-start"><Plus aria-hidden />{t("programWizard.start")}</Button>
        </div>
        <p className="type-footnote text-label-2">{t("programWizard.term.hint")}</p>
      </section>
      <section aria-labelledby="drafts-title" className="flex flex-col gap-2">
        <h2 id="drafts-title" className="type-headline">{t("programWizard.drafts")}</h2>
        {drafts.isLoading ? <Skeleton className="h-16 w-full" /> : drafts.isError ? <Alert tone="error">{errorText(drafts.error, lang)}</Alert> : drafts.data?.items.length ? (
          <ul className="flex flex-col" data-testid="draft-list">
            {drafts.data.items.map((d) => <DraftRow key={d.id} d={d} onDelete={() => void remove(d)} />)}
          </ul>
        ) : (
          <p className="type-footnote text-label-2" data-testid="no-drafts">{t("programWizard.noDrafts")}</p>
        )}
      </section>
      <section aria-labelledby="committed-title" className="flex flex-col gap-2">
        <h2 id="committed-title" className="type-headline">{t("programWizard.landing.committed")}</h2>
        <p className="type-footnote text-label-2">{t("programWizard.landing.committedHint")}</p>
        {committed.data?.items.length ? (
          <ul className="flex flex-col" data-testid="committed-list">
            {committed.data.items.map((d) => <DraftRow key={d.id} d={d} />)}
          </ul>
        ) : committed.isLoading ? <Skeleton className="h-10 w-full" /> : (
          <p className="type-footnote text-label-2">{t("programWizard.landing.noCommitted")}</p>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ the wizard */

export function ProgramWizard({ draftId }: { draftId?: number }) {
  const { can, loading } = usePermissions();
  const { t } = useI18n();
  if (loading) return <Skeleton className="h-96 w-full" />;
  if (!can("planning.edit")) return <EmptyState title={t("programWizard.forbiddenTitle")} description={t("programWizard.forbidden")} />;
  return draftId ? <DraftLoader id={draftId} /> : <Landing />;
}

function DraftLoader({ id }: { id: number }) {
  const { t, locale } = useI18n();
  const q = useQuery({ queryKey: dk.draft(id), queryFn: () => draftsApi.get(id), staleTime: Infinity, refetchOnWindowFocus: false, retry: false });
  if (q.isLoading) return <div className="flex flex-col gap-3" aria-busy><Skeleton className="h-9 w-72" /><Skeleton className="h-96 w-full" /></div>;
  if (q.isError || !q.data) {
    return <EmptyState title={t("programWizard.missingTitle")} description={errorText(q.error, locale === "tr" ? "tr" : "en")} actions={<Button render={<Link href="/programs/new" />} nativeButton={false}>{t("programWizard.drafts")}</Button>} />;
  }
  return <WizardBody key={id} initial={q.data} />;
}

function WizardBody({ initial }: { initial: DraftOut }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const params = useSearchParams();
  const reduce = useReduce();
  const { draft, update, save, flush, setStep, revalidate, overwritten, dismissOverwritten } = useWizard(initial.id, initial);
  const terms = useTerms();
  const rooms = useRooms();
  const termCode = terms.data?.find((x) => x.id === draft.termId)?.code ?? `#${draft.termId}`;
  const step = parseStep(params.get("step") ?? initial.step);
  const [dir, setDir] = useState(1);
  const [stepsOpen, setStepsOpen] = useState(false);
  const [summary, setSummary] = useState<string[] | null>(null);
  const [precheck, setPrecheck] = useState<DraftPrecheck | null>(null);
  const [committed, setCommitted] = useState<CommitOut | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const v = draft.validation;
  const p = draft.payload;

  const go = (next: Step) => {
    setDir(STEPS.indexOf(next) >= STEPS.indexOf(step) ? 1 : -1);
    setSummary(null);
    setStepsOpen(false);
    setStep(next);
    router.replace(`/programs/new/${draft.id}?step=${next}`, { scroll: false });
    window.requestAnimationFrame(() => heading.current?.focus());
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && /^[1-8]$/.test(e.key)) {
        e.preventDefault();
        go(STEPS[Number(e.key) - 1]!);
      } else if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        void flush();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (committed || draft.status !== "draft") {
    return (
      <div className="flex flex-col gap-4" data-testid="program-wizard">
        <PageHeader title={p.program.name || t("programWizard.title")} subtitle={termCode} />
        <CommittedView draftId={draft.id} termId={draft.termId} termCode={termCode} title={p.program.name} status={draft.status === "undone" ? "undone" : "committed"} created={draft.created} result={committed} />
      </div>
    );
  }

  /** Devam with errors: an error summary with links to each field, focused (GOV.UK pattern, spec §10) */
  const next = async (force = false) => {
    if (!force) {
      const fresh = await revalidate(step).catch(() => null);
      const errs = (fresh ?? v).issues.filter((i) => i.step === step && i.level === "error");
      if (errs.length) {
        setSummary(errs.map((i) => i.path));
        window.requestAnimationFrame(() => summaryRef.current?.focus());
        return;
      }
    }
    const i = STEPS.indexOf(step);
    if (i < STEPS.length - 1) go(STEPS[i + 1]!);
  };
  const back = () => {
    const i = STEPS.indexOf(step);
    if (i > 0) go(STEPS[i - 1]!);
  };
  const focusField = (path: string) => {
    const el = document.querySelector<HTMLElement>(`[data-path="${CSS.escape(path)}"]`);
    const target = el?.matches("input,select,textarea,button") ? el : el?.querySelector<HTMLElement>("input,select,textarea,button");
    if (target) {
      target.focus();
      target.classList.add("t-input");
      target.classList.remove("is-shaking");
      void target.offsetWidth;
      target.classList.add("is-shaking");
    }
  };

  const props = { p, update, v, termId: draft.termId };
  const body =
    step === "program" ? <ProgramStep {...props} termCode={termCode} />
    : step === "courses" ? <CoursesStep {...props} draftId={draft.id} />
    : step === "sections" ? <SectionsStep {...props} />
    : step === "instructors" ? <InstructorsStep {...props} />
    : step === "cohorts" ? <CohortsStep {...props} />
    : step === "rooms" ? <RoomsStep {...props} rooms={rooms.data ?? []} />
    : step === "constraints" ? <ConstraintsStep {...props} draftId={draft.id} precheck={precheck} onPrecheck={setPrecheck} onFix={go} />
    : <GenerateStep draftId={draft.id} termId={draft.termId} termCode={termCode} p={p} v={v} flush={flush} onFix={go} onCommitted={setCommitted} />;

  const errs = summary ? v.issues.filter((i) => i.step === step && i.level === "error") : [];
  const idx = STEPS.indexOf(step);

  return (
    <div className="flex flex-col gap-4" data-testid="program-wizard" data-draft-id={draft.id}>
      <PageHeader title={p.program.name || t("programWizard.title")} subtitle={t("programWizard.draftLine", { term: termCode })} />
      {/* phones and tablets: the compact stepper (R9); the step list opens as a bottom sheet */}
      <div className="flex flex-col gap-2 lg:hidden" data-testid="wizard-stepper">
        <Button variant="outline" className="h-auto min-h-11 justify-between gap-3 py-2" onClick={() => setStepsOpen(true)} aria-haspopup="dialog" data-testid="stepper-open">
          <span className="inline-flex min-w-0 items-center gap-2">
            <StepGlyph status={stepState(v, step)?.status} />
            <span className="truncate">{t("programWizard.stepper", { i: idx + 1, total: STEPS.length, step: t(`programWizard.step.${step}`) })}</span>
          </span>
          <ListOrdered aria-hidden />
        </Button>
        <Progress value={((idx + 1) / STEPS.length) * 100} aria-label={t("programWizard.rail.label")} />
        <SaveStatus save={save} onRetry={() => void flush()} />
      </div>
      <Sheet open={stepsOpen} onOpenChange={setStepsOpen}>
        <SheetContent side="bottom" className="max-h-[92dvh] gap-2 overflow-y-auto p-4" data-testid="stepper-sheet">
          <SheetHeader className="p-0"><SheetTitle>{t("programWizard.rail.label")}</SheetTitle></SheetHeader>
          <nav aria-label={t("programWizard.rail.label")}><StepList p={p} v={v} step={step} go={go} /></nav>
        </SheetContent>
      </Sheet>
      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[16rem_minmax(0,1fr)_18rem]">
        <nav aria-label={t("programWizard.rail.label")} className="hidden flex-col gap-3 lg:sticky lg:top-4 lg:flex lg:self-start" data-testid="wizard-rail">
          <StepList p={p} v={v} step={step} go={go} />
          <div className="border-t border-hairline pt-2">
            <SaveStatus save={save} onRetry={() => void flush()} />
            <p className="type-caption text-label-3">{t("programWizard.rail.draftNote", { term: termCode })}</p>
          </div>
        </nav>
        <main className="flex min-w-0 flex-col gap-4 max-lg:pb-24" aria-labelledby="wizard-step-title">
          <details className="rounded-xl border border-hairline px-3 py-2 xl:hidden" data-testid="preview-disclosure">
            <summary className="min-h-11 cursor-pointer content-center type-callout font-semibold md:min-h-8">{t("programWizard.preview.label")}</summary>
            <Preview p={p} v={v} termCode={termCode} />
          </details>
          <h2 id="wizard-step-title" ref={heading} tabIndex={-1} className="type-title-2 outline-hidden">
            {idx + 1}. {t(`programWizard.step.${step}`)}
          </h2>
          {overwritten.length ? (
            <Alert tone="info" data-testid="overwritten" action={<Button size="sm" variant="ghost" onClick={dismissOverwritten}>{t("common.close")}</Button>}>
              {t("programWizard.conflict", { n: n(overwritten.length) })}
            </Alert>
          ) : null}
          {errs.length ? (
            <div ref={summaryRef} tabIndex={-1} role="alert" className="flex flex-col gap-1 rounded-xl border border-status-infeasible-border bg-status-infeasible p-3 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="error-summary">
              <p className="type-callout font-semibold text-status-infeasible-fg">{t("programWizard.errorSummary", { n: n(errs.length) })}</p>
              <ul className="flex flex-col gap-0.5">
                {errs.map((i, k) => (
                  <li key={`${i.path}-${k}`}>
                    <Button variant="link" size="xs" className="h-auto! whitespace-normal text-left text-status-infeasible-fg" onClick={() => focusField(i.path)}>{i.text[lang] || i.text.tr}</Button>
                  </li>
                ))}
              </ul>
              <div><Button size="sm" variant="ghost" onClick={() => void next(true)} data-testid="continue-anyway">{t("programWizard.continueAnyway")}</Button></div>
            </div>
          ) : null}
          {/* wizard.step-change: enter-only, 8 px from the travel direction; the old step leaves instantly */}
          <motion.div key={step} initial={reduce ? { opacity: 0 } : { opacity: 0, x: 8 * dir }} animate={{ opacity: 1, x: 0 }} transition={reduce ? tween.reduced : springs.smooth}>
            {body}
          </motion.div>
          {/* footer: inline on desktop; a floating capsule above the tab bar on phones (M-05, M-06) */}
          <div className="flex justify-between gap-2 border-t border-hairline pt-3 max-lg:sticky max-lg:bottom-[calc(5.25rem+env(safe-area-inset-bottom))] max-lg:z-20 max-lg:rounded-full max-lg:border-0 max-lg:glass-chrome max-lg:p-1.5" data-testid="wizard-footer">
            <Button variant="ghost" onClick={back} disabled={step === "program"} data-testid="wizard-back"><ChevronLeft aria-hidden />{t("common.back")}</Button>
            {step !== "generate" ? <Button onClick={() => void next()} data-testid="wizard-next">{t("common.next")}<ChevronRight aria-hidden /></Button> : null}
          </div>
        </main>
        <aside className="hidden rounded-2xl border border-hairline p-4 xl:sticky xl:top-4 xl:block xl:self-start" aria-label={t("programWizard.preview.label")}>
          <Preview p={p} v={v} termCode={termCode} />
        </aside>
      </div>
    </div>
  );
}
