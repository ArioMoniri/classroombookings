"use client";

import { AlertTriangle, Check, ChevronLeft, ChevronRight, CloudOff, Loader2, Redo2, Undo2 } from "lucide-react";
import { motion } from "motion/react";
import { springs, useReduce } from "@/lib/motion";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api/endpoints";
import { sk } from "@/lib/api/studio-hooks";
import { STUDIO_STEPS, type StudioKind, type StudioStep } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { CheckStep } from "./check-step";
import { ClassesStep } from "./classes-step";
import { GenerateButton, GenerateStep } from "./generate-step";
import { PresetMenu } from "./presets";
import { RulesStep } from "./rules-step";
import { ScopeStep } from "./scope-step";
import { StudioProvider, useStudio, useStudioStore } from "./studio-context";
import { SummaryPanel } from "./summary-panel";
import type { BuilderPrefill } from "./template-gallery";
import { GenerateProvider, useGenerate } from "./use-generate";

const STEP_KEY: Record<StudioStep, MessageKey> = { scope: "studio.step.scope", classes: "studio.step.classes", rules: "studio.step.rules", check: "studio.step.check", run: "studio.step.run" };

export function StudioView() {
  const { term, isLoading } = useActiveTerm();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const kind: StudioKind = params.get("kind") === "EXAM" ? "EXAM" : "COURSE";
  const setKind = (k: StudioKind) => {
    const next = new URLSearchParams(params.toString());
    if (k === "EXAM") next.set("kind", "EXAM");
    else next.delete("kind");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  if (!term)
    return (
      <div className="space-y-4" data-testid="generate" aria-busy={isLoading}>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  return (
    <StudioProvider key={`${term.id}:${kind}`} termId={term.id} kind={kind} term={term}>
      <GenerateProvider>
        <StudioShell onKind={setKind} />
      </GenerateProvider>
    </StudioProvider>
  );
}

function useStepStatus(): Record<StudioStep, string> {
  const { t, n } = useI18n();
  const { summary, local } = useStudio();
  const active = useStudioStore((s) => s.activeRun);
  const weeks = summary.weeks;
  return {
    scope: local.horizon === "TERM" ? t("studio.stepStatus.term", { n: weeks.length }) : weeks.length ? t("studio.stepStatus.weeks", { from: weeks[0], to: weeks[weeks.length - 1], n: weeks.length }) : t("studio.stepStatus.noWeeks"),
    classes: t("studio.stepStatus.classes", { in: n(summary.classesIn), out: n(summary.classesOut) }),
    rules: `${t("studio.stepStatus.rules", { must: n(summary.must), try: n(summary.tryTo) })}${summary.problems ? ` · ⚠${summary.problems}` : ""}`,
    check: t(summary.readiness === "ready" ? "studio.check.ready" : summary.readiness === "needs_look" ? "studio.check.needsLook" : summary.readiness === "blocked" ? "studio.check.blocked" : summary.readiness === "checking" ? "studio.check.checking" : "studio.check.unknown"),
    run: active ? t("studio.stepStatus.running", { id: active.runId }) : t("studio.stepStatus.ready"),
  };
}

function SaveStatus() {
  const { t } = useI18n();
  const { state, flush } = useStudio();
  const s = state.status;
  if (s === "saving" || state.dirty.length)
    return (
      <span className="inline-flex items-center gap-1 text-xs text-label-2" role="status" data-testid="save-status" data-state="saving">
        <Loader2 className="size-3 animate-spin" aria-hidden /> {t("studio.save.saving")}
      </span>
    );
  if (s === "error")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-status-infeasible-fg" role="status" data-testid="save-status" data-state="error">
        <CloudOff className="size-3" aria-hidden /> {t("studio.save.error")}
        <button type="button" className="underline" onClick={() => void flush()}>
          {t("common.retry")}
        </button>
      </span>
    );
  if (s === "saved")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-label-2" role="status" data-testid="save-status" data-state="saved">
        <Check className="size-3" aria-hidden /> {t("studio.save.saved")}
      </span>
    );
  return null;
}

function UndoRedo({ className }: { className?: string }) {
  const { t } = useI18n();
  const undo = useStudioStore((s) => s.undo);
  const redo = useStudioStore((s) => s.redo);
  const canUndo = useStudioStore((s) => s.past.length > 0);
  const canRedo = useStudioStore((s) => s.future.length > 0);
  const run = async (fn: () => Promise<string | null>, key: "studio.undone" | "studio.redone") => {
    const label = await fn();
    if (label) toast(t(key, { label }));
  };
  return (
    <div className={cn("flex items-center gap-1", className)}>
      <Button size="sm" variant="ghost" onClick={() => void run(undo, "studio.undone")} disabled={!canUndo} aria-keyshortcuts="Meta+Z Control+Z" data-testid="studio-undo">
        <Undo2 aria-hidden /> {t("common.undo")}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => void run(redo, "studio.redone")} disabled={!canRedo} aria-keyshortcuts="Meta+Shift+Z Control+Shift+Z">
        <Redo2 aria-hidden /> {t("studio.redo")}
      </Button>
    </div>
  );
}

function ConflictBanner() {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const { state, dispatch, termId, kind, flush } = useStudio();
  const [now] = useState(() => Date.now());
  if (state.status === "conflict" && state.conflict) {
    const when = state.conflict.updated_at ? new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(Math.round((new Date(state.conflict.updated_at).getTime() - now) / 60_000), "minute") : "";
    return (
      <div role="alert" className="flex flex-wrap items-center gap-2 rounded-lg border border-status-warning-border bg-status-warning px-3 py-2 text-sm text-status-warning-fg" data-testid="conflict-banner">
        <AlertTriangle className="size-4" aria-hidden />
        <span className="flex-1">{t("studio.save.conflict", { when })}</span>
        <Button size="sm" variant="outline" onClick={() => state.conflict && dispatch({ type: "hydrate", draft: state.conflict })}>
          {t("studio.save.loadTheirs")}
        </Button>
        <Button
          size="sm"
          onClick={() => {
            if (state.conflict) dispatch({ type: "keepMine", current: state.conflict });
            window.setTimeout(() => void flush(), 0);
          }}
        >
          {t("studio.save.keepMine")}
        </Button>
      </div>
    );
  }
  if (state.status === "error")
    return (
      <div role="alert" className="flex flex-wrap items-center gap-2 rounded-lg border border-status-infeasible-border bg-status-infeasible px-3 py-2 text-sm text-status-infeasible-fg" data-testid="save-error-banner">
        <CloudOff className="size-4" aria-hidden />
        <span className="flex-1">
          {t("studio.save.errorLong")} {state.error ? <span className="text-xs">({state.error})</span> : null}
        </span>
        <Button size="sm" variant="outline" onClick={() => void flush()}>
          {t("common.retry")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            const d = await api.studio.draft(termId, kind);
            qc.setQueryData(sk.draft(termId, kind), d);
            dispatch({ type: "hydrate", draft: d });
          }}
        >
          {t("studio.save.discard")}
        </Button>
      </div>
    );
  return null;
}

function StudioShell({ onKind }: { onKind: (k: StudioKind) => void }) {
  const { t } = useI18n();
  const reduce = useReduce();
  const { step, goStep, advanced, setAdvanced, store, state } = useStudio();
  const { generate } = useGenerate();
  const status = useStepStatus();
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [prefill, setPrefill] = useState<BuilderPrefill | null>(null);
  const index = STUDIO_STEPS.indexOf(step);
  // forward steps enter from the right, back steps from the left
  const [prevIndex, setPrevIndex] = useState(index);
  const [stepDir, setStepDir] = useState(1);
  if (index !== prevIndex) {
    setStepDir(index > prevIndex ? 1 : -1);
    setPrevIndex(index);
  }
  // the class table needs the width: the summary collapses to a 48 px rail below 1800 px
  const collapse = step === "classes";

  // keyboard: Alt+1…5, [ / ], ⌘↵ generate, ⌘Z / ⌘⇧Z, ⌘⇧A advanced
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      const mod = e.metaKey || e.ctrlKey;
      if (e.altKey && /^Digit[1-5]$/.test(e.code)) {
        e.preventDefault();
        goStep(STUDIO_STEPS[Number(e.code.slice(5)) - 1]);
        return;
      }
      if (mod && e.key === "Enter" && el?.tagName !== "TEXTAREA") {
        e.preventDefault();
        void generate();
        return;
      }
      if (mod && e.shiftKey && (e.key === "a" || e.key === "A")) {
        e.preventDefault();
        setAdvanced(!advanced);
        return;
      }
      if (typing) return;
      if (mod && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        void (e.shiftKey ? store.getState().redo() : store.getState().undo()).then((label) => label && toast(t(e.shiftKey ? "studio.redone" : "studio.undone", { label })));
        return;
      }
      if (!mod && !e.altKey && e.key === "[" && index > 0) goStep(STUDIO_STEPS[index - 1]);
      if (!mod && !e.altKey && e.key === "]" && index < STUDIO_STEPS.length - 1) goStep(STUDIO_STEPS[index + 1]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goStep, generate, setAdvanced, advanced, store, index, t]);

  const loading = state.server === null;
  const body = loading ? (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  ) : step === "scope" ? (
    <ScopeStep onKind={onKind} />
  ) : step === "classes" ? (
    <ClassesStep
      onMakeRule={(ids) => {
        setPrefill({ templateId: "same_room_every_week", eventIds: ids });
        goStep("rules");
      }}
    />
  ) : step === "rules" ? (
    <RulesStep builderPrefill={prefill} onBuilderConsumed={() => setPrefill(null)} />
  ) : step === "check" ? (
    <CheckStep />
  ) : (
    <GenerateStep />
  );

  return (
    <div className="mx-auto w-full max-w-[1600px] pb-24 xl:pb-0" data-testid="generate">
      <PageHeader title={t("studio.title")} subtitle={t("studio.subtitle")} actions={<SaveStatus />} />

      <div className="mb-3 space-y-2">
        <ConflictBanner />
      </div>

      {/* < md: segmented progress + "2/5 · Classes" */}
      <div className="mb-3 md:hidden" data-testid="mobile-progress">
        <div className="grid grid-cols-5 gap-1" aria-hidden>
          {STUDIO_STEPS.map((s, i) => (
            <span key={s} className={cn("h-1.5 rounded-full", i <= index ? "bg-tint" : "bg-fill-2")} />
          ))}
        </div>
        <p className="mt-1.5 text-sm font-medium">
          {t("studio.nav.stepOf", { n: index + 1, total: STUDIO_STEPS.length })} · {t(STEP_KEY[step])}
        </p>
      </div>

      {/* md–xl: horizontal step tabs */}
      <nav aria-label={t("studio.nav.label")} className="mb-4 hidden overflow-x-auto md:block xl:hidden">
        <ol className="flex gap-1">
          {STUDIO_STEPS.map((s, i) => (
            <li key={s} className="shrink-0">
              <button type="button" onClick={() => goStep(s)} aria-current={s === step ? "step" : undefined} aria-label={`${t(STEP_KEY[s])}, ${status[s]}`} className={cn("flex flex-col rounded-xl bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)] px-3 py-1.5 text-left text-sm", s === step ? "bg-tint-soft text-tint-text" : "hover:bg-fill-2")} data-testid={`tab-step-${s}`}>
                <span className="font-medium">
                  {i + 1} {t(STEP_KEY[s])}
                </span>
                <span className="max-w-48 truncate text-[11px] text-label-2">{status[s]}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <div
        className={cn(
          "grid gap-6",
          collapse
            ? "xl:grid-cols-[200px_minmax(0,1fr)_var(--studio-summary-collapsed-w)] min-[1800px]:grid-cols-[var(--studio-rail-w)_minmax(0,1200px)_360px] min-[1800px]:justify-center"
            : "xl:grid-cols-[200px_minmax(0,1fr)_304px] 2xl:grid-cols-[var(--studio-rail-w)_minmax(0,1200px)_360px] 2xl:justify-center",
        )}
      >
        <div className="hidden xl:block">
          <div className="sticky top-4 space-y-4">
            <nav aria-label={t("studio.nav.label")}>
              <ol className="space-y-1">
                {STUDIO_STEPS.map((s, i) => {
                  const current = s === step;
                  return (
                    <li key={s}>
                      <button type="button" onClick={() => goStep(s)} aria-current={current ? "step" : undefined} aria-label={`${t(STEP_KEY[s])}, ${status[s]}`} className={cn("flex min-h-14 w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left outline-none focus-visible:outline-2 focus-visible:outline-(--focus)", current ? "bg-fill-1 text-label-1" : "hover:bg-fill-3")} data-testid={`rail-step-${s}`}>
                        <span className={cn("mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums", current ? "bg-tint text-tint-foreground" : "bg-fill-2 text-label-2")}>{i + 1}</span>
                        <span className="min-w-0">
                          <span className="block text-sm font-medium">{t(STEP_KEY[s])}</span>
                          <span className="block truncate text-xs text-label-2" aria-hidden>
                            {status[s]}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
            <div className="space-y-2 border-t pt-3">
              <PresetMenu className="w-full justify-start" />
              <UndoRedo />
              <label className="flex items-center gap-2 px-1 text-sm">
                <Switch checked={advanced} onCheckedChange={setAdvanced} data-testid="advanced-toggle" aria-keyshortcuts="Meta+Shift+A" />
                {t("studio.advanced")}
              </label>
            </div>
          </div>
        </div>

        <section aria-labelledby="studio-step-title" className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 id="studio-step-title" className="mr-auto type-title-2 text-label-1">
              {index + 1} · {t(STEP_KEY[step])}
            </h2>
            <div className="flex items-center gap-2 xl:hidden">
              <UndoRedo />
              <label className="flex items-center gap-2 text-xs">
                <Switch size="sm" checked={advanced} onCheckedChange={setAdvanced} />
                {t("studio.advanced")}
              </label>
            </div>
          </div>
          {/* Enter-only, transform-only step change (motion.md §3.4): no exit wait, and no opacity on a wrapper
              that holds glass cards (backdrop-root rule G6). Reduced motion: no travel. */}
          <motion.div key={step} data-testid={`studio-step-${step}`} initial={reduce ? false : { x: stepDir * 8 }} animate={{ x: 0 }} transition={springs.smooth}>
            {body}
          </motion.div>
          {collapse ? (
            <div className="sticky bottom-3 z-20 mt-3 hidden justify-end xl:flex min-[1800px]:hidden">
              <GenerateButton size="default" testId="inline-generate" />
            </div>
          ) : null}
        </section>

        <div className="hidden xl:block">
          {collapse ? (
            <button type="button" onClick={() => setSummaryOpen(true)} className="sticky top-4 flex w-full flex-col items-center gap-2 rounded-lg border py-3 text-xs hover:bg-fill-2 min-[1800px]:hidden" aria-label={t("studio.summary.title")} data-testid="summary-collapsed">
              <ChevronLeft className="size-4" aria-hidden />
              <span className="[writing-mode:vertical-rl]">{t("studio.summary.title")}</span>
            </button>
          ) : null}
          <div className={cn("sticky top-4", collapse && "hidden min-[1800px]:block")}>
            <SummaryPanel />
          </div>
        </div>
      </div>

      {/* < xl: sticky bottom bar — Back · summary pill · Next / Generate */}
      <div className="pointer-events-none fixed inset-x-0 bottom-[calc(5.25rem+env(safe-area-inset-bottom))] z-30 px-3 lg:bottom-3 xl:hidden" data-testid="studio-bottom-bar">
        <div data-glass="chrome" className="glass-chrome pointer-events-auto mx-auto flex max-w-3xl items-center gap-2 rounded-full p-1.5">
          <Button variant="ghost" size="sm" disabled={index === 0} onClick={() => goStep(STUDIO_STEPS[index - 1])} className="pointer-coarse:min-h-11">
            <ChevronLeft aria-hidden /> {t("common.back")}
          </Button>
          <button type="button" onClick={() => setSummaryOpen(true)} className="min-w-0 flex-1 truncate rounded-full bg-fill-3 px-3 py-1.5 text-left text-xs pointer-coarse:min-h-11" data-testid="summary-pill">
            <SummaryPill />
          </button>
          {step === "run" ? (
            <GenerateButton size="sm" testId="bar-generate" />
          ) : (
            <Button size="sm" onClick={() => goStep(STUDIO_STEPS[index + 1])} className="pointer-coarse:min-h-11" data-testid="step-next">
              {t("common.next")} <ChevronRight aria-hidden />
            </Button>
          )}
        </div>
      </div>
      <Sheet open={summaryOpen} onOpenChange={setSummaryOpen}>
        <SheetContent side="bottom" className="max-h-[85dvh] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{t("studio.summary.title")}</SheetTitle>
          </SheetHeader>
          <div className="px-4 pb-6">
            <SummaryPanel />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function SummaryPill() {
  const { t, n } = useI18n();
  const { summary } = useStudio();
  const word = summary.readiness === "ready" ? `${t("studio.check.ready")} ✓` : summary.readiness === "blocked" ? t("studio.check.blocked") : summary.readiness === "needs_look" ? t("studio.check.needsLook") : summary.readiness === "checking" ? t("studio.check.checking") : "";
  return (
    <>
      {t("studio.summary.pill", { n: n(summary.classesIn) })}
      {word ? ` · ${word}` : ""}
    </>
  );
}
