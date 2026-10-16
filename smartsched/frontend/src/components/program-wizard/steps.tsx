"use client";
/**
 * The step bodies of the program wizard (program-wizard spec §4; the server's steps): Program → Dersler →
 * Şubeler (with joint teaching) → Öğretim elemanları (with this term's load) → Kohortlar → Odalar ve haftalık
 * düzen → Kısıtlar (with the program-scoped pre-check). Every field writes the draft payload; the messages under
 * a field are the server's own (TR + EN) for that path, so the wizard never invents a rule the commit would not
 * apply. Data entry has no motion (motion.md §3.11); on phones the grids are cards and every control is 44 px.
 */
import { useQuery } from "@tanstack/react-query";
import { ClipboardPaste, History, Link2, Minus, Plus, Trash2, UserPlus, Users, X } from "lucide-react";
import { toast } from "sonner";
import { useId, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { usePhone } from "@/components/moderation/use-media";
import { catalogApi } from "@/lib/api/catalog-admin";
import { useRooms } from "@/lib/api/hooks";
import { draftsApi, useInstructorLoads, useInstructorSearch, useRoomsFit, useSectionSearch, type DraftIssue, type DraftPrecheck, type PasteOut, type Validation } from "@/lib/api/program-drafts";
import type { Room } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { errorText } from "./use-wizard";
import {
  LEVELS,
  MODES,
  cohortsFromYears,
  courseHours,
  coursesFromPaste,
  hasError,
  issueText,
  issuesAt,
  issuesUnder,
  jointKey,
  jointTotal,
  neededCapacity,
  newCohortLabel,
  newCourse,
  newKey,
  newSection,
  normalizeCode,
  parseNumber,
  pasteDuplicates,
  patternHours,
  patternOptions,
  uncohorted,
  type CohortP,
  type CourseP,
  type InstructorRef,
  type Payload,
  type SectionP,
  type Step,
  namesakeRecord,
  refusedIssues,
} from "./wizard-model";

type Update = (fn: (p: Payload) => Payload) => void;
export interface StepProps {
  p: Payload;
  update: Update;
  v: Validation;
  termId: number;
  readOnly?: boolean;
}

/** 44 px touch targets on phones for the small chips and icon buttons (MOBILE.md M-02) */
const TOUCH = "max-md:h-11 max-md:min-w-11";

function Glyph({ level }: { level: DraftIssue["level"] }) {
  return <span aria-hidden>{level === "error" ? "✕ " : level === "warning" ? "⚠ " : "ⓘ "}</span>;
}

export function IssueLines({ issues, id, className }: { issues: readonly DraftIssue[]; id?: string; className?: string }) {
  const { locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  if (!issues.length) return null;
  return (
    <span id={id} className={cn("flex flex-col", className)} data-testid="field-issues">
      {issues.map((i, k) => (
        <span key={`${i.code}-${k}`} data-level={i.level} className={cn("type-caption", i.level === "error" ? "text-status-infeasible-fg" : i.level === "warning" ? "text-status-warning-fg" : "text-label-2")}>
          <Glyph level={i.level} />
          {issueText(i, lang)}
        </span>
      ))}
    </span>
  );
}

function FieldMsg({ v, path, id }: { v: Validation; path: string; id: string }) {
  return <IssueLines issues={issuesAt(v, path)} id={id} />;
}

function patchCourse(update: Update, key: string, fn: (c: CourseP) => CourseP) {
  update((d) => ({ ...d, courses: d.courses.map((c) => (c.key === key ? fn(c) : c)) }));
}
function patchSection(update: Update, course: string, section: string, fn: (s: SectionP) => SectionP) {
  patchCourse(update, course, (c) => ({ ...c, sections: c.sections.map((s) => (s.key === section ? fn(s) : s)) }));
}

const num = (v: number | null) => (v === null || Number.isNaN(v) ? "" : String(v));

/* ------------------------------------------------------------------ 1 program */

export function ProgramStep({ p, update, v, termCode }: StepProps & { termCode: string }) {
  const { t } = useI18n();
  const faculties = useQuery({ queryKey: ["wizard", "faculties"], queryFn: () => catalogApi.faculties(), staleTime: 60_000 });
  const pr = p.program;
  const set = (patch: Partial<Payload["program"]>) => update((x) => ({ ...x, program: { ...x.program, ...patch } }));
  const facultyIssues = [...issuesAt(v, "program.faculty"), ...issuesAt(v, "program.faculty_id")];
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <p className="type-callout">
        <span className="font-semibold">{t("programWizard.term.label")}:</span> {termCode}
        <span className="block type-footnote text-label-2">{t("programWizard.term.fixed")}</span>
      </p>
      <label className="flex flex-col gap-1">
        <span className="type-callout font-semibold">{t("programWizard.program.faculty")}</span>
        <Input
          list="wizard-faculties"
          value={pr.faculty_name}
          onChange={(e) => {
            const hit = (faculties.data?.items ?? []).find((f) => f.name.toLocaleLowerCase("tr-TR") === e.target.value.trim().toLocaleLowerCase("tr-TR"));
            set({ faculty_name: e.target.value, faculty_id: hit?.id ?? null });
          }}
          data-path="program.faculty"
          aria-invalid={facultyIssues.some((i) => i.level === "error") || undefined}
          aria-describedby="err-faculty"
          data-testid="wizard-faculty"
        />
        <datalist id="wizard-faculties">{(faculties.data?.items ?? []).map((f) => <option key={f.id} value={f.name} />)}</datalist>
        <span className="type-caption text-label-2">{pr.faculty_id ? t("programWizard.program.facultyExisting") : pr.faculty_name.trim() ? t("programWizard.program.facultyNew") : ""}</span>
        <IssueLines issues={facultyIssues} id="err-faculty" />
      </label>
      <label className="flex flex-col gap-1">
        <span className="type-callout font-semibold">{t("programWizard.program.name")}</span>
        <Input value={pr.name} onChange={(e) => set({ name: e.target.value })} data-path="program.name" aria-invalid={hasError(v, "program.name") || undefined} aria-describedby="err-name" data-testid="wizard-program-name" />
        <FieldMsg v={v} path="program.name" id="err-name" />
      </label>
      <fieldset className="flex flex-col gap-1">
        <legend className="type-callout font-semibold">{t("programWizard.program.level")}</legend>
        {/* choice cards: instant outline + radio dot, no scale (motion.md §3.11) */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {LEVELS.map((l) => (
            <label key={l} className={cn("flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 type-callout", pr.level === l ? "border-(--accent) bg-tint-soft" : "border-hairline")}>
              <input type="radio" name="level" className="accent-(--accent)" checked={pr.level === l} onChange={() => set({ level: l, years: l === "bachelor" || l === "phd" ? 4 : 2 })} />
              {t(`programWizard.level.${l}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="flex min-h-11 items-center gap-2 type-callout">
          <Switch checked={pr.evening} onCheckedChange={(on) => set({ evening: on })} />
          {t("programWizard.program.evening")}
        </label>
        <label className="flex flex-col gap-1 type-callout">
          {t("programWizard.program.language")}
          <NativeSelect className="sm:w-40" value={pr.language} onChange={(e) => set({ language: e.target.value as Payload["program"]["language"] })}>
            <option value="tr">{t("programWizard.lang.tr")}</option>
            <option value="en">{t("programWizard.lang.en")}</option>
            <option value="mixed">{t("programWizard.lang.mixed")}</option>
          </NativeSelect>
        </label>
        <label className="flex flex-col gap-1 type-callout">
          {t("programWizard.program.prefix")}
          <Input className="sm:w-24" value={pr.prefix} onChange={(e) => set({ prefix: e.target.value.toLocaleUpperCase("tr-TR") })} maxLength={4} data-path="program.prefix" aria-invalid={hasError(v, "program.prefix") || undefined} aria-describedby="err-prefix" data-testid="wizard-prefix" />
        </label>
        <label className="flex flex-col gap-1 type-callout">
          {t("programWizard.program.years")}
          <Input className="sm:w-20" inputMode="numeric" value={String(pr.years)} onChange={(e) => set({ years: Math.min(8, Math.max(1, Number(e.target.value) || 1)) })} />
        </label>
      </div>
      <FieldMsg v={v} path="program.prefix" id="err-prefix" />
    </div>
  );
}

/* ------------------------------------------------------------------ 2 courses + paste */

function PasteDialog({ draftId, open, onOpenChange, existing, onInsert }: { draftId: number; open: boolean; onOpenChange: (v: boolean) => void; existing: readonly CourseP[]; onInsert: (rows: CourseP[]) => void }) {
  const { t, n } = useI18n();
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<PasteOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const raw = useMemo(() => text.replace(/\r\n?/g, "\n").split("\n"), [text]);
  const dups = useMemo(() => (preview ? pasteDuplicates(existing, preview.rows) : new Set<number>()), [preview, existing]);
  const rows = (preview?.rows ?? []).filter((r) => !dups.has(r.line) && !r.code_error);
  const read = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await draftsApi.paste(draftId, text, "courses"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) {
      setText("");
      setPreview(null);
    }
  };
  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={close}
      title={t("programWizard.courses.pasteTitle")}
      description={t("programWizard.courses.pasteHint")}
      className="sm:max-w-2xl"
      testId="paste-dialog"
      footer={
        <>
          <Button variant="ghost" onClick={() => close(false)}>{t("common.cancel")}</Button>
          {preview ? (
            <Button disabled={!rows.length} onClick={() => { onInsert(coursesFromPaste(rows)); close(false); }} data-testid="paste-insert">
              {t("programWizard.courses.insert", { n: rows.length })}
            </Button>
          ) : (
            <Button disabled={!text.trim() || busy} onClick={() => void read()} aria-busy={busy || undefined} data-testid="paste-read">
              {busy ? t("busy.checking") : t("programWizard.courses.read")}
            </Button>
          )}
        </>
      }
    >
      <Textarea value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }} rows={6} className="font-mono" aria-label={t("programWizard.courses.pasteTitle")} data-testid="paste-text" />
      {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
      {preview ? (
        <>
          <ul className="flex max-h-56 flex-col overflow-auto rounded-lg border border-hairline type-footnote" aria-label={t("programWizard.courses.previewRows")} data-testid="paste-preview">
            {preview.rows.map((r) => {
              const typed = (raw[r.line - 1] ?? "").split("\t")[0]?.trim() ?? "";
              const fixed = typed && typed !== r.code && !r.code_error;
              return (
                <li key={r.line} className="flex flex-col border-b border-hairline px-2 py-1 last:border-b-0">
                  <span className="flex flex-wrap gap-x-3">
                    <span className="font-semibold">{r.code}</span>
                    <span className="min-w-0 flex-1">{r.name}</span>
                    <span className="tabular-nums text-label-2">T{r.t ?? "—"} U{r.u ?? "—"} L{r.l ?? "—"} · {t("programWizard.col.ects")} {r.ects ?? "—"} · {t("programWizard.col.year")} {r.year ?? "—"}</span>
                  </span>
                  {fixed ? <span className="type-caption text-label-2">ⓘ {t("programWizard.v.codeFixed", { from: typed, to: r.code })}</span> : null}
                  {r.code_error ? <span className="type-caption text-status-infeasible-fg">✕ {t("programWizard.courses.badCode", { code: r.code })}</span> : null}
                  {dups.has(r.line) ? <span className="type-caption text-status-warning-fg">⚠ {t("programWizard.courses.duplicate", { code: r.code })}</span> : null}
                </li>
              );
            })}
          </ul>
          <p className="type-footnote text-label-2" aria-live="polite" data-testid="paste-count">{t("programWizard.courses.pasteCount", { n: n(rows.length), ignored: n(preview.ignored.length + (preview.rows.length - rows.length)) })}</p>
        </>
      ) : null}
    </ResponsiveDialog>
  );
}

/** "Var olan dersi ekle": a catalogue course reused as is (MBG 014, lisans), never edited from the wizard */
function ExistingCourse({ onPick }: { onPick: (c: CourseP) => void }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const found = useQuery({ queryKey: ["wizard", "courses", q], queryFn: () => catalogApi.courses(q), enabled: q.trim().length >= 2, staleTime: 30_000 });
  const listId = useId();
  return (
    <div className="relative w-full sm:w-72">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("programWizard.courses.existingPh")} aria-label={t("programWizard.courses.existing")} aria-controls={listId} data-testid="wizard-existing-course" />
      {q.trim().length >= 2 && found.data?.items.length ? (
        <ul id={listId} role="listbox" aria-label={t("programWizard.courses.existing")} className="absolute z-20 mt-1 flex max-h-60 w-full flex-col overflow-auto rounded-lg border border-hairline bg-(--mat-thick-solid) p-1">
          {found.data.items.slice(0, 12).map((c) => (
            <li key={c.id} role="option" aria-selected={false}>
              <Button variant="ghost" size="sm" className="h-auto min-h-11 w-full justify-start whitespace-normal text-left md:min-h-8" onClick={() => { onPick(newCourse({ course_id: c.id, code: c.display_code, name: c.name ?? "", t: c.t_hours ?? 0, u: c.u_hours ?? 0, l: c.l_hours ?? 0, credits: c.credits, ects: c.ects, pattern: { theory_blocks: c.t_hours ? [c.t_hours] : [], weekly_hours: (c.t_hours ?? 0) + (c.u_hours ?? 0) + (c.l_hours ?? 0) ? null : 1, days: [1, 2, 3, 4, 5], start: "", weeks: "1-14" } })); setQ(""); }}>
                <span className="font-semibold">{c.display_code}</span> {c.name}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function CoursesStep({ p, update, v, draftId }: StepProps & { draftId: number }) {
  const { t, n } = useI18n();
  const [paste, setPaste] = useState(false);
  const phone = usePhone();
  const [codeFix, setCodeFix] = useState<Record<string, string>>({});
  const blurCode = (c: CourseP) => {
    const nc = normalizeCode(c.code);
    if (!nc.error && nc.code !== c.code) {
      setCodeFix((m) => ({ ...m, [c.key]: t("programWizard.v.codeFixed", { from: c.code, to: nc.code }) }));
      patchCourse(update, c.key, (x) => ({ ...x, code: nc.code }));
    }
  };
  const remove = (c: CourseP) =>
    update((x) => ({ ...x, courses: x.courses.filter((y) => y.key !== c.key), cohorts: x.cohorts.map((co) => ({ ...co, compulsory: co.compulsory.filter((k) => k !== c.key), elective_groups: co.elective_groups.map((g) => g.filter((k) => k !== c.key)).filter((g) => g.length) })) }));
  const rowIssues = (c: CourseP) => issuesUnder(v, `courses.${c.key}`).filter((i) => i.step === "courses");
  const numField = (c: CourseP, k: "t" | "u" | "l" | "credits" | "ects", cls: string) => (
    <Input inputMode="decimal" className={cls} value={num(c[k])} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, [k]: parseNumber(e.target.value) }))} aria-label={`${c.code || "—"} ${k === "ects" ? t("programWizard.col.ects") : k === "credits" ? t("programWizard.col.credits") : k.toUpperCase()}`} data-path={`courses.${c.key}.${k}`} disabled={c.course_id !== null && k !== "ects"} />
  );
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <Button variant="outline" onClick={() => setPaste(true)} data-testid="wizard-paste"><ClipboardPaste aria-hidden />{t("programWizard.courses.paste")}</Button>
        <Button variant="ghost" onClick={() => update((x) => ({ ...x, courses: [...x.courses, newCourse({ code: x.program.prefix ? `${x.program.prefix} ` : "" })] }))} data-testid="wizard-add-course"><Plus aria-hidden />{t("programWizard.courses.add")}</Button>
        <ExistingCourse onPick={(c) => update((x) => ({ ...x, courses: [...x.courses, c] }))} />
        <span className="type-footnote text-label-2 tabular-nums sm:ml-auto">{t("programWizard.courses.count", { n: n(p.courses.length) })}</span>
      </div>
      {p.courses.length && phone ? (
        <ul className="flex flex-col gap-2" data-testid="courses-grid">
          {p.courses.map((c) => (
            <li key={c.key} className="flex flex-col gap-2 rounded-xl border border-hairline p-3" data-testid="course-row">
              <div className="flex gap-2">
                <Input value={c.code} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, code: e.target.value }))} onBlur={() => blurCode(c)} className="w-32" aria-label={t("programWizard.col.code")} data-path={`courses.${c.key}.code`} aria-invalid={hasError(v, `courses.${c.key}.code`) || undefined} disabled={c.course_id !== null} />
                <Button variant="ghost" size="icon" className="ml-auto" aria-label={t("programWizard.courses.remove", { code: c.code || "—" })} onClick={() => remove(c)}><Trash2 aria-hidden /></Button>
              </div>
              <Input value={c.name} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, name: e.target.value }))} aria-label={t("programWizard.col.name")} data-path={`courses.${c.key}.name`} disabled={c.course_id !== null} />
              {codeFix[c.key] ? <span className="type-caption text-label-2">ⓘ {codeFix[c.key]}</span> : null}
              <div className="grid grid-cols-3 gap-2">
                {(["t", "u", "l"] as const).map((k) => (
                  <label key={k} className="flex flex-col gap-0.5 type-caption text-label-2">{k.toUpperCase()}{numField(c, k, "")}</label>
                ))}
                <label className="flex flex-col gap-0.5 type-caption text-label-2">{t("programWizard.col.credits")}{numField(c, "credits", "")}</label>
                <label className="flex flex-col gap-0.5 type-caption text-label-2">{t("programWizard.col.ects")}{numField(c, "ects", "")}</label>
                <label className="flex flex-col gap-0.5 type-caption text-label-2">{t("programWizard.col.year")}<Input inputMode="numeric" value={String(c.year)} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, year: Math.max(1, Number(e.target.value) || 1) }))} /></label>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <NativeSelect value={c.compulsory ? "c" : "e"} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, compulsory: e.target.value === "c" }))} aria-label={t("programWizard.col.kind")}>
                  <option value="c">{t("programWizard.courses.compulsory")}</option>
                  <option value="e">{t("programWizard.courses.elective")}</option>
                </NativeSelect>
                <NativeSelect value={c.mode} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, mode: e.target.value as CourseP["mode"] }))} aria-label={t("programWizard.col.mode")}>
                  {MODES.map((m) => <option key={m} value={m}>{t(`programWizard.mode.${m}`)}</option>)}
                </NativeSelect>
              </div>
              {c.course_id !== null ? <span className="type-caption text-label-2">{t("programWizard.courses.reused")}</span> : null}
              <IssueLines issues={rowIssues(c)} />
            </li>
          ))}
        </ul>
      ) : p.courses.length ? (
        <div className="overflow-x-auto rounded-xl border border-hairline">
          <table className="w-full min-w-[60rem] type-callout" data-testid="courses-grid">
            <thead className="bg-(--mat-thick-solid) text-left type-caption text-label-2">
              <tr>
                <th className="px-2 py-1.5">{t("programWizard.col.code")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.name")}</th>
                <th className="px-2 py-1.5" title={t("programWizard.col.tHint")}>T</th>
                <th className="px-2 py-1.5" title={t("programWizard.col.uHint")}>U</th>
                <th className="px-2 py-1.5" title={t("programWizard.col.lHint")}>L</th>
                <th className="px-2 py-1.5">{t("programWizard.col.credits")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.ects")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.year")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.kind")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.mode")}</th>
                <th className="px-2 py-1.5"><span className="sr-only">{t("common.actions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {p.courses.map((c) => (
                <tr key={c.key} className="border-t border-hairline align-top" data-testid="course-row">
                  <td className="px-2 py-1">
                    <Input value={c.code} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, code: e.target.value }))} onBlur={() => blurCode(c)} className="w-28" aria-label={t("programWizard.col.code")} data-path={`courses.${c.key}.code`} aria-invalid={hasError(v, `courses.${c.key}.code`) || undefined} aria-describedby={`e-${c.key}`} disabled={c.course_id !== null} />
                  </td>
                  <td className="px-2 py-1">
                    <Input value={c.name} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, name: e.target.value }))} aria-label={t("programWizard.col.name")} data-path={`courses.${c.key}.name`} disabled={c.course_id !== null} />
                    {codeFix[c.key] ? <span className="block type-caption text-label-2">ⓘ {codeFix[c.key]}</span> : null}
                    {c.course_id !== null ? <span className="block type-caption text-label-2">{t("programWizard.courses.reused")}</span> : null}
                    <IssueLines issues={rowIssues(c)} id={`e-${c.key}`} />
                  </td>
                  {(["t", "u", "l", "credits", "ects"] as const).map((k) => <td key={k} className="px-2 py-1">{numField(c, k, "w-14")}</td>)}
                  <td className="px-2 py-1"><Input inputMode="numeric" className="w-12" value={String(c.year)} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, year: Math.max(1, Number(e.target.value) || 1) }))} aria-label={t("programWizard.col.year")} /></td>
                  <td className="px-2 py-1">
                    <NativeSelect value={c.compulsory ? "c" : "e"} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, compulsory: e.target.value === "c" }))} aria-label={t("programWizard.col.kind")}>
                      <option value="c">{t("programWizard.courses.compulsory")}</option>
                      <option value="e">{t("programWizard.courses.elective")}</option>
                    </NativeSelect>
                  </td>
                  <td className="px-2 py-1">
                    <NativeSelect value={c.mode} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, mode: e.target.value as CourseP["mode"] }))} aria-label={t("programWizard.col.mode")}>
                      {MODES.map((m) => <option key={m} value={m}>{t(`programWizard.mode.${m}`)}</option>)}
                    </NativeSelect>
                  </td>
                  <td className="px-2 py-1"><Button variant="ghost" size="icon-sm" aria-label={t("programWizard.courses.remove", { code: c.code || "—" })} onClick={() => remove(c)}><Trash2 aria-hidden /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="type-callout text-label-2">{t("programWizard.courses.empty")}</p>
      )}
      <IssueLines issues={issuesAt(v, "courses")} />
      <p className="type-footnote text-label-2">{t("programWizard.courses.saveNote")}</p>
      <PasteDialog draftId={draftId} open={paste} onOpenChange={setPaste} existing={p.courses} onInsert={(rows) => update((x) => ({ ...x, courses: [...x.courses, ...rows] }))} />
    </div>
  );
}

/* ------------------------------------------------------------------ 3 sections + joint teaching */

function JointPicker({ termId, section, onLink }: { termId: number; section: SectionP; onLink: (id: number, label: string, enrolment: number | null, periods: number | null) => void }) {
  const { t, n } = useI18n();
  const [q, setQ] = useState("");
  const found = useSectionSearch(termId, q);
  const listId = useId();
  const items = (found.data?.items ?? []).filter((s) => !section.joint_section_ids.includes(s.section_id));
  return (
    <div className="relative w-full sm:w-80">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("programWizard.sections.jointPh")} aria-label={t("programWizard.sections.jointAdd")} aria-controls={listId} data-testid="joint-search" />
      {q.trim().length >= 2 ? (
        <ul id={listId} role="listbox" aria-label={t("programWizard.sections.jointAdd")} className="absolute z-20 mt-1 flex max-h-64 w-full flex-col overflow-auto rounded-lg border border-hairline bg-(--mat-thick-solid) p-1" data-testid="joint-results">
          {found.isFetching && !found.data ? <li className="px-2 py-1 type-footnote text-label-2">{t("busy.searching")}</li> : null}
          {found.data && !items.length ? <li className="px-2 py-1 type-footnote text-label-2">{t("programWizard.sections.jointNone")}</li> : null}
          {items.map((s) => {
            const label = [s.course_code, s.label ? `§${s.label}` : null, s.course_name].filter(Boolean).join(" ");
            const sub = [s.program_name, s.class_years.length ? t("programWizard.sections.years", { years: s.class_years.join(", ") }) : null, s.enrolment !== null ? t("programWizard.sections.students", { n: n(s.enrolment) }) : null, t("programWizard.sections.periods", { n: s.periods_per_week })].filter(Boolean).join(" · ");
            return (
              <li key={s.section_id} role="option" aria-selected={false}>
                <Button variant="ghost" size="sm" className="h-auto min-h-11 w-full flex-col items-start justify-start whitespace-normal text-left md:min-h-8" onClick={() => { onLink(s.section_id, `${label}${s.program_name ? ` · ${s.program_name}` : ""}`, s.enrolment, s.periods_per_week); setQ(""); }} data-testid="joint-option">
                  <span className="font-semibold">{label}</span>
                  <span className="type-caption text-label-2">{sub}</span>
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export function SectionsStep({ p, update, v, termId }: StepProps) {
  const { t, n } = useI18n();
  if (!p.courses.length) return <p className="type-callout text-label-2">{t("programWizard.sections.noCourses")}</p>;
  return (
    <div className="flex flex-col gap-4">
      {p.courses.map((c) => (
        <section key={c.key} aria-labelledby={`sec-${c.key}`} className="flex flex-col gap-2 border-b border-hairline pb-3" data-testid="sections-course">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={`sec-${c.key}`} className="min-w-0 flex-1 type-headline">{c.code} {c.name}</h3>
            <span className="type-footnote text-label-2">{t("programWizard.sections.count", { n: c.sections.length })}</span>
            <Button variant="ghost" size="icon-sm" className={TOUCH} aria-label={t("programWizard.sections.less", { code: c.code })} disabled={c.sections.length <= 1} onClick={() => patchCourse(update, c.key, (x) => ({ ...x, sections: x.sections.slice(0, -1) }))}><Minus aria-hidden /></Button>
            <Button variant="ghost" size="icon-sm" className={TOUCH} aria-label={t("programWizard.sections.more", { code: c.code })} onClick={() => patchCourse(update, c.key, (x) => ({ ...x, sections: [...x.sections, newSection(String(x.sections.length + 1), x.sections[0]?.enrolment ?? null)] }))}><Plus aria-hidden /></Button>
          </div>
          <IssueLines issues={issuesAt(v, `courses.${c.key}.sections`)} />
          {c.sections.map((s) => {
            const sp = `courses.${c.key}.sections.${s.key}`;
            const total = jointTotal(s);
            return (
              <div key={s.key} className="flex flex-col gap-2 rounded-xl border border-hairline p-3 sm:ml-2" data-testid="section-row">
                <div className="flex flex-wrap items-start gap-3">
                  <label className="flex flex-col gap-0.5">
                    <span className="type-caption text-label-2">{t("programWizard.sections.label")}</span>
                    <Input className="w-20" value={s.label} onChange={(e) => patchSection(update, c.key, s.key, (x) => ({ ...x, label: e.target.value }))} data-path={`${sp}.label`} />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="type-caption text-label-2">{t("programWizard.sections.enrolment")}</span>
                    <Input inputMode="numeric" className="w-28" value={s.enrolment ?? ""} onChange={(e) => patchSection(update, c.key, s.key, (x) => ({ ...x, enrolment: e.target.value ? Math.max(0, Number(e.target.value) || 0) : null }))} data-path={`${sp}.enrolment`} aria-invalid={hasError(v, `${sp}.enrolment`) || undefined} aria-describedby={`e-${s.key}-en`} data-testid="section-enrolment" />
                  </label>
                  {s.joint_section_ids.length ? (
                    <p className="self-end pb-2 type-callout" data-testid="joint-total">{t("programWizard.sections.jointTotal", { n: n(total) })}</p>
                  ) : null}
                </div>
                <IssueLines issues={[...issuesAt(v, `${sp}.label`), ...issuesAt(v, `${sp}.enrolment`)]} id={`e-${s.key}-en`} />
                <div className="flex flex-col gap-1">
                  <span className="inline-flex items-center gap-1 type-caption text-label-2"><Link2 className="size-3.5" aria-hidden />{t("programWizard.sections.joint")}</span>
                  {s.joint_section_ids.length ? (
                    <ul className="flex flex-wrap gap-1.5" aria-label={t("programWizard.sections.joint")} data-testid="joint-links">
                      {s.joint_section_ids.map((id) => {
                        const info = s.joint_labels?.[jointKey(id)];
                        return (
                          <li key={id}>
                            <Chip className={TOUCH} removeLabel={t("programWizard.sections.jointRemove", { label: info?.label ?? `#${id}` })} onRemove={() => patchSection(update, c.key, s.key, (x) => { const labels = { ...(x.joint_labels ?? {}) }; delete labels[jointKey(id)]; return { ...x, joint_section_ids: x.joint_section_ids.filter((y) => y !== id), joint_labels: labels }; })}>
                              {info?.label ?? `#${id}`}{info?.enrolment !== null && info?.enrolment !== undefined ? ` · ${n(info.enrolment)}` : ""}
                            </Chip>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                  <JointPicker termId={termId} section={s} onLink={(id, label, enrolment, periods) => patchSection(update, c.key, s.key, (x) => ({ ...x, joint_section_ids: [...x.joint_section_ids, id], joint_labels: { ...(x.joint_labels ?? {}), [jointKey(id)]: { label, enrolment, periods } } }))} />
                  <IssueLines issues={issuesAt(v, `${sp}.joint`)} />
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ 4 instructors + load */

function InstructorPicker({ termId, value, onChange, label, testId }: { termId: number; value: InstructorRef | null; onChange: (v: InstructorRef | null) => void; label: string; testId?: string }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const found = useInstructorSearch(open ? termId : null, q);
  const listId = useId();
  if (value) {
    return (
      <span className="inline-flex min-h-11 items-center gap-1 type-callout md:min-h-8" data-testid="picked-instructor">
        <span className="min-w-0 truncate">{[value.title, value.name].filter(Boolean).join(" ") || `#${value.id}`}{!value.id ? ` · ${t("programWizard.sections.newPerson")}` : ""}</span>
        <Button variant="ghost" size="icon-sm" className={TOUCH} aria-label={t("programWizard.sections.clear", { label })} onClick={() => onChange(null)}><X aria-hidden /></Button>
      </span>
    );
  }
  return (
    <div className="relative w-full sm:w-72">
      <Input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} placeholder={t("programWizard.sections.searchPerson")} aria-label={label} aria-controls={listId} data-testid={testId} />
      {open && q.trim().length >= 2 ? (
        <ul id={listId} role="listbox" aria-label={label} className="absolute z-20 mt-1 flex max-h-64 w-full flex-col overflow-auto rounded-lg border border-hairline bg-(--mat-thick-solid) p-1">
          {(found.data?.items ?? []).map((i) => (
            <li key={i.instructor_id} role="option" aria-selected={false}>
              <Button variant="ghost" size="sm" className="h-auto min-h-11 w-full justify-between gap-2 whitespace-normal text-left md:min-h-8" onMouseDown={(e) => e.preventDefault()} onClick={() => { onChange({ id: i.instructor_id, name: i.full_name, title: i.title }); setQ(""); }}>
                <span>{[i.title, i.full_name].filter(Boolean).join(" ")}</span>
                <span className={cn("shrink-0 type-caption", i.over_limit ? "text-status-warning-fg" : "text-label-2")}>{i.over_limit ? "⚠ " : ""}{t("programWizard.instructors.load", { n: i.periods_per_week })}</span>
              </Button>
            </li>
          ))}
          <li role="option" aria-selected={false}>
            <Button variant="ghost" size="sm" className="h-auto min-h-11 w-full justify-start md:min-h-8" onMouseDown={(e) => e.preventDefault()} onClick={() => { onChange({ name: q.trim() }); setQ(""); }} data-testid="wizard-new-person">
              <UserPlus aria-hidden />{t("programWizard.sections.create", { name: q.trim() })}
            </Button>
          </li>
        </ul>
      ) : null}
    </div>
  );
}

export function InstructorsStep({ p, update, v, termId }: StepProps) {
  const { t } = useI18n();
  const ids = p.courses.flatMap((c) => c.sections.flatMap((s) => s.instructors.map((i) => i.id).filter((x): x is number => typeof x === "number")));
  const loads = useInstructorLoads(termId, ids);
  const byId = new Map((loads.data?.items ?? []).map((i) => [i.instructor_id, i]));
  if (!p.courses.length) return <p className="type-callout text-label-2">{t("programWizard.sections.noCourses")}</p>;
  const setSlot = (c: CourseP, s: SectionP, slot: 0 | 1, ref: InstructorRef | null) =>
    patchSection(update, c.key, s.key, (x) => {
      const next: (InstructorRef | null)[] = [x.instructors[0] ?? null, x.instructors[1] ?? null];
      next[slot] = ref;
      return { ...x, instructors: next.filter((r): r is InstructorRef => r !== null) };
    });
  return (
    <div className="flex flex-col gap-4">
      {loads.data ? <p className="type-footnote text-label-2">{t("programWizard.instructors.limit", { n: loads.data.limit })}</p> : null}
      {p.courses.map((c) => (
        <section key={c.key} aria-labelledby={`ins-${c.key}`} className="flex flex-col gap-2 border-b border-hairline pb-3" data-testid="instructors-course">
          <h3 id={`ins-${c.key}`} className="type-headline">{c.code} {c.name}</h3>
          {c.sections.map((s) => {
            const sp = `courses.${c.key}.sections.${s.key}`;
            return (
              <div key={s.key} className="flex flex-col gap-2 sm:ml-2" data-testid="instructor-row">
                <span className="type-footnote text-label-2">§{s.label}</span>
                <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                  {([0, 1] as const).map((slot) => {
                    const ref = s.instructors[slot] ?? null;
                    const load = ref?.id ? byId.get(ref.id) : undefined;
                    const label = t(slot === 0 ? "programWizard.sections.first" : "programWizard.sections.second");
                    if (slot === 1 && !s.instructors[0]) return null;
                    return (
                      <div key={slot} className="flex flex-col gap-0.5" data-path={`${sp}.instructors.${slot}`}>
                        <span className="type-caption text-label-2">{label}</span>
                        <InstructorPicker termId={termId} value={ref} label={label} testId={slot === 0 ? "section-instructor" : "section-instructor-2"} onChange={(r) => setSlot(c, s, slot, r)} />
                        {load ? <span className={cn("type-caption", load.over_limit ? "text-status-warning-fg" : "text-label-2")} data-testid="instructor-load">{load.over_limit ? "⚠ " : ""}{t("programWizard.instructors.load", { n: load.periods_per_week })}</span> : null}
                        <IssueLines issues={issuesAt(v, `${sp}.instructors.${slot}`)} />
                        {issuesAt(v, `${sp}.instructors.${slot}`).map(namesakeRecord).filter((r) => r !== null).slice(0, 1).map((r) => (
                          <Button
                            key={r.id}
                            size="sm"
                            variant="outline"
                            className={cn("self-start", TOUCH)}
                            aria-label={t("programWizard.v.useThisLabel", { name: r.name })}
                            onClick={() => {
                              setSlot(c, s, slot, { id: r.id, name: r.name });
                              toast.success(t("programWizard.v.usedThis", { name: r.name }));
                            }}
                            data-testid="use-archived-person"
                          >
                            <History aria-hidden />
                            {t("programWizard.v.useThis")}
                          </Button>
                        ))}
                      </div>
                    );
                  })}
                </div>
                <IssueLines issues={issuesAt(v, `${sp}.instructors`)} />
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ 5 cohorts */

export function CohortsStep({ p, update, v }: StepProps) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const prefix = p.program.prefix || p.program.name.split(/\s+/)[0] || "";
  const label = (year: number) => newCohortLabel(prefix, year, lang);
  const setCohort = (key: string, fn: (c: CohortP) => CohortP) => update((x) => ({ ...x, cohorts: x.cohorts.map((c) => (c.key === key ? fn(c) : c)) }));
  const toggle = (list: string[], key: string, on: boolean) => (on ? [...new Set([...list, key])] : list.filter((k) => k !== key));
  const missing = uncohorted(p);
  if (!p.courses.length) return <p className="type-callout text-label-2">{t("programWizard.sections.noCourses")}</p>;
  return (
    <div className="flex flex-col gap-4">
      <p className="type-footnote text-label-2">{t("programWizard.cohorts.intro")}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button variant="outline" onClick={() => update((x) => ({ ...x, cohorts: cohortsFromYears(x, label) }))} data-testid="cohorts-build"><Users aria-hidden />{t("programWizard.cohorts.fromYears")}</Button>
        <Button variant="ghost" onClick={() => update((x) => ({ ...x, cohorts: [...x.cohorts, { key: newKey("y"), label: label(1), year: 1, compulsory: [], elective_groups: [] }] }))}><Plus aria-hidden />{t("programWizard.cohorts.add")}</Button>
      </div>
      {!p.cohorts.length ? <p className="type-callout text-label-2" data-testid="cohorts-empty">{t("programWizard.cohorts.empty")}</p> : null}
      {p.cohorts.map((co) => {
        const issues = issuesAt(v, `cohorts.${co.key}`);
        const electives = co.elective_groups[0] ?? [];
        return (
          <section key={co.key} aria-label={co.label} className="flex flex-col gap-2 rounded-xl border border-hairline p-3" data-testid="cohort">
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="type-caption text-label-2">{t("programWizard.cohorts.label")}</span>
                <Input value={co.label} onChange={(e) => setCohort(co.key, (c) => ({ ...c, label: e.target.value }))} />
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="type-caption text-label-2">{t("programWizard.col.year")}</span>
                <Input inputMode="numeric" className="w-16" value={String(co.year)} onChange={(e) => setCohort(co.key, (c) => ({ ...c, year: Math.max(1, Number(e.target.value) || 1) }))} />
              </label>
              <Button variant="ghost" size="icon" aria-label={t("programWizard.cohorts.remove", { label: co.label })} onClick={() => update((x) => ({ ...x, cohorts: x.cohorts.filter((c) => c.key !== co.key) }))}><Trash2 aria-hidden /></Button>
            </div>
            <div className="flex flex-col gap-1" role="group" aria-label={t("programWizard.cohorts.compulsory")}>
              <span className="type-caption text-label-2">{t("programWizard.cohorts.compulsory")}</span>
              <div className="flex flex-wrap gap-1.5">
                {p.courses.map((c) => (
                  <Chip key={c.key} size="sm" className={TOUCH} selected={co.compulsory.includes(c.key)} onSelectedChange={(on) => setCohort(co.key, (x) => ({ ...x, compulsory: toggle(x.compulsory, c.key, on), elective_groups: on ? x.elective_groups.map((g) => g.filter((k) => k !== c.key)).filter((g) => g.length) : x.elective_groups }))}>
                    {c.code || "—"}
                  </Chip>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-1" role="group" aria-label={t("programWizard.cohorts.electives")}>
              <span className="type-caption text-label-2">{t("programWizard.cohorts.electives")}</span>
              <div className="flex flex-wrap gap-1.5">
                {p.courses.filter((c) => !co.compulsory.includes(c.key)).map((c) => (
                  <Chip key={c.key} size="sm" className={TOUCH} selected={electives.includes(c.key)} onSelectedChange={(on) => setCohort(co.key, (x) => { const g = toggle(x.elective_groups[0] ?? [], c.key, on); return { ...x, elective_groups: g.length ? [g, ...x.elective_groups.slice(1)] : x.elective_groups.slice(1) }; })}>
                    {c.code || "—"}
                  </Chip>
                ))}
              </div>
            </div>
            <IssueLines issues={issues} />
          </section>
        );
      })}
      {missing.length ? (
        <p className="type-footnote text-status-warning-fg" data-testid="cohorts-missing">⚠ {t("programWizard.cohorts.missing", { codes: missing.map((c) => c.code).join(", ") })}</p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ 6 rooms + weekly patterns */

function FitLine({ termId, c }: { termId: number; c: CourseP }) {
  const { t, n } = useI18n();
  const cap = neededCapacity(c);
  const fit = useRoomsFit(c.mode === "ONLINE" || c.mode === "UZEM" ? null : termId, cap, c.room.tags, c.room.building);
  if (c.mode === "ONLINE" || c.mode === "UZEM") return <p className="type-footnote text-label-2">{t("programWizard.patterns.online")}</p>;
  if (!cap) return <p className="type-footnote text-label-2">{t("programWizard.patterns.noCapacity")}</p>;
  if (!fit.data) return <p className="type-footnote text-label-3">{t("busy.checking")}</p>;
  return (
    <p className={cn("type-footnote", fit.data.count ? "text-label-2" : "text-status-infeasible-fg")} data-testid="fit-line" aria-live="polite">
      {fit.data.count ? t("programWizard.v.fits", { n: n(cap), count: n(fit.data.count), rooms: fit.data.items.slice(0, 4).map((r) => `${r.display_name} (${r.capacity})`).join(", ") }) : t("programWizard.patterns.noFit", { n: n(cap) })}
    </p>
  );
}

export function RoomsStep({ p, update, v, termId, rooms }: StepProps & { rooms: readonly Room[] }) {
  const { t, locale } = useI18n();
  const buildings = useMemo(() => [...new Set(rooms.map((r) => r.building_code).filter((b): b is string => !!b))].sort((a, b) => a.localeCompare(b, "tr")), [rooms]);
  // the tags the room pool has (a tag no room carries could only fail); TIP stays for medicine programmes
  const tags = useMemo(() => [...new Set(rooms.flatMap((r) => (r.tags as string[]) ?? []))].sort(), [rooms]);
  const roomNames = useMemo(() => rooms.filter((r) => r.is_bookable).map((r) => r.display_name).sort((a, b) => a.localeCompare(b, "tr", { numeric: true })), [rooms]);
  if (!p.courses.length) return <p className="type-callout text-label-2">{t("programWizard.sections.noCourses")}</p>;
  const startOptions = p.program.evening ? PERIODS.filter((x) => x.index >= 12) : PERIODS.filter((x) => x.index <= 12);
  return (
    <div className="flex flex-col gap-5">
      <datalist id="wizard-rooms">{roomNames.map((r) => <option key={r} value={r} />)}</datalist>
      {p.courses.map((c) => {
        const cp = `courses.${c.key}`;
        const hours = courseHours(c);
        const opts = patternOptions(c.t ?? 0);
        const cap = neededCapacity(c);
        const mine = issuesUnder(v, cp).filter((i) => i.step === "rooms");
        const setPat = (patch: Partial<CourseP["pattern"]>) => patchCourse(update, c.key, (x) => ({ ...x, pattern: { ...x.pattern, ...patch } }));
        const setRoom = (patch: Partial<CourseP["room"]>) => patchCourse(update, c.key, (x) => ({ ...x, room: { ...x.room, ...patch } }));
        return (
          <section key={c.key} aria-labelledby={`pat-${c.key}`} className="flex flex-col gap-2 border-b border-hairline pb-4" data-testid="pattern-course">
            <h3 id={`pat-${c.key}`} className="type-headline">{c.code} {c.name} <span className="type-footnote font-normal text-label-2">T{c.t ?? 0} U{c.u ?? 0} L{c.l ?? 0} · {t("programWizard.patterns.placed", { n: patternHours(c) })}</span></h3>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
              {hours ? (
                opts.length > 1 ? (
                  <div className="flex flex-col gap-1">
                    <span className="type-caption text-label-2">{t("programWizard.patterns.split")}</span>
                    <SegmentedControl<string>
                      aria-label={t("programWizard.patterns.split")}
                      semantics="radiogroup"
                      size="sm"
                      value={(c.pattern.theory_blocks.length ? c.pattern.theory_blocks : [c.t ?? 0]).join("+")}
                      onValueChange={(val) => setPat({ theory_blocks: val.split("+").map(Number) })}
                      options={opts.map((o) => ({ value: o.join("+"), label: o.length === 1 ? t("programWizard.patterns.oneBlock", { n: o[0]! }) : o.join(" + ") }))}
                    />
                  </div>
                ) : null
              ) : (
                <label className="flex flex-col gap-1">
                  <span className="type-caption text-label-2">{t("programWizard.patterns.weekly")}</span>
                  <Input inputMode="numeric" className="sm:w-20" value={c.pattern.weekly_hours ?? ""} onChange={(e) => setPat({ weekly_hours: e.target.value ? Math.max(0, Number(e.target.value) || 0) : null })} data-path={`${cp}.pattern.weekly_hours`} data-testid="pattern-weekly" />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.start")}</span>
                <NativeSelect className="sm:w-36" value={c.pattern.start} onChange={(e) => setPat({ start: e.target.value })} data-path={`${cp}.pattern.start`} aria-invalid={hasError(v, `${cp}.pattern.start`) || undefined} data-testid="pattern-start">
                  <option value="">{t("programWizard.patterns.pickStart")}</option>
                  {startOptions.map((o) => <option key={o.index} value={o.start}>P{o.index} {o.start}</option>)}
                </NativeSelect>
              </label>
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.weeks")}</span>
                <Input className="sm:w-24" value={c.pattern.weeks} onChange={(e) => setPat({ weeks: e.target.value })} data-path={`${cp}.pattern.weeks`} />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("programWizard.patterns.days")} data-path={`${cp}.pattern.days`}>
              <span className="w-full type-caption text-label-2 sm:w-auto">{t("programWizard.patterns.days")}</span>
              {[1, 2, 3, 4, 5, 6].map((day) => (
                <Chip key={day} size="sm" className={TOUCH} selected={c.pattern.days.includes(day)} onSelectedChange={(on) => setPat({ days: on ? [...c.pattern.days, day].sort((a, b) => a - b) : c.pattern.days.filter((y) => y !== day) })} data-testid={`day-${day}`}>
                  {dayName(day, locale, "short")}
                </Chip>
              ))}
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.capacity")}</span>
                <Input inputMode="numeric" className="sm:w-24" value={c.room.capacity ?? ""} placeholder={cap ? String(cap) : undefined} onChange={(e) => setRoom({ capacity: e.target.value ? Number(e.target.value) || null : null })} data-path={`${cp}.room.capacity`} />
              </label>
              {tags.length ? (
                <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("programWizard.patterns.tags")}>
                  <span className="w-full type-caption text-label-2 sm:w-auto">{t("programWizard.patterns.tags")}</span>
                  {tags.map((tag) => (
                    <Chip key={tag} size="sm" className={TOUCH} selected={c.room.tags.includes(tag)} onSelectedChange={(on) => setRoom({ tags: on ? [...c.room.tags, tag] : c.room.tags.filter((y) => y !== tag) })}>
                      {tag}
                    </Chip>
                  ))}
                </div>
              ) : null}
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.building")}</span>
                <NativeSelect className="sm:w-32" value={c.room.building} onChange={(e) => setRoom({ building: e.target.value })}>
                  <option value="">{t("programWizard.patterns.anyBuilding")}</option>
                  {buildings.map((b) => <option key={b} value={b}>{b}</option>)}
                </NativeSelect>
              </label>
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.preferred")}</span>
                <Input className="sm:w-28" list="wizard-rooms" value={c.room.preferred} onChange={(e) => setRoom({ preferred: e.target.value })} data-path={`${cp}.room.preferred`} data-testid="pattern-preferred" />
              </label>
            </div>
            {/* live consequence line (spec §4.6), from GET /terms/{id}/rooms/fit */}
            <FitLine termId={termId} c={c} />
            <IssueLines issues={mine} />
          </section>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ 7 constraints + pre-check */

/** the draft errors of a refused pre-check / commit (422), each with "Düzelt" to its step */
export function RefusedIssues({ issues, onFix }: { issues: readonly DraftIssue[]; onFix: (s: Step) => void }) {
  const { t } = useI18n();
  return (
    <ul className="flex flex-col gap-1" data-testid="refused-issues">
      {issues.map((i, k) => (
        <li key={`${i.code}-${i.path}-${k}`} className="flex flex-wrap items-start gap-x-2">
          <IssueLines issues={[i]} className="min-w-0 flex-1" />
          <Button variant="link" size="xs" className="max-md:h-11" onClick={() => onFix(i.step)}>{t("programWizard.precheck.goFix")}</Button>
        </li>
      ))}
    </ul>
  );
}

/** where "Düzelt" sends a pre-check item: capacity and tags are room needs, clashes are people, the rest patterns */
export function stepOfPrecheck(group: string): Step {
  if (group === "instructor_clash") return "instructors";
  if (group === "cohort_clash" || group === "curriculum") return "cohorts";
  return "rooms";
}

export function PrecheckPanel({ draftId, result, onResult, onFix, disabled }: { draftId: number; result: DraftPrecheck | null; onResult: (r: DraftPrecheck) => void; onFix: (s: Step) => void; disabled?: boolean }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refused, setRefused] = useState<{ issues: DraftIssue[]; errors: number } | null>(null);
  const rooms = useRooms();
  const roomName = (id: number, code: string) => rooms.data?.find((r) => r.id === id)?.display_name ?? code;
  const run = async () => {
    setBusy(true);
    setError(null);
    setRefused(null);
    try {
      onResult(await draftsApi.precheck(draftId));
    } catch (e) {
      // 422 {message, message_tr, issues, errors}: the draft's own errors, listed with a "Düzelt" each
      const r = refusedIssues(e);
      if (r) setRefused(r);
      setError(errorText(e, lang));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="flex flex-col gap-2 rounded-xl border border-hairline p-3" aria-labelledby="precheck-title" data-testid="precheck-panel">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="precheck-title" className="min-w-0 flex-1 type-headline">{t("programWizard.precheck.studio")}</h3>
        <Button size="sm" variant="outline" className={TOUCH} onClick={() => void run()} disabled={busy || disabled} aria-busy={busy || undefined} data-testid="precheck-run">
          {busy ? t("busy.checking") : t("programWizard.precheck.run")}
        </Button>
      </div>
      {disabled ? <p className="type-footnote text-label-2">{t("programWizard.precheck.fixFirst")}</p> : null}
      {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{refused ? t("programWizard.precheck.draftErrors", { n: n(refused.errors) }) : error}</p> : null}
      {refused?.issues.length ? <RefusedIssues issues={refused.issues} onFix={onFix} /> : null}
      {result ? (
        <div role="status" aria-live="polite" className="flex flex-col gap-2" data-testid="precheck-result" data-readiness={result.readiness}>
          <p className="type-callout font-semibold">{t("programWizard.precheck.result", { errors: n(result.counts.errors), warnings: n(result.counts.warnings) })} · {t(`programWizard.precheck.readiness.${result.readiness}`)}</p>
          {result.items.length ? (
            <ul className="flex flex-col gap-1">
              {result.items.map((i) => (
                <li key={i.id} className="flex flex-wrap items-start gap-x-2 type-footnote">
                  <span aria-hidden>{i.severity === "error" ? "✕" : i.severity === "warning" ? "⚠" : "ⓘ"}</span>
                  <span className="min-w-0 flex-1"><span className="font-semibold">{i.title[lang] || i.title.tr}</span> · {i.message[lang] || i.message.tr}</span>
                  <Button variant="link" size="xs" onClick={() => onFix(stepOfPrecheck(i.group))}>{t("programWizard.precheck.fix")}</Button>
                </li>
              ))}
            </ul>
          ) : null}
          {result.rooms_fit.length ? (
            <div className="flex flex-col gap-1" data-testid="precheck-rooms">
              <h4 className="type-footnote font-semibold text-label-2">{t("programWizard.precheck.roomsFit")}</h4>
              <ul className="flex flex-col gap-0.5 type-footnote">
                {result.rooms_fit.map((f) => (
                  <li key={f.event_id} className={cn(!f.rooms.length && "text-status-infeasible-fg")}>
                    <span className="font-semibold">{f.label}</span>{f.size !== null ? ` · ${t("programWizard.sections.students", { n: n(f.size) })}` : ""}: {f.rooms.length ? f.rooms.slice(0, 5).map((r) => `${roomName(r.id, r.code)} (${r.capacity ?? "?"})`).join(", ") : t("programWizard.precheck.noRoom")}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.joint_merged.length ? <p className="type-footnote text-label-2" data-testid="precheck-joint">{t("programWizard.precheck.joint", { n: n(result.joint_merged.length) })}</p> : null}
        </div>
      ) : (
        <p className="type-footnote text-label-2">{t("programWizard.precheck.hint")}</p>
      )}
    </section>
  );
}

export function ConstraintsStep({ p, update, v, draftId, precheck, onPrecheck, onFix }: StepProps & { draftId: number; precheck: DraftPrecheck | null; onPrecheck: (r: DraftPrecheck) => void; onFix: (s: Step) => void }) {
  const { t } = useI18n();
  const w = p.rules.window;
  const setW = (patch: Partial<typeof w>) => update((x) => ({ ...x, rules: { ...x.rules, window: { ...x.rules.window, ...patch } } }));
  const blocking = (v.steps ?? []).filter((s) => s.step !== "constraints" && s.step !== "generate").some((s) => s.errors.length);
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <p className="type-footnote text-label-2">{t("programWizard.constraints.intro")}</p>
      <section className="flex flex-col gap-2 rounded-xl border border-hairline p-3" data-path="rules.window">
        <label className="flex min-h-11 items-center gap-2 type-callout font-semibold">
          <Switch checked={w.enabled} onCheckedChange={(on) => setW({ enabled: on })} data-testid="rule-window" />
          {t("programWizard.constraints.window")}
        </label>
        {w.enabled ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <NativeSelect className="sm:w-36" value={w.earliest} onChange={(e) => setW({ earliest: Number(e.target.value) })} aria-label={t("programWizard.constraints.from")}>
              {PERIODS.map((x) => <option key={x.index} value={x.index}>P{x.index} {x.start}</option>)}
            </NativeSelect>
            <span className="hidden sm:inline" aria-hidden>–</span>
            <NativeSelect className="sm:w-36" value={w.latest} onChange={(e) => setW({ latest: Number(e.target.value) })} aria-label={t("programWizard.constraints.to")}>
              {PERIODS.map((x) => <option key={x.index} value={x.index}>P{x.index} {x.end}</option>)}
            </NativeSelect>
            <SegmentedControl<"soft" | "hard"> aria-label={t("programWizard.constraints.hardness")} semantics="radiogroup" size="sm" value={w.hard ? "hard" : "soft"} onValueChange={(val) => setW({ hard: val === "hard" })} options={[{ value: "soft", label: t("programWizard.constraints.soft") }, { value: "hard", label: t("programWizard.constraints.hard") }]} />
          </div>
        ) : null}
        <IssueLines issues={issuesAt(v, "rules.window")} />
      </section>
      <label className="flex min-h-11 items-center gap-2 rounded-xl border border-hairline p-3 type-callout font-semibold">
        <Switch checked={p.rules.same_room} onCheckedChange={(on) => update((x) => ({ ...x, rules: { ...x.rules, same_room: on } }))} />
        {t("programWizard.constraints.sameRoom")}
      </label>
      <p className="type-footnote text-label-2">{t("programWizard.constraints.studio")}</p>
      <PrecheckPanel draftId={draftId} result={precheck} onResult={onPrecheck} onFix={onFix} disabled={blocking} />
    </div>
  );
}

