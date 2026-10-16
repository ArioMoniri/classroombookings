"use client";
/**
 * Step 8 "Oluştur ve çöz" and what follows it (program-wizard spec §4.8, §9 Done; backend
 * `POST /program-drafts/{id}/commit {solve}` and `GET/POST …/undo`). The summary lists every step with the
 * server's status and a "Düzelt" link; errors disable the write, warnings never do. The commit is one
 * transaction: with a published plan "Oluştur ve mevcut plana ekle" (solve=minimal) lands in the moderation
 * preview and nothing is published before it is approved; without one "Oluştur ve dönemi çöz" writes, then
 * starts the term's first run. The result screen keeps "Geri al (30 gün)" with the server's blockers, and the
 * learned-suggestions panel says honestly when this programme has no history yet.
 */
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleDashed, History, RotateCcw, XOctagon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { api } from "@/lib/api/endpoints";
import { useRuns } from "@/lib/api/hooks";
import { useSuggestions } from "@/lib/api/learning";
import { dk, draftsApi, useUndoCheck, type CommitOut, type CreatedIds, type StepState, type UndoOut, type Validation } from "@/lib/api/program-drafts";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { errorText } from "./use-wizard";
import { commitCounts, issueText, refusedIssues, restoredSummary, type Payload, type Step } from "./wizard-model";
import { RefusedIssues } from "./steps";
import type { DraftIssue } from "@/lib/api/program-drafts";

export function StepGlyph({ status }: { status: StepState["status"] | undefined }) {
  if (status === "error") return <XOctagon className="size-4 shrink-0 text-status-infeasible-fg" aria-hidden />;
  if (status === "warning") return <AlertTriangle className="size-4 shrink-0 text-status-warning-fg" aria-hidden />;
  if (status === "ok") return <CheckCircle2 className="size-4 shrink-0 text-status-feasible-fg" aria-hidden />;
  return <CircleDashed className="size-4 shrink-0 text-label-3" aria-hidden />;
}

export function statusWord(t: ReturnType<typeof useI18n>["t"], s: StepState | undefined): string {
  if (!s) return t("programWizard.rail.empty");
  if (s.status === "error") return t("programWizard.rail.errors", { n: s.errors.length });
  if (s.status === "warning") return t("programWizard.rail.warnings", { n: s.warnings.length });
  if (s.status === "empty") return t("programWizard.rail.empty");
  return t("programWizard.rail.done");
}

/** "Bu program için geçmiş veri yok": learned suggestions about this programme's people and courses, if any */
export function HistoryPanel({ termId, personIds, courseIds }: { termId: number; personIds: readonly number[]; courseIds: readonly number[] }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const { can } = usePermissions();
  const q = useSuggestions(can("planning.view") ? termId : null);
  const people = new Set(personIds);
  const courses = new Set(courseIds);
  const mine = (q.data ?? []).filter((s) => s.state === "open" && ((s.subject.type === "instructor" && people.has(Number(s.subject.id))) || (s.subject.type === "course" && courses.has(Number(s.subject.id)))));
  if (q.isLoading) return null;
  return (
    <section aria-labelledby="wizard-history" className="flex flex-col gap-1 rounded-xl border border-dashed border-hairline-strong p-3" data-testid="wizard-history">
      <h3 id="wizard-history" className="inline-flex items-center gap-1.5 type-headline"><History className="size-4" aria-hidden />{t("programWizard.history.title")}</h3>
      {mine.length ? (
        <ul className="flex flex-col gap-1 type-footnote">
          {mine.slice(0, 6).map((s) => (
            <li key={s.id} className="flex flex-wrap gap-x-2">
              <span className="min-w-0 flex-1">{s.claim[lang] || s.claim.tr}</span>
              {s.subject.type === "instructor" ? <Link className="text-(--accent) underline-offset-2 hover:underline" href={`/moderation/people/${s.subject.id}`}>{t("programWizard.history.open")}</Link> : null}
            </li>
          ))}
        </ul>
      ) : (
        <>
          <p className="type-callout" data-testid="wizard-no-history">{t("programWizard.history.none")}</p>
          <p className="type-footnote text-label-2">{t("programWizard.history.noneHint")}</p>
        </>
      )}
    </section>
  );
}

function payloadPeople(p: Payload): number[] {
  return p.courses.flatMap((c) => c.sections.flatMap((s) => s.instructors.map((i) => i.id).filter((x): x is number => typeof x === "number")));
}

export function GenerateStep({ draftId, termId, termCode, p, v, flush, onFix, onCommitted }: { draftId: number; termId: number; termCode: string; p: Payload; v: Validation; flush: () => Promise<boolean>; onFix: (s: Step) => void; onCommitted: (r: CommitOut) => void }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const qc = useQueryClient();
  const runs = useRuns({ term_id: termId });
  const published = (runs.data ?? []).find((r) => r.is_active && r.kind === "COURSE" && r.term_id === termId);
  const [mode, setMode] = useState<"solve" | "only">("solve");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refused, setRefused] = useState<DraftIssue[]>([]);
  const cancel = useRef<HTMLButtonElement>(null);
  const counts = commitCounts(p);
  const ok = v.can_commit;
  const go = async () => {
    setBusy(true);
    setError(null);
    setRefused([]);
    try {
      if (!(await flush())) throw new Error(t("programWizard.generate.saveFirst"));
      const out = await draftsApi.commit(draftId, mode === "solve" && published ? "minimal" : "none");
      void qc.invalidateQueries({ queryKey: ["program-drafts"] });
      toast.success(t("programWizard.generate.created", { term: termCode }));
      setConfirm(false);
      if (out.next === "moderation_preview" && out.run_id) {
        router.push(`/moderation/recreate/${out.run_id}`);
        return;
      }
      if (mode === "solve" && !published) {
        const run = await api.runs.create({ term_id: termId, kind: "COURSE", horizon: "TERM" });
        router.push(`/runs/${run.run_id}`);
        return;
      }
      onCommitted(out);
    } catch (e) {
      setError(errorText(e, lang));
      setRefused(refusedIssues(e)?.issues ?? []);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <table className="w-full type-callout" data-testid="generate-summary">
        <tbody>
          {v.steps.filter((x) => x.step !== "generate").map((x, i) => {
            const first = x.errors[0] ?? x.warnings[0];
            return (
              <tr key={x.step} className="border-b border-hairline align-top">
                <td className="w-6 py-1.5 tabular-nums text-label-2">{i + 1}</td>
                <th scope="row" className="py-1.5 pr-2 text-left font-semibold">{t(`programWizard.step.${x.step}`)}</th>
                <td className="py-1.5">
                  <span className="inline-flex items-center gap-1"><StepGlyph status={x.status} />{statusWord(t, x)}</span>
                  {first ? <span className="block type-caption text-label-2">{issueText(first, lang)}</span> : null}
                </td>
                <td className="py-1.5 text-right">{x.status !== "ok" ? <Button variant="link" size="xs" className="max-md:h-11" onClick={() => onFix(x.step)}>{t("programWizard.precheck.fix")}</Button> : null}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <HistoryPanel termId={termId} personIds={payloadPeople(p)} courseIds={p.courses.map((c) => c.course_id).filter((x): x is number => x !== null)} />
      <fieldset className="flex flex-col gap-2">
        <legend className="type-headline">{t("programWizard.generate.how")}</legend>
        <label className="flex min-h-11 items-start gap-2 type-callout">
          <input type="radio" name="gen" className="mt-1 accent-(--accent)" checked={mode === "solve"} onChange={() => setMode("solve")} data-testid="generate-mode-solve" />
          <span><span className="font-semibold">{published ? t("programWizard.generate.solve") : t("programWizard.generate.solveFirst")}</span><span className="block type-footnote text-label-2">{published ? t("programWizard.generate.solveHint", { term: termCode, id: published.id }) : t("programWizard.generate.solveFirstHint")}</span></span>
        </label>
        <label className="flex min-h-11 items-start gap-2 type-callout">
          <input type="radio" name="gen" className="mt-1 accent-(--accent)" checked={mode === "only"} onChange={() => setMode("only")} data-testid="generate-mode-only" />
          <span><span className="font-semibold">{t("programWizard.generate.only")}</span><span className="block type-footnote text-label-2">{t("programWizard.generate.onlyHint")}</span></span>
        </label>
      </fieldset>
      {!ok ? <p role="alert" className="type-footnote text-status-infeasible-fg">{t("programWizard.generate.blocked")}</p> : null}
      <div className="flex justify-end">
        <Button className="max-md:w-full" disabled={!ok || busy} onClick={() => setConfirm(true)} data-testid="generate-open">{mode === "solve" ? t("programWizard.generate.go") : t("programWizard.generate.only")}</Button>
      </div>
      <ResponsiveDialog
        open={confirm}
        onOpenChange={(o) => { setConfirm(o); if (!o) setError(null); }}
        alert
        initialFocus={cancel}
        title={t("programWizard.generate.confirmTitle")}
        description={t("programWizard.generate.confirmBody", { term: termCode, courses: n(counts.courses), sections: n(counts.sections), cohorts: n(counts.cohorts), meetings: n(counts.meetings), people: n(v.summary.new_people), rules: n(counts.rules) })}
        testId="generate-confirm"
        footer={
          <>
            <Button ref={cancel} variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
            <Button onClick={() => void go()} disabled={busy} aria-busy={busy || undefined} data-testid="generate-go">{busy ? t("programWizard.generate.creating") : mode === "solve" ? t("programWizard.generate.go") : t("programWizard.generate.only")}</Button>
          </>
        }
      >
        <p className="type-footnote text-label-2">{t("programWizard.generate.undoNote")}</p>
        {error ? <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="generate-error">{error}</p> : null}
        {refused.length ? <RefusedIssues issues={refused} onFix={(s) => (setConfirm(false), onFix(s))} /> : null}
      </ResponsiveDialog>
    </div>
  );
}

/* ------------------------------------------------------------------ after the commit */

const fmtDate = (iso: string | null, lang: "tr" | "en") => (iso ? new Date(iso).toLocaleDateString(lang === "tr" ? "tr-TR" : "en-GB", { day: "numeric", month: "long", year: "numeric" }) : "—");

export function CommittedView({ draftId, termId, termCode, title, status, created, result }: { draftId: number; termId: number; termCode: string; title: string; status: "committed" | "undone"; created: CreatedIds | null; result?: CommitOut | null }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const qc = useQueryClient();
  const router = useRouter();
  const [undone, setUndone] = useState<UndoOut | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null);
  const isUndone = status === "undone" || undone !== null;
  const check = useUndoCheck(isUndone ? null : draftId);
  const made = result?.created ?? created;
  const restored = restoredSummary(made);
  const counts = made ? { courses: made.courses.length + made.reused_courses.length, sections: made.sections.length, requests: made.requests.length, people: made.people.length, rules: made.rules.length } : null;
  const undo = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await draftsApi.undo(draftId);
      setUndone(out);
      setConfirm(false);
      void qc.invalidateQueries({ queryKey: ["program-drafts"] });
      void qc.invalidateQueries({ queryKey: dk.draft(draftId) });
      toast.success(t("programWizard.done.undoneToast", { name: title }));
    } catch (e) {
      setError(errorText(e, lang));
    } finally {
      setBusy(false);
    }
  };
  const solve = async () => {
    setStarting(true);
    try {
      const run = await api.runs.create({ term_id: termId, kind: "COURSE", horizon: "TERM" });
      router.push(`/runs/${run.run_id}`);
    } catch (e) {
      toast.error(errorText(e, lang));
      setStarting(false);
    }
  };
  return (
    <div className="flex max-w-3xl flex-col gap-4" data-testid="wizard-committed" data-status={isUndone ? "undone" : "committed"}>
      <div role="status" className={cn("flex flex-col gap-1 rounded-2xl border p-4", isUndone ? "border-hairline" : "border-status-feasible-border bg-status-feasible")}>
        <p className="inline-flex items-center gap-2 type-headline">
          {isUndone ? <RotateCcw className="size-5" aria-hidden /> : <CheckCircle2 className="size-5 text-status-feasible-fg" aria-hidden />}
          {isUndone ? t("programWizard.done.undoneTitle", { term: termCode }) : t("programWizard.done.title", { term: termCode })}
        </p>
        {counts ? <p className="type-callout tabular-nums">{t("programWizard.done.counts", { courses: n(counts.courses), sections: n(counts.sections), requests: n(counts.requests), people: n(counts.people), rules: n(counts.rules) })}</p> : null}
        {(result?.warnings ?? made?.warnings ?? []).length ? (
          <ul className="type-footnote text-label-2">{(result?.warnings ?? made?.warnings ?? []).map((w) => <li key={w}>ⓘ {w}</li>)}</ul>
        ) : null}
        {restored && !isUndone ? (
          <p className="type-footnote text-label-2" data-testid="done-restored">
            {t("programWizard.done.restored", { what: [restored.program ? t("programWizard.done.restoredProgram") : null, restored.courses ? t("programWizard.done.restoredCourses", { n: n(restored.courses) }) : null, restored.people ? t("programWizard.done.restoredPeople", { n: n(restored.people) }) : null].filter(Boolean).join(", ") })}
          </p>
        ) : null}
        {undone ? <p className="type-footnote text-label-2" data-testid="undo-result">{t("programWizard.done.archived", { sections: n(undone.archived.sections?.length ?? 0), courses: n(undone.archived.courses?.length ?? 0), people: n(undone.archived.people?.length ?? 0) })}</p> : null}
      </div>
      {!isUndone ? (
        <>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            {result?.next === "studio" || !result ? (
              <Button onClick={() => void solve()} disabled={starting} aria-busy={starting || undefined} data-testid="done-solve">{t("programWizard.done.solve")}</Button>
            ) : null}
            <Button variant="outline" render={<Link href="/moderation?tab=requests" />} nativeButton={false}>{t("programWizard.done.moderation")}</Button>
            <Button variant="ghost" render={<Link href="/programs/new" />} nativeButton={false}>{t("programWizard.done.another")}</Button>
          </div>
          <section aria-labelledby="undo-title" className="flex flex-col gap-2 border-t border-hairline pt-3" data-testid="undo-panel">
            <h3 id="undo-title" className="type-headline">{t("programWizard.done.undoTitle")}</h3>
            {check.data ? (
              <>
                <p className="type-footnote text-label-2">{t("programWizard.done.undoUntil", { date: fmtDate(check.data.undo_until ?? result?.undo_until ?? null, lang) })}</p>
                {check.data.blockers.length ? (
                  <ul className="flex flex-col gap-0.5 type-footnote text-status-warning-fg" data-testid="undo-blockers">
                    {check.data.blockers.map((b, i) => <li key={`${b.code}-${i}`}>⚠ {b.text[lang] || b.text.tr}</li>)}
                  </ul>
                ) : null}
                <div>
                  <Button variant="outline" onClick={() => setConfirm(true)} disabled={!check.data.can_undo} data-testid="undo-open"><RotateCcw aria-hidden />{t("programWizard.done.undo")}</Button>
                </div>
              </>
            ) : check.isError ? (
              <p role="alert" className="type-footnote text-label-2">{errorText(check.error, lang)}</p>
            ) : (
              <p className="type-footnote text-label-3">{t("busy.checking")}</p>
            )}
          </section>
          <HistoryPanel termId={termId} personIds={[...(made?.people ?? []), ...(made?.reused_people ?? [])]} courseIds={[...(made?.courses ?? []), ...(made?.reused_courses ?? [])]} />
        </>
      ) : null}
      <ResponsiveDialog
        open={confirm}
        onOpenChange={(o) => { setConfirm(o); if (!o) setError(null); }}
        alert
        initialFocus={cancel}
        title={t("programWizard.done.undoConfirmTitle", { name: title })}
        description={t("programWizard.done.undoConfirmBody")}
        testId="undo-confirm"
        footer={
          <>
            <Button ref={cancel} variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
            <Button variant="destructive" onClick={() => void undo()} disabled={busy} aria-busy={busy || undefined} data-testid="undo-go">{busy ? t("busy.working") : t("programWizard.done.undo")}</Button>
          </>
        }
      >
        {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
      </ResponsiveDialog>
    </div>
  );
}
