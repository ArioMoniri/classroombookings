"use client";
/**
 * /programs/new (docs/design/v2/phase19-program-wizard.md, motion.md §3.11): create a programme with no file to
 * import. A vertical rail of eight steps that can be visited in any order, each with ✓ / ⚠ n / ✕ n / –, the
 * autosave line and "Taslak", the step content, and a plain preview column. Saves through the catalog_admin
 * endpoints as you type; only errors block the last step. The last step starts a minimal-change re-solve of the
 * published plan (moderation preview) or, with no published plan, a first run of the term.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, CircleDashed, FolderOpen, Plus, Trash2, XOctagon } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { catalogApi } from "@/lib/api/catalog-admin";
import { api } from "@/lib/api/endpoints";
import { useRooms, useRuns, useTerms } from "@/lib/api/hooks";
import { moderationApi } from "@/lib/api/moderation";
import type { PrecheckItem } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce, useReducedTransparency } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { ConstraintsStep, CoursesStep, PatternsStep, ProgramStep, SectionsStep, TermStep, issueText } from "./steps";
import { createDraft, draftFromServer, errorText, useDraftStore, useWizard, type SaveState } from "./use-wizard";
import { STEPS, canGenerate, meetingIds, parseStep, stepStatus, summary, validate, type Draft, type Issue, type Step, type StepStatus } from "./wizard-model";

function relTime(at: string, locale: string): string {
  const s = Math.round((Date.now() - new Date(at).getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale === "tr" ? "tr" : "en", { numeric: "auto" });
  return s < 60 ? rtf.format(0, "minute") : s < 3600 ? rtf.format(-Math.round(s / 60), "minute") : rtf.format(-Math.round(s / 3600), "hour");
}

export function SaveStatus({ save, savedAt, onRetry }: { save: SaveState; savedAt: string | null; onRetry: () => void }) {
  const { t, locale } = useI18n();
  // text swap only: a ✓ animation on every 800 ms save would be motion on a frequent action (motion.md §3.11)
  return (
    <p role="status" aria-live="polite" className={cn("type-footnote", save.kind === "error" ? "text-status-warning-fg" : "text-label-2")} data-testid="save-status" data-state={save.kind}>
      {save.kind === "saving" ? t("programWizard.save.saving") : save.kind === "error" ? (
        <>
          {t("programWizard.save.error")} <Button variant="link" size="xs" onClick={onRetry}>{t("common.retry")}</Button>
          <span className="block text-label-2">{save.message}</span>
        </>
      ) : savedAt || save.kind === "saved" ? t("programWizard.save.saved", { when: relTime(save.kind === "saved" ? save.at : savedAt!, locale) }) : t("programWizard.save.local")}
    </p>
  );
}

function StatusGlyph({ s }: { s: StepStatus }) {
  if (s.errors) return <XOctagon className="size-4 text-status-infeasible-fg" aria-hidden />;
  if (s.warnings) return <AlertTriangle className="size-4 text-status-warning-fg" aria-hidden />;
  if (s.empty) return <CircleDashed className="size-4 text-label-3" aria-hidden />;
  return <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden />;
}

function Rail({ d, statuses, step, go, save, onRetry }: { d: Draft; statuses: StepStatus[]; step: Step; go: (s: Step) => void; save: SaveState; onRetry: () => void }) {
  const { t, n } = useI18n();
  const reduce = useReduce();
  const solid = useReducedTransparency();
  const sum = summary(d);
  const line: Partial<Record<Step, string>> = {
    term: d.termCode ?? undefined,
    program: d.program.name || undefined,
    courses: sum.courses ? t("programWizard.rail.courses", { n: n(sum.courses), ects: n(sum.ects) }) : undefined,
    sections: sum.sections ? t("programWizard.rail.sections", { n: n(sum.sections), people: n(sum.people) }) : undefined,
    patterns: sum.meetings ? t("programWizard.rail.meetings", { n: n(sum.meetings) }) : undefined,
  };
  return (
    <nav aria-label={t("programWizard.rail.label")} className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start" data-testid="wizard-rail">
      <ol className="flex flex-col gap-0.5">
        {statuses.map((s, i) => {
          const on = s.step === step;
          const status = s.errors ? t("programWizard.rail.errors", { n: s.errors }) : s.warnings ? t("programWizard.rail.warnings", { n: s.warnings }) : s.empty ? t("programWizard.rail.empty") : t("programWizard.rail.done");
          return (
            <li key={s.step}>
              <Button
                variant="ghost"
                className="relative h-auto w-full justify-start rounded-xl px-2.5 py-2 text-left"
                aria-current={on ? "step" : undefined}
                aria-label={`${i + 1}. ${t(`programWizard.step.${s.step}`)}, ${status}`}
                aria-keyshortcuts={`Alt+${i + 1}`}
                onClick={() => go(s.step)}
                data-testid={`rail-${s.step}`}
                data-status={s.errors ? "error" : s.warnings ? "warning" : s.empty ? "empty" : "done"}
              >
                {/* rail pill: one element that glides to the step (pattern 2); reduced motion: jumps */}
                {on ? <motion.span layoutId="wizard-rail" aria-hidden className={cn("absolute inset-0 -z-10 rounded-xl bg-tint-soft", solid && "border border-hairline-strong")} transition={reduce ? { duration: 0 } : springs.glassMorph} /> : null}
                <StatusGlyph s={s} />
                <span className="flex min-w-0 flex-col">
                  <span className="type-callout whitespace-normal text-label-1">{i + 1} {t(`programWizard.step.${s.step}`)}</span>
                  {line[s.step] ? <span className="truncate type-caption text-label-2">{line[s.step]}</span> : null}
                  {s.errors || s.warnings ? <span className="type-caption text-label-2">{status}</span> : null}
                </span>
              </Button>
            </li>
          );
        })}
      </ol>
      <div className="border-t border-hairline pt-2">
        <SaveStatus save={save} savedAt={d.savedAt} onRetry={onRetry} />
        <p className="type-caption text-label-3">{t("programWizard.rail.draftNote", { term: d.termCode ?? "—" })}</p>
      </div>
    </nav>
  );
}

function Preview({ d }: { d: Draft }) {
  const { t, n } = useI18n();
  const s = summary(d);
  return (
    <aside className="flex flex-col gap-1 rounded-2xl border border-hairline p-4 xl:sticky xl:top-4 xl:self-start" aria-label={t("programWizard.preview.label")} data-testid="wizard-preview">
      <p className="type-headline">{d.program.name || t("programWizard.preview.noName")}</p>
      <p className="type-footnote text-label-2">{[d.termCode, d.program.facultyName].filter(Boolean).join(" · ")}</p>
      <p className="type-callout tabular-nums">{t("programWizard.preview.counts", { courses: n(s.courses), sections: n(s.sections), people: n(s.people), hours: n(s.weeklyHours) })}</p>
      {s.newPeople ? <p className="type-footnote text-label-2">{t("programWizard.preview.newPeople", { n: n(s.newPeople) })}</p> : null}
      <p className="type-footnote text-label-2">{d.program.evening ? t("programWizard.preview.evening") : t("programWizard.preview.day")}</p>
    </aside>
  );
}

/* ------------------------------------------------------------------ 7 pre-check */

function PrecheckStep({ d, issues, onFix }: { d: Draft; issues: readonly Issue[]; onFix: (s: Step) => void }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const ids = useMemo(() => new Set(meetingIds(d)), [d]);
  const [items, setItems] = useState<PrecheckItem[] | null>(null);
  const [state, setState] = useState<"idle" | "running" | "error">("idle");
  const [err, setErr] = useState("");
  const run = async () => {
    if (!d.termId) return;
    setState("running");
    try {
      const out = await catalogApi.precheck(d.termId);
      setItems(out.items.filter((i) => i.event_ids.some((e) => ids.has(e))));
      setState("idle");
    } catch (e) {
      setErr(errorText(e));
      setState("error");
    }
  };
  const own = issues.filter((i) => i.level !== "info");
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-1">
        <h3 className="type-headline">{t("programWizard.precheck.wizard")}</h3>
        {own.length ? (
          <ul className="flex flex-col gap-1" data-testid="wizard-issues">
            {own.map((i, k) => (
              <li key={k} className="flex items-start gap-2 type-footnote">
                {i.level === "error" ? <XOctagon className="mt-0.5 size-3.5 text-status-infeasible-fg" aria-hidden /> : <AlertTriangle className="mt-0.5 size-3.5 text-status-warning-fg" aria-hidden />}
                <span className="flex-1">{issueText(t, i)}</span>
                <Button variant="link" size="xs" onClick={() => onFix(i.step)}>{t("programWizard.precheck.fix")}</Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="type-footnote text-status-feasible-fg">✓ {t("programWizard.precheck.clean")}</p>
        )}
      </section>
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="type-headline">{t("programWizard.precheck.studio")}</h3>
          <Button size="sm" variant="outline" onClick={() => void run()} disabled={state === "running" || !ids.size} aria-busy={state === "running" || undefined} data-testid="precheck-run">
            {state === "running" ? t("busy.checking") : t("programWizard.precheck.run")}
          </Button>
        </div>
        {!ids.size ? <p className="type-footnote text-label-2">{t("programWizard.precheck.noMeetings")}</p> : null}
        {state === "error" ? <p role="alert" className="type-footnote text-status-infeasible-fg">{err}</p> : null}
        {items ? (
          <div role="status" aria-live="polite" data-testid="precheck-result">
            <p className="type-callout">{t("programWizard.precheck.result", { errors: items.filter((i) => i.severity === "error").length, warnings: items.filter((i) => i.severity === "warning").length })}</p>
            <ul className="flex flex-col gap-1">
              {items.map((i) => (
                <li key={i.id} className="type-footnote">
                  {i.severity === "error" ? "✕" : i.severity === "warning" ? "⚠" : "ⓘ"} <span className="font-semibold">{i.title[lang] || i.title.tr}</span> · {i.message[lang] || i.message.tr}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ 8 generate */

function GenerateStep({ d, issues, flush, onFix }: { d: Draft; issues: readonly Issue[]; flush: () => Promise<boolean>; onFix: (s: Step) => void }) {
  const { t, n } = useI18n();
  const router = useRouter();
  const runs = useRuns(d.termId ? { term_id: d.termId } : undefined, { enabled: d.termId !== null });
  const published = (runs.data ?? []).find((r) => r.is_active && r.kind === "COURSE" && r.term_id === d.termId);
  const [mode, setMode] = useState<"solve" | "only">("solve");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const statuses = stepStatus(d, issues);
  const s = summary(d);
  const ok = canGenerate(issues);
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!(await flush())) throw new Error(t("programWizard.generate.saveFirst"));
      const fresh = useDraftStore.getState().drafts[d.key] ?? d;
      const ids = meetingIds(fresh);
      if (mode === "only") {
        toast.success(t("programWizard.generate.created", { term: d.termCode ?? "" }));
        setConfirm(false);
        return;
      }
      if (published) {
        const out = await moderationApi.resolve(d.termId!, { base_run_id: published.id, changed_request_ids: ids, mode: "repair" });
        router.push(`/moderation/recreate/${out.run_id}`);
      } else {
        const out = await api.runs.create({ term_id: d.termId!, kind: "COURSE", horizon: "TERM" });
        router.push(`/runs/${out.run_id}`);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <table className="w-full type-callout" data-testid="generate-summary">
        <tbody>
          {statuses.filter((x) => x.step !== "generate").map((x, i) => (
            <tr key={x.step} className="border-b border-hairline">
              <td className="w-8 py-1.5 tabular-nums text-label-2">{i + 1}</td>
              <th scope="row" className="py-1.5 text-left font-semibold">{t(`programWizard.step.${x.step}`)}</th>
              <td className="py-1.5"><span className="inline-flex items-center gap-1"><StatusGlyph s={x} />{x.errors ? t("programWizard.rail.errors", { n: x.errors }) : x.warnings ? t("programWizard.rail.warnings", { n: x.warnings }) : x.empty ? t("programWizard.rail.empty") : t("programWizard.rail.done")}</span></td>
              <td className="py-1.5 text-right">{x.errors || x.warnings || x.empty ? <Button variant="link" size="xs" onClick={() => onFix(x.step)}>{t("programWizard.precheck.fix")}</Button> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <fieldset className="flex flex-col gap-2">
        <legend className="type-headline">{t("programWizard.generate.how")}</legend>
        <label className="flex items-start gap-2 type-callout">
          <input type="radio" name="gen" className="mt-1 accent-(--accent)" checked={mode === "solve"} onChange={() => setMode("solve")} />
          <span><span className="font-semibold">{published ? t("programWizard.generate.solve") : t("programWizard.generate.solveFirst")}</span><span className="block type-footnote text-label-2">{published ? t("programWizard.generate.solveHint", { term: d.termCode ?? "", id: published.id }) : t("programWizard.generate.solveFirstHint")}</span></span>
        </label>
        <label className="flex items-start gap-2 type-callout">
          <input type="radio" name="gen" className="mt-1 accent-(--accent)" checked={mode === "only"} onChange={() => setMode("only")} />
          <span><span className="font-semibold">{t("programWizard.generate.only")}</span><span className="block type-footnote text-label-2">{t("programWizard.generate.onlyHint")}</span></span>
        </label>
      </fieldset>
      {!ok ? <p role="alert" className="type-footnote text-status-infeasible-fg">{t("programWizard.generate.blocked")}</p> : null}
      <div className="flex justify-end">
        <Button disabled={!ok || busy} onClick={() => setConfirm(true)} data-testid="generate-open">{t("programWizard.generate.go")}</Button>
      </div>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent className="sm:max-w-md" data-testid="generate-confirm">
          <DialogHeader>
            <DialogTitle>{t("programWizard.generate.confirmTitle")}</DialogTitle>
            <DialogDescription>{t("programWizard.generate.confirmBody", { term: d.termCode ?? "", courses: n(s.courses), sections: n(s.sections), meetings: n(s.meetings), people: n(s.newPeople) })}</DialogDescription>
          </DialogHeader>
          {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
            <Button onClick={() => void go()} disabled={busy} aria-busy={busy || undefined} data-testid="generate-go">{busy ? t("programWizard.generate.creating") : mode === "solve" ? t("programWizard.generate.go") : t("programWizard.generate.only")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ landing (drafts + resume) */

function Landing() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const drafts = useDraftStore((s) => s.drafts);
  const remove = useDraftStore((s) => s.remove);
  const terms = useTerms();
  const [termId, setTermId] = useState<string>("");
  const [programId, setProgramId] = useState<string>("");
  const programs = useQuery({ queryKey: ["wizard", "programs"], queryFn: () => catalogApi.programs({}), staleTime: 60_000 });
  const [busy, setBusy] = useState(false);
  const list = Object.values(drafts).sort((a, b) => (b.savedAt ?? b.createdAt).localeCompare(a.savedAt ?? a.createdAt));
  const start = (example = false) => {
    const term = (terms.data ?? []).find((x) => x.id === Number(termId)) ?? terms.data?.[0];
    const key = createDraft(term?.id ?? null, term?.code ?? null);
    if (example) {
      const d = useDraftStore.getState().drafts[key]!;
      useDraftStore.getState().put({ ...d, step: "program", program: { ...d.program, name: "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans", facultyName: "Fen Bilimleri Enstitüsü", prefix: "MBG", level: "masterThesis", years: 2 } });
    }
    router.push(`/programs/new?draft=${key}&step=${example ? "program" : "term"}`);
  };
  const resume = async () => {
    const term = (terms.data ?? []).find((x) => x.id === Number(termId));
    if (!term || !programId) return;
    setBusy(true);
    try {
      const key = await draftFromServer(term.id, term.code, Number(programId));
      router.push(`/programs/new?draft=${key}&step=courses`);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex max-w-3xl flex-col gap-6" data-testid="wizard-landing">
      <PageHeader title={t("programWizard.title")} subtitle={t("programWizard.intro")} actions={<><Button onClick={() => start()} data-testid="wizard-start"><Plus aria-hidden />{t("programWizard.start")}</Button><Button variant="outline" onClick={() => start(true)} data-testid="wizard-example">{t("programWizard.startExample")}</Button></>} />
      <section aria-labelledby="drafts-title" className="flex flex-col gap-2">
        <h2 id="drafts-title" className="type-headline">{t("programWizard.drafts")}</h2>
        {list.length ? (
          <ul className="flex flex-col" data-testid="draft-list">
            {list.map((d) => (
              <li key={d.key} className="flex flex-wrap items-center gap-3 border-b border-hairline py-2 type-callout">
                <span className="min-w-0 flex-1">
                  <span className="font-semibold">{d.program.name || t("programWizard.preview.noName")}</span>
                  <span className="block type-footnote text-label-2">{[d.termCode, t("programWizard.resumeAt", { step: t(`programWizard.step.${d.step}`) }), d.savedAt ? new Date(d.savedAt).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB") : null].filter(Boolean).join(" · ")}</span>
                </span>
                <Button size="sm" variant="secondary" render={<Link href={`/programs/new?draft=${d.key}&step=${d.step}`} />} nativeButton={false}>{t("programWizard.resume")}</Button>
                <Button size="icon-sm" variant="ghost" aria-label={t("programWizard.forget", { name: d.program.name || "—" })} onClick={() => remove(d.key)}><Trash2 aria-hidden /></Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="type-footnote text-label-2">{t("programWizard.noDrafts")}</p>
        )}
      </section>
      <section aria-labelledby="server-title" className="flex flex-col gap-2">
        <h2 id="server-title" className="type-headline">{t("programWizard.openExisting")}</h2>
        <p className="type-footnote text-label-2">{t("programWizard.openExistingHint")}</p>
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect className="w-48" value={termId} onChange={(e) => setTermId(e.target.value)} aria-label={t("programWizard.term.label")}>
            <option value="">{t("programWizard.term.pick")}</option>
            {(terms.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}
          </NativeSelect>
          <NativeSelect className="w-72" value={programId} onChange={(e) => setProgramId(e.target.value)} aria-label={t("programWizard.program.name")}>
            <option value="">{t("programWizard.pickProgram")}</option>
            {(programs.data?.items ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </NativeSelect>
          <Button variant="outline" disabled={!termId || !programId || busy} onClick={() => void resume()}><FolderOpen aria-hidden />{t("programWizard.open")}</Button>
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ the wizard */

export function ProgramWizard() {
  const { can, loading } = usePermissions();
  const params = useSearchParams();
  const key = params.get("draft");
  const { t } = useI18n();
  if (loading) return <Skeleton className="h-96 w-full" />;
  if (!can("planning.edit")) return <EmptyState title={t("programWizard.forbiddenTitle")} description={t("programWizard.forbidden")} />;
  return key ? <WizardBody draftKey={key} /> : <Landing />;
}

function WizardBody({ draftKey }: { draftKey: string }) {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const reduce = useReduce();
  const { draft, update, save, flush, warnings } = useWizard(draftKey);
  const terms = useTerms();
  const rooms = useRooms();
  const step = parseStep(params.get("step") ?? draft?.step);
  const [dir, setDir] = useState(1);
  const heading = useRef<HTMLHeadingElement>(null);
  const issues = useMemo(() => (draft ? validate(draft, rooms.data ?? null) : []), [draft, rooms.data]);
  const statuses = useMemo(() => (draft ? stepStatus(draft, issues) : []), [draft, issues]);

  const go = (next: Step) => {
    setDir(STEPS.indexOf(next) >= STEPS.indexOf(step) ? 1 : -1);
    update((d) => ({ ...d, step: next }));
    router.replace(`/programs/new?draft=${draftKey}&step=${next}`, { scroll: false });
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

  if (!draft) {
    return <EmptyState title={t("programWizard.missingTitle")} description={t("programWizard.missing")} actions={<Button render={<Link href="/programs/new" />} nativeButton={false}>{t("programWizard.title")}</Button>} />;
  }

  /** Devam with errors: focus the first invalid field of this step and shake it once (motion.md §3.11) */
  const next = () => {
    const first = issues.find((i) => i.step === step && i.level === "error" && i.path);
    if (first) {
      const el = document.querySelector<HTMLElement>(`[data-path="${CSS.escape(first.path!)}"]`);
      if (el) {
        el.focus();
        el.classList.add("t-input");
        el.classList.remove("is-shaking");
        void el.offsetWidth;
        el.classList.add("is-shaking");
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

  const body =
    step === "term" ? <TermStep d={draft} update={update} terms={terms.data ?? []} />
    : step === "program" ? <ProgramStep d={draft} update={update} issues={issues} />
    : step === "courses" ? <CoursesStep d={draft} update={update} issues={issues} />
    : step === "sections" ? <SectionsStep d={draft} update={update} issues={issues} />
    : step === "patterns" ? <PatternsStep d={draft} update={update} issues={issues} rooms={rooms.data ?? []} />
    : step === "constraints" ? <ConstraintsStep d={draft} update={update} />
    : step === "precheck" ? <PrecheckStep d={draft} issues={issues} onFix={go} />
    : <GenerateStep d={draft} issues={issues} flush={flush} onFix={go} />;

  return (
    <div className="flex flex-col gap-4" data-testid="program-wizard">
      <PageHeader title={draft.program.name || t("programWizard.title")} subtitle={t("programWizard.subtitle")} />
      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[16rem_minmax(0,1fr)_18rem]">
        <Rail d={draft} statuses={statuses} step={step} go={go} save={save} onRetry={() => void flush()} />
        <main className="flex min-w-0 flex-col gap-4" aria-labelledby="wizard-step-title">
          <h2 id="wizard-step-title" ref={heading} tabIndex={-1} className="type-title-2 outline-hidden">
            {STEPS.indexOf(step) + 1}. {t(`programWizard.step.${step}`)}
          </h2>
          {/* wizard.step-change: enter-only, 8 px from the travel direction; the old step leaves instantly */}
          <motion.div key={step} initial={reduce ? { opacity: 0 } : { opacity: 0, x: 8 * dir }} animate={{ opacity: 1, x: 0 }} transition={reduce ? tween.reduced : springs.smooth}>
            {body}
          </motion.div>
          {warnings.length ? (
            <ul className="type-footnote text-label-2" aria-label={t("programWizard.serverNotes")}>
              {warnings.slice(-5).map((w) => <li key={w}>ⓘ {w.startsWith("reused:") ? t("programWizard.v.reused", { code: w.slice(7) }) : w}</li>)}
            </ul>
          ) : null}
          <div className="flex justify-between gap-2 border-t border-hairline pt-3">
            <Button variant="ghost" onClick={back} disabled={step === "term"}><ChevronLeft aria-hidden />{t("common.back")}</Button>
            {step !== "generate" ? <Button onClick={next} data-testid="wizard-next">{t("common.next")}<ChevronRight aria-hidden /></Button> : null}
          </div>
        </main>
        <div className="hidden xl:block"><Preview d={draft} /></div>
      </div>
    </div>
  );
}
