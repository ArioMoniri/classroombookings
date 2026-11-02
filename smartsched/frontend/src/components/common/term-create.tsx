"use client";
/**
 * "Yeni dönem oluştur…" from every term dropdown (owner report 2026-11-02, Çizelge item 4): the import wizard's
 * "Hedef dönem", Studio's scope step (Oluştur), the program wizard, Ayarlar › Takvim haftaları and the shell's term
 * switcher. One small dialog (code, name, kind Ders / Sınav, first and last day) posts `POST /terms` (the API the
 * Sessions page uses) and hands the new term back, so the dropdown selects it at once.
 *
 * Only people who may create terms see the action: the backend's `SessionsEditor` guard, `planning.edit` or
 * `setup.sessions` (app/api/v1/terms.py).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ChangeEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { DateField } from "@/components/ui/date-field";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { crbsAdmin, crbsError, weeksBetween } from "@/lib/api/crbs";
import type { Term } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";

/** the backend guard on `POST /terms` (SessionsEditor): either right is enough */
export const TERM_CREATE_PERMISSIONS = ["planning.edit", "setup.sessions"] as const;
/** the option value that opens the dialog instead of selecting a term */
export const NEW_TERM_VALUE = "__new_term__";

export type NewTermKind = "REGULAR" | "FINAL";

export function useCanCreateTerm(): boolean {
  const { can } = usePermissions();
  return can([...TERM_CREATE_PERMISSIONS]);
}

/** The created term in the shape of `GET /terms`, so a list can show it before the refetch lands. */
export function termFromCreated(out: { id: number; code: string; name: string; start_date?: string | null; end_date?: string | null }, kind: NewTermKind, start: string, end: string): Term {
  return { id: out.id, code: out.code, name: out.name, kind, start_date: out.start_date ?? start, end_date: out.end_date ?? end, week_count: weeksBetween(start, end), is_active: false };
}

export interface CreateTermDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** called with the new term after the terms list holds it */
  onCreated: (term: Term) => void;
  /** Studio's exam flow starts on Sınav */
  defaultKind?: NewTermKind;
}

export function CreateTermDialog({ open, onOpenChange, onCreated, defaultKind = "REGULAR" }: CreateTermDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md" data-testid="term-create-dialog">
        {open ? <CreateTermForm defaultKind={defaultKind} onCancel={() => onOpenChange(false)} onCreated={(term) => { onOpenChange(false); onCreated(term); }} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function CreateTermForm({ defaultKind, onCancel, onCreated }: { defaultKind: NewTermKind; onCancel: () => void; onCreated: (term: Term) => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const ids = useId();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState<NewTermKind>(defaultKind);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const badDates = !!start && !!end && end < start;
  const ready = code.trim() !== "" && !!start && !!end && !badDates;

  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const out = await crbsAdmin.terms.create({ code: code.trim(), name: name.trim() || null, kind, start_date: start, end_date: end, week_count: weeksBetween(start, end) });
      const term = termFromCreated(out, kind, start, end);
      // the dropdowns read ["terms"]: put the new one in first so the select can hold its id, then refetch
      qc.setQueryData<Term[]>(["terms"], (old) => (old ? [...old.filter((x) => x.id !== term.id), term] : old));
      void qc.invalidateQueries({ queryKey: ["terms"] });
      void qc.invalidateQueries({ queryKey: ["crbs", "sessions"] });
      toast.success(t("termCreate.created", { name: term.name }));
      onCreated(term);
    } catch (err) {
      const e = crbsError(err);
      setError(e.status === 409 ? t("termCreate.codeTaken") : e.message || t("termCreate.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <DialogHeader>
        <DialogTitle>{t("termCreate.title")}</DialogTitle>
        <DialogDescription>{t("termCreate.lead")}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={`${ids}-code`} className="type-footnote font-medium text-label-2">{t("termCreate.code")}</label>
          <Input id={`${ids}-code`} required maxLength={32} autoFocus placeholder="2027-BAHAR" value={code} onChange={(e) => setCode(e.target.value)} aria-describedby={`${ids}-code-hint`} data-testid="term-create-code" />
          <p id={`${ids}-code-hint`} className="type-footnote text-label-3">{t("termCreate.codeHint")}</p>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={`${ids}-name`} className="type-footnote font-medium text-label-2">{t("termCreate.name")}</label>
          <Input id={`${ids}-name`} maxLength={128} placeholder={code.trim() || t("termCreate.namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} aria-describedby={`${ids}-name-hint`} data-testid="term-create-name" />
          <p id={`${ids}-name-hint`} className="type-footnote text-label-3">{t("termCreate.nameHint")}</p>
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <span id={`${ids}-kind`} className="type-footnote font-medium text-label-2">{t("termCreate.kind")}</span>
        <SegmentedControl
          semantics="radiogroup"
          aria-labelledby={`${ids}-kind`}
          value={kind}
          onValueChange={(v) => setKind(v as NewTermKind)}
          data-testid="term-create-kind"
          options={[
            { value: "REGULAR", label: t("termCreate.kindCourse"), testId: "term-create-kind-REGULAR" },
            { value: "FINAL", label: t("termCreate.kindExam"), testId: "term-create-kind-FINAL" },
          ]}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={`${ids}-start`} className="type-footnote font-medium text-label-2">{t("termCreate.start")}</label>
          <DateField id={`${ids}-start`} required value={start} onChange={setStart} data-testid="term-create-start" />
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={`${ids}-end`} className="type-footnote font-medium text-label-2">{t("termCreate.end")}</label>
          <DateField id={`${ids}-end`} required min={start || undefined} value={end} onChange={setEnd} aria-describedby={badDates ? `${ids}-dates` : undefined} data-testid="term-create-end" />
        </div>
      </div>
      {badDates ? <p id={`${ids}-dates`} role="alert" className="type-footnote text-status-infeasible-fg">{t("termCreate.endBeforeStart")}</p> : null}
      {error ? <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="term-create-error">{error}</p> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>{t("termCreate.cancel")}</Button>
        <Button type="submit" disabled={!ready || busy} aria-busy={busy || undefined} data-testid="term-create-save">
          <BusyLabel busy={busy} label={t("busy.saving")}>{t("termCreate.create")}</BusyLabel>
        </Button>
      </DialogFooter>
    </form>
  );
}

export interface TermSelectProps {
  terms: readonly Term[];
  value: number | string | null | undefined;
  onChange: (termId: number) => void;
  id?: string;
  className?: string;
  selectClassName?: string;
  disabled?: boolean;
  "aria-label"?: string;
  "data-testid"?: string;
  /** the option text (default: the term's name) */
  optionLabel?: (term: Term) => string;
  /** the dialog's starting kind (Studio's exam flow: FINAL) */
  defaultKind?: NewTermKind;
  /** hide the create action even for people allowed to create terms */
  noCreate?: boolean;
}

/**
 * A term `<select>` (NativeSelect: the OS picker on touch, full keyboard) whose last option, for people who may create
 * terms, is "Yeni dönem oluştur…": choosing it opens the dialog and keeps the current term until one is created.
 */
export function TermSelect({ terms, value, onChange, id, className, selectClassName, disabled, optionLabel, defaultKind, noCreate, "aria-label": ariaLabel, "data-testid": testId }: TermSelectProps) {
  const { t } = useI18n();
  const canCreate = useCanCreateTerm() && !noCreate;
  const [open, setOpen] = useState(false);
  const current = value === null || value === undefined ? "" : String(value);
  const known = terms.some((x) => String(x.id) === current);
  const onSelect = (e: ChangeEvent<HTMLSelectElement>) => {
    if (e.target.value === NEW_TERM_VALUE) {
      setOpen(true);
      return;
    }
    const n = Number(e.target.value);
    if (Number.isFinite(n)) onChange(n);
  };
  return (
    <>
      <NativeSelect id={id} className={className} selectClassName={selectClassName} disabled={disabled} aria-label={ariaLabel} value={current} onChange={onSelect} data-testid={testId}>
        {/* a value the list does not hold (empty, or the terms still loading): a placeholder, so the select never shows
            the create action as the chosen term */}
        {!known ? <option value={current} disabled hidden>{t("termCreate.pick")}</option> : null}
        {terms.map((x) => (
          <option key={x.id} value={x.id}>{optionLabel ? optionLabel(x) : x.name}</option>
        ))}
        {canCreate ? <option value={NEW_TERM_VALUE} data-testid="term-create-option">{t("termCreate.action")}</option> : null}
      </NativeSelect>
      {canCreate ? <CreateTermDialog open={open} onOpenChange={setOpen} defaultKind={defaultKind} onCreated={(term) => onChange(term.id)} /> : null}
    </>
  );
}
