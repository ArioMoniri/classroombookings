"use client";
/**
 * RF-05: the edit sheet's forms, one per catalogue list. Each shows the few fields people change (name, code,
 * class size) and keeps the rest behind "Gelişmiş"; "Son değişiklik" and a delete with its consequences come from
 * `GET /catalog/usage/{entity}/{id}`. Saves send only the changed fields (the backend audits every write).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { BusyLabel } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { catalogAdminApi, catalogApi, type CatalogEntity, type CatalogUsage, type Course, type CourseBody, type Faculty, type Instructor, type ProgramRow, type SectionRow } from "@/lib/api/catalog-admin";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Field, SelectField } from "../kit";
import { CATALOG_TABS, MODES, catalogErrorText, changedFields, deleteMode, lastChangeText, numText, parseDecimal, parseWhole, usageLines, type CatalogTab } from "./catalog-model";

export type CatalogRow = Instructor | Course | ProgramRow | Faculty | SectionRow;

export function rowTitle(tab: CatalogTab, row: CatalogRow): string {
  switch (tab) {
    case "instructors":
      return (row as Instructor).full_name;
    case "courses": {
      const c = row as Course;
      return c.name ? `${c.display_code} ${c.name}` : c.display_code;
    }
    case "sections": {
      const s = row as SectionRow;
      return `${s.course_code ?? ""}${s.label ? ` §${s.label}` : ""}`.trim();
    }
    default:
      return (row as ProgramRow | Faculty).name;
  }
}

interface FormProps<R> {
  row: R | null;
  canEdit: boolean;
  onDone: (outcome: "saved" | "deleted" | "cancel") => void;
}

/** Dispatches to the form of the list. */
export function CatalogForm({ tab, row, canEdit, onDone }: { tab: CatalogTab } & FormProps<CatalogRow>) {
  switch (tab) {
    case "instructors":
      return <InstructorForm row={row as Instructor | null} canEdit={canEdit} onDone={onDone} />;
    case "courses":
      return <CourseForm row={row as Course | null} canEdit={canEdit} onDone={onDone} />;
    case "programs":
      return <ProgramForm row={row as ProgramRow | null} canEdit={canEdit} onDone={onDone} />;
    case "faculties":
      return <FacultyForm row={row as Faculty | null} canEdit={canEdit} onDone={onDone} />;
    case "sections":
      return row ? <SectionForm row={row as SectionRow} canEdit={canEdit} onDone={onDone} /> : null;
  }
}

/* ------------------------------------------------------------------------------------------- the shell */

function useSave(onDone: FormProps<unknown>["onDone"], name: () => string, isNew: boolean) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["catalog"] });
      toast.success(t(isNew ? "catalog.created" : "catalog.saved", { name: name() }));
      onDone("saved");
    },
    onError: (e) => setError(catalogErrorText(e, t, locale)),
  });
  return { m, error, setError };
}

function FormShell({
  tab,
  entity,
  row,
  title,
  canEdit,
  busy,
  error,
  dirty,
  onSubmit,
  onDone,
  advanced,
  children,
}: {
  tab: CatalogTab;
  entity: CatalogEntity;
  row: { id: number } | null;
  title: string;
  canEdit: boolean;
  busy: boolean;
  error: string | null;
  dirty: boolean;
  onSubmit: () => void;
  onDone: FormProps<unknown>["onDone"];
  advanced?: ReactNode;
  children: ReactNode;
}) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const advId = useId();
  const usage = useQuery({ queryKey: ["catalog", "usage", entity, row?.id], queryFn: () => catalogAdminApi.usage(entity, row?.id ?? 0), enabled: !!row, retry: false });
  const conf = CATALOG_TABS.find((x) => x.id === tab);
  return (
    <form
      className="flex min-h-0 flex-1 flex-col"
      data-testid="catalog-form"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <SheetHeader className="pr-12">
        <SheetTitle>{title}</SheetTitle>
        <SheetDescription data-testid="catalog-last-change">
          {row ? (usage.data ? lastChangeText(usage.data.last_change, t, locale) : usage.isError ? "" : t("crbs.common.loading")) : conf ? t(conf.labelKey) : ""}
        </SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-4">
        {!canEdit ? <Alert tone="info">{t("catalog.readOnly")}</Alert> : null}
        <fieldset disabled={!canEdit} className="flex flex-col gap-4">
          {children}
          {advanced ? (
            <div className="flex flex-col gap-3">
              <Button type="button" variant="ghost" className="self-start pointer-coarse:h-11" aria-expanded={open} aria-controls={advId} onClick={() => setOpen((o) => !o)} data-testid="catalog-advanced">
                <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", open && "rotate-180")} />
                {t("catalog.advanced")}
              </Button>
              <div id={advId} hidden={!open} className="flex flex-col gap-4">
                {advanced}
              </div>
            </div>
          ) : null}
        </fieldset>
        {error ? (
          <Alert tone="error" testId="catalog-error">
            {error}
          </Alert>
        ) : null}
      </div>
      <SheetFooter className="mt-auto flex-row flex-wrap items-center justify-end gap-2">
        {row && canEdit ? (
          <Button type="button" variant="ghost" className="mr-auto text-status-infeasible-fg pointer-coarse:h-11" onClick={() => setConfirm(true)} disabled={!usage.data} data-testid="catalog-delete">
            {usage.data?.action === "archive" ? t("catalog.archive") : t("catalog.delete")}
          </Button>
        ) : null}
        <Button type="button" variant="ghost" className="pointer-coarse:h-11" onClick={() => onDone("cancel")}>
          {canEdit ? t("catalog.cancel") : t("catalog.close")}
        </Button>
        {canEdit ? (
          <Button type="submit" className="pointer-coarse:h-11" disabled={busy || (!!row && !dirty)} aria-busy={busy || undefined} data-testid="catalog-save">
            <BusyLabel busy={busy} label={t("busy.working")}>
              {t("catalog.save")}
            </BusyLabel>
          </Button>
        ) : null}
      </SheetFooter>
      {row && usage.data ? <DeleteDialog open={confirm} onOpenChange={setConfirm} entity={entity} id={row.id} title={title} usage={usage.data} onDeleted={() => onDone("deleted")} /> : null}
    </form>
  );
}

function DeleteDialog({
  open,
  onOpenChange,
  entity,
  id,
  title,
  usage,
  onDeleted,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  entity: CatalogEntity;
  id: number;
  title: string;
  usage: CatalogUsage;
  onDeleted: () => void;
}) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const mode = deleteMode(usage);
  const lines = usageLines(usage, t);
  const [error, setError] = useState<string | null>(null);
  const del = useMutation({
    mutationFn: () => {
      switch (entity) {
        case "instructor":
          return catalogAdminApi.deleteInstructor(id);
        case "course":
          return catalogAdminApi.deleteCourse(id);
        case "faculty":
          return catalogAdminApi.deleteFaculty(id);
        case "program":
          return catalogAdminApi.deleteProgram(id);
        case "section":
          return catalogAdminApi.archiveSection(id);
      }
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["catalog"] });
      toast.success(t(mode === "archive" ? "catalog.archived" : "catalog.deleted", { name: title }));
      onOpenChange(false);
      onDeleted();
    },
    onError: (e) => setError(catalogErrorText(e, t, locale)),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent role="alertdialog" className="sm:max-w-md" data-testid="catalog-delete-dialog">
        <DialogHeader>
          <DialogTitle>{mode === "blocked" ? t("catalog.blockedTitle", { name: title }) : t(mode === "archive" ? "catalog.archiveTitle" : "catalog.deleteTitle", { name: title })}</DialogTitle>
          <DialogDescription>{mode === "blocked" ? t("catalog.blockedBody") : mode === "archive" ? t("catalog.archiveBody") : t("catalog.deleteFree")}</DialogDescription>
        </DialogHeader>
        {lines.length ? (
          <ul className="flex list-disc flex-col gap-1 pl-5 type-callout text-label-1" data-testid="catalog-delete-uses">
            {lines.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <DialogFooter>
          <Button variant="ghost" className="pointer-coarse:h-11" onClick={() => onOpenChange(false)}>
            {mode === "blocked" ? t("catalog.close") : t("catalog.cancel")}
          </Button>
          {mode !== "blocked" ? (
            <Button variant="destructive" className="pointer-coarse:h-11" onClick={() => del.mutate()} disabled={del.isPending} aria-busy={del.isPending || undefined} data-testid="catalog-delete-confirm">
              <BusyLabel busy={del.isPending} label={t("busy.working")}>
                {mode === "archive" ? t("catalog.archive") : t("catalog.delete")}
              </BusyLabel>
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------------------------------- forms */

function InstructorForm({ row, canEdit, onDone }: FormProps<Instructor>) {
  const { t } = useI18n();
  const init = { full_name: row?.full_name ?? "", title: row?.title ?? "", email: row?.email ?? "" };
  const [v, setV] = useState(init);
  const id = useId();
  const { m, error, setError } = useSave(onDone, () => v.full_name.trim(), !row);
  const body = { full_name: v.full_name.trim(), title: v.title.trim() || null, email: v.email.trim() || null };
  const diff = changedFields({ full_name: init.full_name, title: init.title || null, email: init.email || null }, body);
  return (
    <FormShell
      tab="instructors"
      entity="instructor"
      row={row}
      title={row ? row.full_name : t("catalog.newNamed.instructors")}
      canEdit={canEdit}
      busy={m.isPending}
      error={error}
      dirty={Object.keys(diff).length > 0}
      onDone={onDone}
      onSubmit={() => {
        if (!body.full_name) return setError(t("catalog.error.required"));
        m.mutate(() => (row ? catalogAdminApi.updateInstructor(row.id, diff) : catalogApi.createInstructor(body)));
      }}
      advanced={
        <Field label={t("catalog.field.email")} htmlFor={`${id}-email`}>
          <Input id={`${id}-email`} type="email" inputMode="email" autoCapitalize="none" spellCheck={false} value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        </Field>
      }
    >
      <Field label={t("catalog.field.fullName")} htmlFor={`${id}-name`}>
        <Input id={`${id}-name`} required maxLength={255} value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} data-testid="catalog-field-name" />
      </Field>
      <Field label={t("catalog.field.title")} htmlFor={`${id}-title`} hint={t("catalog.field.titleHint")}>
        <Input id={`${id}-title`} maxLength={64} value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />
      </Field>
    </FormShell>
  );
}

function CourseForm({ row, canEdit, onDone }: FormProps<Course>) {
  const { t, locale } = useI18n();
  const init = {
    code: row?.display_code ?? "",
    name: row?.name ?? "",
    t_hours: numText(row?.t_hours, locale),
    u_hours: numText(row?.u_hours, locale),
    l_hours: numText(row?.l_hours, locale),
    credits: numText(row?.credits, locale),
    ects: numText(row?.ects, locale),
  };
  const [v, setV] = useState(init);
  const id = useId();
  const { m, error, setError } = useSave(onDone, () => v.code.trim(), !row);
  const diff = changedFields(init, v);
  const num = (k: "t_hours" | "u_hours" | "l_hours" | "credits" | "ects", label: string) => (
    <Field label={label} htmlFor={`${id}-${k}`}>
      <Input id={`${id}-${k}`} inputMode={k === "credits" || k === "ects" ? "decimal" : "numeric"} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} />
    </Field>
  );
  return (
    <FormShell
      tab="courses"
      entity="course"
      row={row}
      title={row ? rowTitle("courses", row) : t("catalog.newNamed.courses")}
      canEdit={canEdit}
      busy={m.isPending}
      error={error}
      dirty={Object.keys(diff).length > 0}
      onDone={onDone}
      onSubmit={() => {
        if (!v.code.trim()) return setError(t("catalog.error.required"));
        const body: Record<string, unknown> = {};
        for (const [k, raw] of Object.entries(row ? diff : v) as [keyof typeof v, string][]) {
          if (k === "code") body.code = raw.trim();
          else if (k === "name") body.name = raw.trim() || null;
          else if (k === "credits" || k === "ects") {
            const n = parseDecimal(raw);
            if (n === "invalid") return setError(t("catalog.error.decimal"));
            body[k] = n;
          } else {
            const n = parseWhole(raw, 40);
            if (n === "invalid") return setError(t("catalog.error.hours"));
            body[k] = n;
          }
        }
        m.mutate(() => (row ? catalogApi.updateCourse(row.id, body as Partial<CourseBody>) : catalogApi.createCourse(body as unknown as CourseBody)));
      }}
      advanced={
        <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
          {num("t_hours", t("catalog.field.t"))}
          {num("u_hours", t("catalog.field.u"))}
          {num("l_hours", t("catalog.field.l"))}
          {num("credits", t("catalog.field.credits"))}
          {num("ects", t("catalog.field.ects"))}
        </div>
      }
    >
      <Field label={t("catalog.field.code")} htmlFor={`${id}-code`} hint={t("catalog.field.codeHint")}>
        <Input id={`${id}-code`} required maxLength={32} autoCapitalize="characters" spellCheck={false} value={v.code} onChange={(e) => setV({ ...v, code: e.target.value })} data-testid="catalog-field-code" />
      </Field>
      <Field label={t("catalog.field.name")} htmlFor={`${id}-name`}>
        <Input id={`${id}-name`} maxLength={255} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} data-testid="catalog-field-name" />
      </Field>
    </FormShell>
  );
}

function useFacultyOptions(enabled = true) {
  return useQuery({ queryKey: ["catalog", "faculty-options"], queryFn: () => catalogAdminApi.facultiesPage({ limit: 500 }), enabled, staleTime: 60_000 });
}

function ProgramForm({ row, canEdit, onDone }: FormProps<ProgramRow>) {
  const { t } = useI18n();
  const faculties = useFacultyOptions();
  const init = { name: row?.name ?? "", faculty_id: row?.faculty_id ?? null, is_evening: row?.is_evening ?? false };
  const [v, setV] = useState(init);
  const id = useId();
  const { m, error, setError } = useSave(onDone, () => v.name.trim(), !row);
  const body = { ...v, name: v.name.trim() };
  const diff = changedFields(init, body);
  return (
    <FormShell
      tab="programs"
      entity="program"
      row={row}
      title={row ? row.name : t("catalog.newNamed.programs")}
      canEdit={canEdit}
      busy={m.isPending}
      error={error}
      dirty={Object.keys(diff).length > 0}
      onDone={onDone}
      onSubmit={() => {
        if (!body.name) return setError(t("catalog.error.required"));
        m.mutate(() => (row ? catalogApi.updateProgram(row.id, diff) : catalogApi.createProgram(body)));
      }}
      advanced={
        <div className="flex items-center justify-between gap-3">
          <label htmlFor={`${id}-evening`} className="type-callout text-label-1">
            {t("catalog.field.evening")}
          </label>
          <Switch id={`${id}-evening`} checked={v.is_evening} onCheckedChange={(c) => setV({ ...v, is_evening: !!c })} />
        </div>
      }
    >
      <Field label={t("catalog.field.programName")} htmlFor={`${id}-name`}>
        <Input id={`${id}-name`} required maxLength={255} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} data-testid="catalog-field-name" />
      </Field>
      <Field label={t("catalog.field.faculty")} htmlFor={`${id}-faculty`}>
        <SelectField id={`${id}-faculty`} value={v.faculty_id === null ? "" : String(v.faculty_id)} onChange={(e) => setV({ ...v, faculty_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">{t("catalog.field.noFaculty")}</option>
          {(faculties.data?.items ?? []).map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </SelectField>
      </Field>
    </FormShell>
  );
}

function FacultyForm({ row, canEdit, onDone }: FormProps<Faculty>) {
  const { t } = useI18n();
  const [name, setName] = useState(row?.name ?? "");
  const id = useId();
  const { m, error, setError } = useSave(onDone, () => name.trim(), !row);
  return (
    <FormShell
      tab="faculties"
      entity="faculty"
      row={row}
      title={row ? row.name : t("catalog.newNamed.faculties")}
      canEdit={canEdit}
      busy={m.isPending}
      error={error}
      dirty={name.trim() !== (row?.name ?? "")}
      onDone={onDone}
      onSubmit={() => {
        if (!name.trim()) return setError(t("catalog.error.required"));
        m.mutate(() => (row ? catalogAdminApi.updateFaculty(row.id, name.trim()) : catalogApi.createFaculty(name.trim())));
      }}
    >
      <Field label={t("catalog.field.facultyName")} htmlFor={`${id}-name`}>
        <Input id={`${id}-name`} required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} data-testid="catalog-field-name" />
      </Field>
    </FormShell>
  );
}

function SectionForm({ row, canEdit, onDone }: FormProps<SectionRow> & { row: SectionRow }) {
  const { t } = useI18n();
  const detail = useQuery({ queryKey: ["catalog", "section", row.id], queryFn: () => catalogApi.section(row.id), retry: false });
  const programs = useQuery({ queryKey: ["catalog", "program-options"], queryFn: () => catalogAdminApi.programsPage({ limit: 500 }), staleTime: 60_000 });
  const init = { enrolment: row.enrolment === null ? "" : String(row.enrolment), label: row.label ?? "", program_id: row.program_id, mode: row.mode, notes: row.notes ?? "" };
  const [v, setV] = useState(init);
  const id = useId();
  const { m, error, setError } = useSave(onDone, () => rowTitle("sections", row), false);
  const diff = changedFields(init, v);
  const people = detail.data?.instructors ?? [];
  return (
    <FormShell
      tab="sections"
      entity="section"
      row={row}
      title={rowTitle("sections", row)}
      canEdit={canEdit}
      busy={m.isPending}
      error={error}
      dirty={Object.keys(diff).length > 0}
      onDone={onDone}
      onSubmit={() => {
        const body: Record<string, unknown> = {};
        if ("enrolment" in diff) {
          const n = parseWhole(v.enrolment, 2000);
          if (n === "invalid") return setError(t("catalog.error.students"));
          body.enrolment = n;
        }
        if ("label" in diff) body.label = v.label.trim() || null;
        if ("program_id" in diff) body.program_id = v.program_id;
        if ("mode" in diff) body.mode = v.mode;
        if ("notes" in diff) body.notes = v.notes.trim() || null;
        m.mutate(() => catalogAdminApi.updateSection(row.id, body));
      }}
      advanced={
        <>
          <Field label={t("catalog.field.mode")} htmlFor={`${id}-mode`}>
            <SelectField id={`${id}-mode`} value={v.mode} onChange={(e) => setV({ ...v, mode: e.target.value })}>
              {MODES.map((mo) => (
                <option key={mo} value={mo}>
                  {t(`catalog.mode.${mo}`)}
                </option>
              ))}
            </SelectField>
          </Field>
          <Field label={t("catalog.field.notes")} htmlFor={`${id}-notes`}>
            <Textarea id={`${id}-notes`} maxLength={4000} value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />
          </Field>
        </>
      }
    >
      <p className="type-callout text-label-2">{row.course_name}</p>
      <Field label={t("catalog.field.students")} htmlFor={`${id}-students`} hint={t("catalog.field.studentsHint")}>
        <Input id={`${id}-students`} inputMode="numeric" value={v.enrolment} onChange={(e) => setV({ ...v, enrolment: e.target.value })} data-testid="catalog-field-students" />
      </Field>
      <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
        <Field label={t("catalog.field.label")} htmlFor={`${id}-label`}>
          <Input id={`${id}-label`} maxLength={64} value={v.label} onChange={(e) => setV({ ...v, label: e.target.value })} />
        </Field>
        <Field label={t("catalog.field.program")} htmlFor={`${id}-program`}>
          <SelectField id={`${id}-program`} value={v.program_id === null ? "" : String(v.program_id)} onChange={(e) => setV({ ...v, program_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">{t("catalog.field.noProgram")}</option>
            {(programs.data?.items ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
            {row.program_id !== null && !(programs.data?.items ?? []).some((p) => p.id === row.program_id) ? <option value={row.program_id}>{row.program_name ?? row.program_id}</option> : null}
          </SelectField>
        </Field>
      </div>
      <div>
        <p className="type-footnote font-medium text-label-2">{t("catalog.field.instructors")}</p>
        <p className="type-callout text-label-1" data-testid="catalog-section-instructors">
          {detail.isSuccess ? (people.length ? people.map((p) => [p.title, p.full_name].filter(Boolean).join(" ")).join(", ") : t("catalog.field.noInstructors")) : "…"}
        </p>
      </div>
    </FormShell>
  );
}

/** The sections list's lead: the term and where new sections come from. */
export function SectionsLead({ term }: { term: string }) {
  const { t } = useI18n();
  return (
    <p className="type-callout text-label-2">
      {t("catalog.sectionsLead", { term })}{" "}
      <Link href="/programs/new" className="inline-flex min-h-11 items-center font-medium text-tint-text underline-offset-2 hover:underline sm:min-h-0">
        {t("catalog.wizardLink")}
      </Link>
    </p>
  );
}
