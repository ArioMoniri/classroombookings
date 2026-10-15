"use client";
/**
 * The eight step bodies of the program wizard (program-wizard spec §4; task order: term → faculty and program →
 * courses (TSV paste) → sections + instructors → patterns and room needs → constraints → pre-check → generate).
 * Field errors appear inline with `aria-describedby`; data entry has no motion (motion.md §3.11).
 */
import { useQuery } from "@tanstack/react-query";
import { ClipboardPaste, Minus, Plus, Trash2, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { catalogApi } from "@/lib/api/catalog-admin";
import type { Room, Term } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { LEVELS, MBG_ENROLMENT, MBG_TSV, MODES, TAGS, coursesFromPaste, courseHours, fittingRooms, neededCapacity, newCourse, newSection, normalizeCode, parseNumber, parseTsv, patternHours, patternOptions, type CourseDraft, type Draft, type InstructorRef, type Issue, type SectionDraft } from "./wizard-model";

type Update = (fn: (d: Draft) => Draft) => void;

export function issueText(t: (k: MessageKey, v?: Record<string, string | number>) => string, i: Issue): string {
  return t(`programWizard.v.${i.code}` as MessageKey, i.vars);
}

function FieldMsg({ issues, path, id }: { issues: readonly Issue[]; path: string; id: string }) {
  const { t } = useI18n();
  const mine = issues.filter((i) => i.path === path);
  if (!mine.length) return null;
  return (
    <span id={id} className="flex flex-col">
      {mine.map((i, k) => (
        <span key={k} className={cn("type-caption", i.level === "error" ? "text-status-infeasible-fg" : i.level === "warning" ? "text-status-warning-fg" : "text-label-2")}>
          {i.level === "error" ? "✕ " : i.level === "warning" ? "⚠ " : "ⓘ "}
          {issueText(t, i)}
        </span>
      ))}
    </span>
  );
}

const hasError = (issues: readonly Issue[], path: string) => issues.some((i) => i.path === path && i.level === "error");

function patchCourse(update: Update, key: string, fn: (c: CourseDraft) => CourseDraft) {
  update((d) => ({ ...d, courses: d.courses.map((c) => (c.key === key ? fn(c) : c)) }));
}
function patchSection(update: Update, course: string, section: string, fn: (s: SectionDraft) => SectionDraft) {
  patchCourse(update, course, (c) => ({ ...c, sections: c.sections.map((s) => (s.key === section ? fn(s) : s)) }));
}

/* ------------------------------------------------------------------ 1 term */

export function TermStep({ d, update, terms }: { d: Draft; update: Update; terms: readonly Term[] }) {
  const { t } = useI18n();
  return (
    <div className="flex max-w-xl flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="type-callout font-semibold">{t("programWizard.term.label")}</span>
        <NativeSelect value={d.termId ?? ""} onChange={(e) => {
          const term = terms.find((x) => x.id === Number(e.target.value));
          update((x) => ({ ...x, termId: term?.id ?? null, termCode: term?.code ?? null }));
        }} data-path="termId" data-testid="wizard-term">
          <option value="">{t("programWizard.term.pick")}</option>
          {terms.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}
        </NativeSelect>
      </label>
      <p className="type-footnote text-label-2">{t("programWizard.term.hint")}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ 2 faculty + program */

export function ProgramStep({ d, update, issues }: { d: Draft; update: Update; issues: readonly Issue[] }) {
  const { t } = useI18n();
  const faculties = useQuery({ queryKey: ["wizard", "faculties"], queryFn: () => catalogApi.faculties(), staleTime: 60_000 });
  const p = d.program;
  const set = (patch: Partial<Draft["program"]>) => update((x) => ({ ...x, program: { ...x.program, ...patch } }));
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="type-callout font-semibold">{t("programWizard.program.faculty")}</span>
        <Input list="wizard-faculties" value={p.facultyName} onChange={(e) => {
          const hit = (faculties.data?.items ?? []).find((f) => f.name === e.target.value);
          set({ facultyName: e.target.value, facultyId: hit?.id ?? null });
        }} placeholder={t("programWizard.program.facultyPh")} data-path="program.faculty" aria-invalid={hasError(issues, "program.faculty") || undefined} aria-describedby="err-faculty" data-testid="wizard-faculty" />
        <datalist id="wizard-faculties">{(faculties.data?.items ?? []).map((f) => <option key={f.id} value={f.name} />)}</datalist>
        <span className="type-caption text-label-2">{p.facultyId ? t("programWizard.program.facultyExisting") : p.facultyName.trim() ? t("programWizard.program.facultyNew") : ""}</span>
        <FieldMsg issues={issues} path="program.faculty" id="err-faculty" />
      </label>
      <label className="flex flex-col gap-1">
        <span className="type-callout font-semibold">{t("programWizard.program.name")}</span>
        <Input value={p.name} onChange={(e) => set({ name: e.target.value })} placeholder="Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans" data-path="program.name" aria-invalid={hasError(issues, "program.name") || undefined} aria-describedby="err-name" data-testid="wizard-program-name" />
        <FieldMsg issues={issues} path="program.name" id="err-name" />
      </label>
      <fieldset className="flex flex-col gap-1">
        <legend className="type-callout font-semibold">{t("programWizard.program.level")}</legend>
        {/* choice cards: instant outline + radio dot, no scale (motion.md §3.11) */}
        <div role="radiogroup" className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {LEVELS.map((l) => (
            <label key={l} className={cn("flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 type-callout", p.level === l ? "border-(--accent) bg-tint-soft" : "border-hairline")}>
              <input type="radio" name="level" className="accent-(--accent)" checked={p.level === l} onChange={() => set({ level: l, years: l === "bachelor" ? 4 : l === "associate" ? 2 : l === "phd" ? 4 : 2 })} />
              {t(`programWizard.level.${l}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 type-callout">
          <Switch checked={p.evening} onCheckedChange={(v) => set({ evening: v })} />
          {t("programWizard.program.evening")}
        </label>
        <label className="flex items-center gap-2 type-callout">
          {t("programWizard.program.language")}
          <NativeSelect className="w-40" value={p.language} onChange={(e) => set({ language: e.target.value as Draft["program"]["language"] })}>
            <option value="tr">{t("programWizard.lang.tr")}</option>
            <option value="en">{t("programWizard.lang.en")}</option>
            <option value="mixed">{t("programWizard.lang.mixed")}</option>
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 type-callout">
          {t("programWizard.program.prefix")}
          <Input className="w-24" value={p.prefix} onChange={(e) => set({ prefix: e.target.value.toLocaleUpperCase("tr-TR") })} maxLength={4} data-path="program.prefix" aria-describedby="err-prefix" data-testid="wizard-prefix" />
        </label>
      </div>
      <FieldMsg issues={issues} path="program.prefix" id="err-prefix" />
    </div>
  );
}

/* ------------------------------------------------------------------ 3 courses + TSV paste */

function PasteDialog({ open, onOpenChange, onInsert }: { open: boolean; onOpenChange: (v: boolean) => void; onInsert: (rows: CourseDraft[]) => void }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const parsed = useMemo(() => parseTsv(text), [text]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl" data-testid="paste-dialog">
        <DialogHeader>
          <DialogTitle>{t("programWizard.courses.pasteTitle")}</DialogTitle>
          <DialogDescription>{t("programWizard.courses.pasteHint")}</DialogDescription>
        </DialogHeader>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} className="font-mono" aria-label={t("programWizard.courses.pasteTitle")} data-testid="paste-text" />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => setText(MBG_TSV)} data-testid="paste-example">{t("programWizard.courses.example")}</Button>
        </div>
        {parsed.rows.length ? (
          <div className="max-h-56 overflow-auto rounded-lg border border-hairline">
            <table className="w-full type-footnote">
              <thead><tr className="text-left text-label-2"><th className="px-2 py-1">{t("programWizard.col.code")}</th><th className="px-2 py-1">{t("programWizard.col.name")}</th><th className="px-2 py-1">T</th><th className="px-2 py-1">U</th><th className="px-2 py-1">L</th><th className="px-2 py-1">{t("programWizard.col.ects")}</th><th className="px-2 py-1">{t("programWizard.col.year")}</th></tr></thead>
              <tbody>
                {parsed.rows.map((r) => {
                  const nc = normalizeCode(r.code);
                  return (
                    <tr key={r.line} className="border-t border-hairline">
                      <td className="px-2 py-1">{nc.error ? r.code : nc.code}{nc.info ? <span className="text-label-3"> ← {r.code}</span> : null}</td>
                      <td className="px-2 py-1">{r.name}</td><td className="px-2 py-1">{r.t ?? "—"}</td><td className="px-2 py-1">{r.u ?? "—"}</td><td className="px-2 py-1">{r.l ?? "—"}</td><td className="px-2 py-1">{r.ects ?? "—"}</td><td className="px-2 py-1">{r.year ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
        <p className="type-footnote text-label-2" aria-live="polite">{t("programWizard.courses.pasteCount", { n: parsed.rows.length, ignored: parsed.ignored.length })}</p>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button disabled={!parsed.rows.length} onClick={() => { onInsert(coursesFromPaste(parsed.rows, text === MBG_TSV ? MBG_ENROLMENT : {})); setText(""); onOpenChange(false); }} data-testid="paste-insert">
            {t("programWizard.courses.insert", { n: parsed.rows.length })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const num = (v: number | null) => (v === null || Number.isNaN(v) ? "" : String(v));

export function CoursesStep({ d, update, issues }: { d: Draft; update: Update; issues: readonly Issue[] }) {
  const { t, n } = useI18n();
  const [paste, setPaste] = useState(false);
  const [codeFix, setCodeFix] = useState<Record<string, string>>({});
  const blurCode = (c: CourseDraft) => {
    const nc = normalizeCode(c.code);
    if (!nc.error && nc.code !== c.code) {
      setCodeFix((m) => ({ ...m, [c.key]: t("programWizard.v.codeFixed", { from: c.code, to: nc.code }) }));
      patchCourse(update, c.key, (x) => ({ ...x, code: nc.code }));
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setPaste(true)} data-testid="wizard-paste"><ClipboardPaste aria-hidden />{t("programWizard.courses.paste")}</Button>
        <Button variant="ghost" onClick={() => update((x) => ({ ...x, courses: [...x.courses, newCourse({ code: x.program.prefix ? `${x.program.prefix} ` : "" })] }))} data-testid="wizard-add-course"><Plus aria-hidden />{t("programWizard.courses.add")}</Button>
        <span className="ml-auto self-center type-footnote text-label-2 tabular-nums">{t("programWizard.courses.count", { n: n(d.courses.length) })}</span>
      </div>
      {d.courses.length ? (
        <div className="overflow-x-auto rounded-xl border border-hairline">
          <table className="w-full min-w-[52rem] type-callout" data-testid="courses-grid">
            <thead className="bg-(--mat-thick-solid) text-left type-caption text-label-2">
              <tr>
                <th className="px-2 py-1.5">{t("programWizard.col.code")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.name")}</th>
                <th className="px-2 py-1.5" title={t("programWizard.col.tHint")}>T</th>
                <th className="px-2 py-1.5" title={t("programWizard.col.uHint")}>U</th>
                <th className="px-2 py-1.5" title={t("programWizard.col.lHint")}>L</th>
                <th className="px-2 py-1.5">{t("programWizard.col.ects")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.year")}</th>
                <th className="px-2 py-1.5">{t("programWizard.col.mode")}</th>
                <th className="px-2 py-1.5"><span className="sr-only">{t("common.actions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {d.courses.map((c) => {
                const p = `courses.${c.key}`;
                return (
                  <tr key={c.key} className="border-t border-hairline align-top" data-testid="course-row">
                    <td className="px-2 py-1">
                      <Input value={c.code} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, code: e.target.value }))} onBlur={() => blurCode(c)} className="w-28" aria-label={t("programWizard.col.code")} data-path={`${p}.code`} aria-invalid={hasError(issues, `${p}.code`) || undefined} aria-describedby={`e-${c.key}-code`} />
                      {codeFix[c.key] ? <span className="block type-caption text-label-2">ⓘ {codeFix[c.key]}</span> : null}
                      <FieldMsg issues={issues} path={`${p}.code`} id={`e-${c.key}-code`} />
                    </td>
                    <td className="px-2 py-1"><Input value={c.name} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, name: e.target.value }))} aria-label={t("programWizard.col.name")} data-path={`${p}.name`} /></td>
                    {(["t", "u", "l", "ects"] as const).map((k) => (
                      <td key={k} className="px-2 py-1"><Input inputMode="decimal" className="w-14" value={num(c[k])} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, [k]: parseNumber(e.target.value) }))} aria-label={k.toUpperCase()} data-path={k === "t" ? `${p}.t` : undefined} /></td>
                    ))}
                    <td className="px-2 py-1"><Input inputMode="numeric" className="w-12" value={String(c.year)} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, year: Math.max(1, Number(e.target.value) || 1) }))} aria-label={t("programWizard.col.year")} /></td>
                    <td className="px-2 py-1">
                      <NativeSelect value={c.mode} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, mode: e.target.value as CourseDraft["mode"] }))} aria-label={t("programWizard.col.mode")}>
                        {MODES.map((m) => <option key={m} value={m}>{t(`programWizard.mode.${m}`)}</option>)}
                      </NativeSelect>
                    </td>
                    <td className="px-2 py-1"><Button variant="ghost" size="icon-sm" aria-label={t("programWizard.courses.remove", { code: c.code || "—" })} onClick={() => update((x) => ({ ...x, courses: x.courses.filter((y) => y.key !== c.key) }))}><Trash2 aria-hidden /></Button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="type-callout text-label-2">{t("programWizard.courses.empty")}</p>
      )}
      <p className="type-footnote text-label-2">{t("programWizard.courses.saveNote")}</p>
      <PasteDialog open={paste} onOpenChange={setPaste} onInsert={(rows) => update((x) => ({ ...x, courses: [...x.courses, ...rows] }))} />
    </div>
  );
}

/* ------------------------------------------------------------------ 4 sections + instructors */

function InstructorPicker({ value, onChange, label, testId }: { value: InstructorRef | null; onChange: (v: InstructorRef | null) => void; label: string; testId?: string }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const found = useQuery({ queryKey: ["wizard", "instructors", q], queryFn: () => catalogApi.instructors(q), enabled: open && q.trim().length >= 2, staleTime: 30_000 });
  if (value) {
    return (
      <span className="inline-flex items-center gap-1 type-footnote">
        <span className="truncate">{[value.title, value.name].filter(Boolean).join(" ")}{value.id === null ? ` · ${t("programWizard.sections.newPerson")}` : ""}</span>
        <Button variant="ghost" size="icon-xs" aria-label={t("programWizard.sections.clear", { label })} onClick={() => onChange(null)}><Minus aria-hidden /></Button>
      </span>
    );
  }
  return (
    <div className="relative">
      <Input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} placeholder={t("programWizard.sections.searchPerson")} aria-label={label} className="w-56" data-testid={testId} />
      {open && q.trim().length >= 2 ? (
        <ul role="listbox" aria-label={label} className="absolute z-20 mt-1 flex max-h-56 w-72 flex-col overflow-auto rounded-lg border border-hairline bg-(--mat-thick-solid) p-1">
          {(found.data?.items ?? []).map((i) => (
            <li key={i.id} role="option" aria-selected={false}>
              <Button variant="ghost" size="sm" className="w-full justify-start" onMouseDown={(e) => e.preventDefault()} onClick={() => { onChange({ id: i.id, name: i.full_name, title: i.title }); setQ(""); }}>
                {[i.title, i.full_name].filter(Boolean).join(" ")}
              </Button>
            </li>
          ))}
          <li role="option" aria-selected={false}>
            <Button variant="ghost" size="sm" className="w-full justify-start" onMouseDown={(e) => e.preventDefault()} onClick={() => { onChange({ id: null, name: q.trim() }); setQ(""); }} data-testid="wizard-new-person">
              <UserPlus aria-hidden />{t("programWizard.sections.create", { name: q.trim() })}
            </Button>
          </li>
        </ul>
      ) : null}
    </div>
  );
}

export function SectionsStep({ d, update, issues }: { d: Draft; update: Update; issues: readonly Issue[] }) {
  const { t } = useI18n();
  if (!d.courses.length) return <p className="type-callout text-label-2">{t("programWizard.sections.noCourses")}</p>;
  return (
    <div className="flex flex-col gap-4">
      {d.courses.map((c) => (
        <section key={c.key} aria-labelledby={`sec-${c.key}`} className="flex flex-col gap-2 border-b border-hairline pb-3" data-testid="sections-course">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={`sec-${c.key}`} className="type-headline">{c.code} {c.name}</h3>
            <span className="type-footnote text-label-2">{t("programWizard.sections.count", { n: c.sections.length })}</span>
            <Button variant="ghost" size="icon-xs" aria-label={t("programWizard.sections.less", { code: c.code })} disabled={c.sections.length <= 1} onClick={() => patchCourse(update, c.key, (x) => ({ ...x, sections: x.sections.slice(0, -1) }))}><Minus aria-hidden /></Button>
            <Button variant="ghost" size="icon-xs" aria-label={t("programWizard.sections.more", { code: c.code })} onClick={() => patchCourse(update, c.key, (x) => ({ ...x, sections: [...x.sections, newSection(String(x.sections.length + 1), x.sections[0]?.enrolment ?? null)] }))}><Plus aria-hidden /></Button>
          </div>
          {c.sections.map((s) => {
            const p = `courses.${c.key}.${s.key}`;
            return (
              <div key={s.key} className="flex flex-wrap items-start gap-3 pl-2" data-testid="section-row">
                <span className="w-12 pt-1.5 type-footnote text-label-2">§{s.label}</span>
                <label className="flex flex-col gap-0.5">
                  <span className="type-caption text-label-2">{t("programWizard.sections.enrolment")}</span>
                  <Input inputMode="numeric" className="w-24" value={s.enrolment ?? ""} onChange={(e) => patchSection(update, c.key, s.key, (x) => ({ ...x, enrolment: e.target.value ? Math.max(0, Number(e.target.value) || 0) : null }))} data-path={`${p}.enrolment`} aria-invalid={hasError(issues, `${p}.enrolment`) || undefined} aria-describedby={`e-${s.key}-en`} data-testid="section-enrolment" />
                  <FieldMsg issues={issues} path={`${p}.enrolment`} id={`e-${s.key}-en`} />
                </label>
                {([0, 1] as const).map((slot) => (
                  <label key={slot} className="flex flex-col gap-0.5">
                    <span className="type-caption text-label-2">{t(slot === 0 ? "programWizard.sections.first" : "programWizard.sections.second")}</span>
                    <InstructorPicker value={s.instructors[slot]} label={t(slot === 0 ? "programWizard.sections.first" : "programWizard.sections.second")} testId={slot === 0 ? "section-instructor" : undefined} onChange={(v) => patchSection(update, c.key, s.key, (x) => ({ ...x, instructors: (slot === 0 ? [v, x.instructors[1]] : [x.instructors[0], v]) as SectionDraft["instructors"] }))} />
                    {slot === 0 ? <FieldMsg issues={issues} path={`${p}.instructor`} id={`e-${s.key}-ins`} /> : null}
                  </label>
                ))}
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ 5 patterns + room needs */

export function PatternsStep({ d, update, issues, rooms }: { d: Draft; update: Update; issues: readonly Issue[]; rooms: readonly Room[] }) {
  const { t, locale } = useI18n();
  if (!d.courses.length) return <p className="type-callout text-label-2">{t("programWizard.sections.noCourses")}</p>;
  const startOptions = d.program.evening ? PERIODS.filter((p) => p.index >= 12) : PERIODS.filter((p) => p.index <= 12);
  return (
    <div className="flex flex-col gap-5">
      {d.courses.map((c) => {
        const p = `courses.${c.key}`;
        const hours = courseHours(c);
        const opts = patternOptions(c.t ?? 0);
        const cap = neededCapacity(c);
        const fit = fittingRooms(rooms, cap, c.room.tags, c.room.building);
        const mine = issues.filter((i) => i.path?.startsWith(p) && i.step === "patterns");
        return (
          <section key={c.key} aria-labelledby={`pat-${c.key}`} className="flex flex-col gap-2 border-b border-hairline pb-4" data-testid="pattern-course">
            <h3 id={`pat-${c.key}`} className="type-headline">{c.code} {c.name} <span className="type-footnote font-normal text-label-2">T{c.t ?? 0} U{c.u ?? 0} L{c.l ?? 0} · {t("programWizard.patterns.placed", { n: patternHours(c) })}</span></h3>
            <div className="flex flex-wrap items-end gap-4">
              {hours ? (
                opts.length > 1 ? (
                  <div className="flex flex-col gap-1">
                    <span className="type-caption text-label-2">{t("programWizard.patterns.split")}</span>
                    <SegmentedControl<string>
                      aria-label={t("programWizard.patterns.split")}
                      semantics="radiogroup"
                      size="sm"
                      value={(c.pattern.theoryBlocks.length ? c.pattern.theoryBlocks : [c.t ?? 0]).join("+")}
                      onValueChange={(v) => patchCourse(update, c.key, (x) => ({ ...x, pattern: { ...x.pattern, theoryBlocks: v.split("+").map(Number) } }))}
                      options={opts.map((o) => ({ value: o.join("+"), label: o.length === 1 ? t("programWizard.patterns.oneBlock", { n: o[0]! }) : o.join(" + ") }))}
                    />
                  </div>
                ) : null
              ) : (
                <label className="flex flex-col gap-1">
                  <span className="type-caption text-label-2">{t("programWizard.patterns.weekly")}</span>
                  <Input inputMode="numeric" className="w-20" value={c.pattern.weeklyHours ?? ""} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, pattern: { ...x.pattern, weeklyHours: e.target.value ? Math.max(0, Number(e.target.value) || 0) : null } }))} data-path={`${p}.weekly`} aria-describedby={`e-${c.key}-wk`} />
                  <FieldMsg issues={issues} path={`${p}.weekly`} id={`e-${c.key}-wk`} />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.start")}</span>
                <NativeSelect className="w-36" value={c.pattern.start} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, pattern: { ...x.pattern, start: e.target.value } }))} data-path={`${p}.start`} aria-invalid={hasError(issues, `${p}.start`) || undefined} data-testid="pattern-start">
                  <option value="">{t("programWizard.patterns.pickStart")}</option>
                  {startOptions.map((o) => <option key={o.index} value={o.start}>P{o.index} {o.start}</option>)}
                </NativeSelect>
              </label>
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.weeks")}</span>
                <Input className="w-24" value={c.pattern.weeks} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, pattern: { ...x.pattern, weeks: e.target.value } }))} />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("programWizard.patterns.days")}>
              <span className="type-caption text-label-2">{t("programWizard.patterns.days")}</span>
              {[1, 2, 3, 4, 5, 6].map((day) => (
                <Chip key={day} size="sm" selected={c.pattern.days.includes(day)} onSelectedChange={(on) => patchCourse(update, c.key, (x) => ({ ...x, pattern: { ...x.pattern, days: on ? [...x.pattern.days, day].sort() : x.pattern.days.filter((y) => y !== day) } }))}>
                  {dayName(day, locale, "short")}
                </Chip>
              ))}
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.capacity")}</span>
                <Input inputMode="numeric" className="w-24" value={c.room.capacity ?? ""} placeholder={String(cap || "")} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, room: { ...x.room, capacity: e.target.value ? Number(e.target.value) || null : null } }))} />
              </label>
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("programWizard.patterns.tags")}>
                {TAGS.map((tag) => (
                  <Chip key={tag} size="sm" selected={c.room.tags.includes(tag)} onSelectedChange={(on) => patchCourse(update, c.key, (x) => ({ ...x, room: { ...x.room, tags: on ? [...x.room.tags, tag] : x.room.tags.filter((y) => y !== tag) } }))}>
                    {t(`programWizard.tag.${tag}`)}
                  </Chip>
                ))}
              </div>
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.building")}</span>
                <NativeSelect className="w-32" value={c.room.building} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, room: { ...x.room, building: e.target.value } }))}>
                  <option value="">{t("programWizard.patterns.anyBuilding")}</option>
                  {["A", "B", "C", "D"].map((b) => <option key={b} value={b}>{b}</option>)}
                </NativeSelect>
              </label>
              <label className="flex flex-col gap-1">
                <span className="type-caption text-label-2">{t("programWizard.patterns.preferred")}</span>
                <Input className="w-28" value={c.room.preferred} onChange={(e) => patchCourse(update, c.key, (x) => ({ ...x, room: { ...x.room, preferred: e.target.value } }))} data-path={`${p}.preferred`} placeholder="A 207" />
              </label>
            </div>
            {/* live consequence line (spec §4.6) */}
            <p className="type-footnote text-label-2" data-testid="fit-line">
              {c.mode === "ONLINE" ? t("programWizard.patterns.online") : fit.length ? t("programWizard.v.fits", { n: cap, count: fit.length, rooms: fit.slice(0, 4).map((r) => `${r.display_name} (${r.capacity})`).join(", ") }) : null}
            </p>
            {mine.filter((i) => i.level !== "info").map((i, k) => (
              <p key={k} className={cn("type-footnote", i.level === "error" ? "text-status-infeasible-fg" : "text-status-warning-fg")}>{i.level === "error" ? "✕ " : "⚠ "}{issueText(t, i)}</p>
            ))}
          </section>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ 6 constraints */

export function ConstraintsStep({ d, update }: { d: Draft; update: Update }) {
  const { t } = useI18n();
  const w = d.rules.window;
  const setW = (patch: Partial<typeof w>) => update((x) => ({ ...x, rules: { ...x.rules, window: { ...x.rules.window, ...patch } } }));
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <p className="type-footnote text-label-2">{t("programWizard.constraints.intro")}</p>
      <section className="flex flex-col gap-2 rounded-xl border border-hairline p-3">
        <label className="flex items-center gap-2 type-callout font-semibold">
          <Switch checked={w.enabled} onCheckedChange={(v) => setW({ enabled: v })} data-testid="rule-window" />
          {t("programWizard.constraints.window")}
        </label>
        {w.enabled ? (
          <div className="flex flex-wrap items-center gap-3">
            <NativeSelect className="w-36" value={w.earliest} onChange={(e) => setW({ earliest: Number(e.target.value) })} aria-label={t("programWizard.constraints.from")}>
              {PERIODS.map((p) => <option key={p.index} value={p.index}>P{p.index} {p.start}</option>)}
            </NativeSelect>
            <span>–</span>
            <NativeSelect className="w-36" value={w.latest} onChange={(e) => setW({ latest: Number(e.target.value) })} aria-label={t("programWizard.constraints.to")}>
              {PERIODS.map((p) => <option key={p.index} value={p.index}>P{p.index} {p.end}</option>)}
            </NativeSelect>
            <SegmentedControl<"soft" | "hard"> aria-label={t("programWizard.constraints.hardness")} semantics="radiogroup" size="sm" value={w.hard ? "hard" : "soft"} onValueChange={(v) => setW({ hard: v === "hard" })} options={[{ value: "soft", label: t("programWizard.constraints.soft") }, { value: "hard", label: t("programWizard.constraints.hard") }]} />
          </div>
        ) : null}
      </section>
      <label className="flex items-center gap-2 rounded-xl border border-hairline p-3 type-callout font-semibold">
        <Switch checked={d.rules.sameRoom} onCheckedChange={(v) => update((x) => ({ ...x, rules: { ...x.rules, sameRoom: v } }))} />
        {t("programWizard.constraints.sameRoom")}
      </label>
      <p className="type-footnote text-label-2">{t("programWizard.constraints.studio")}</p>
    </div>
  );
}
