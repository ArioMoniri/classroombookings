"use client";
/**
 * HX-10 admin side (ROADMAP HX-10; backend HB-10 / HB-11): Yönetim › Yapay zekâ › Limitler › **Fakülteler**.
 *
 * One row per faculty with its monthly allowance (tokens; empty = the faculty draws from the org budget). "Bölümler
 * ve yöneticiler" opens this month's use in words (`GET /ai/faculty/usage?faculty_id=`), the department split
 * (checked against the allowance before saving), the quota managers (`ai.usage_faculty` holders who see and split the
 * faculty) and whether they see per-person token totals. The cost cap per faculty sits in the same details; strict
 * mode is behind "Gelişmiş". One primary action: "Fakülte paylarını kaydet" → `PUT /ai/admin/limits` with
 * `faculties`, `departments` and `strict`. A 422 (`department_sum_exceeds_faculty`, `unknown_unit`, strict
 * `faculty_sum_exceeds_org`) is shown inline on the faculty it names; the non-strict overbooking note as a warning.
 */
import { useQuery } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert, Field } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { type FacultyCap, type Limits, type LimitsIn, type UnitCap, useSaveLimits } from "@/lib/api/ai-admin";
import { catalogApi } from "@/lib/api/catalog-admin";
import { refusalBody } from "@/lib/api/error-text";
import { useFacultyUsage } from "@/lib/api/helper";
import { useDirtyCapsule } from "@/components/settings/dirty-capsule";
import { useI18n } from "@/lib/i18n/provider";

interface FacultyDraft {
  tokens: string;
  cost: string;
  managers: string;
  showPeople: boolean;
}

const draftOf = (f: FacultyCap | undefined): FacultyDraft => ({
  tokens: f?.monthly_tokens ? String(f.monthly_tokens) : "",
  cost: f?.monthly_cost_usd ? String(f.monthly_cost_usd) : "",
  managers: (f?.managers ?? []).join(", "),
  showPeople: !!f?.show_people,
});

/** "" → 0; a whole number ≥ 0 → it; anything else → null (invalid). */
export function wholeOrZero(v: string): number | null {
  const s = v.trim().replace(/[.\s]/g, "");
  if (!s) return 0;
  return /^\d+$/.test(s) ? Number(s) : null;
}

function costOf(v: string): number | null {
  const s = v.trim().replace(",", ".");
  if (!s) return 0;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function managersOf(v: string): number[] | null {
  const parts = v.split(/[,\s]+/).filter(Boolean);
  if (parts.some((p) => !/^\d+$/.test(p) || Number(p) <= 0)) return null;
  return [...new Set(parts.map(Number))];
}

/** The `PUT /ai/admin/limits` body of the editor (null when a field is invalid). Departments not shown are kept. */
export function facultyBody(facultyIds: number[], drafts: Record<string, FacultyDraft>, deps: Record<string, string>, stored: Record<string, UnitCap>, strict: boolean): LimitsIn | null {
  const faculties: Record<string, FacultyCap> = {};
  for (const id of facultyIds.map(String)) {
    const d = drafts[id];
    if (!d) continue;
    const tokens = wholeOrZero(d.tokens);
    const cost = costOf(d.cost);
    const managers = managersOf(d.managers);
    if (tokens === null || cost === null || managers === null) return null;
    if (tokens || cost || managers.length || d.showPeople) faculties[id] = { monthly_tokens: tokens, monthly_cost_usd: cost, managers, show_people: d.showPeople };
  }
  const departments: Record<string, UnitCap> = {};
  for (const [id, v] of Object.entries(deps)) {
    const tokens = wholeOrZero(v);
    if (tokens === null) return null;
    const cost = stored[id]?.monthly_cost_usd ?? 0;
    if (tokens || cost) departments[id] = { monthly_tokens: tokens, monthly_cost_usd: cost };
  }
  return { faculties, departments, strict };
}

/** The department split's total and whether it is over the faculty's allowance (`null` = no allowance). */
export function splitCheck(split: Record<string, number>, allowance: number | null): { sum: number; over: boolean } {
  const sum = Object.values(split).reduce((a, v) => a + v, 0);
  return { sum, over: allowance !== null && sum > allowance };
}

/** The faculty a 422 names (`field: "faculties.3"`), or null. */
/** E2EB-F05: the client keeps FastAPI's wrapper (`{detail: {code, message_tr, field}}`); read the inner body. */
const errorBody = (err: unknown): Record<string, unknown> => refusalBody(err) ?? {};

function facultyOfField(err: unknown): string | null {
  const d = errorBody(err);
  const m = typeof d.field === "string" ? /^faculties\.(\d+)$/.exec(d.field) : null;
  return m ? m[1]! : null;
}

function serverText(err: unknown, locale: string, fallback: string): string {
  const d = errorBody(err);
  const text = locale === "en" ? d.message_en : d.message_tr;
  return typeof text === "string" && text ? text : fallback;
}

function Departments({ facultyId, allowance, deps, setDep, onOver, canEdit }: { facultyId: number; allowance: number; deps: Record<string, string>; setDep: (id: string, v: string) => void; onOver: (facultyId: number, over: boolean) => void; canEdit: boolean }) {
  const { t, n } = useI18n();
  const q = useFacultyUsage(facultyId);
  const rows = q.data?.by_department ?? [];
  const split = Object.fromEntries(rows.map((d) => [String(d.id), wholeOrZero(deps[String(d.id)] ?? "") ?? 0]));
  const { sum, over } = splitCheck(split, allowance > 0 ? allowance : null);
  // the parent's save button reads it; closing the details clears it
  useEffect(() => {
    onOver(facultyId, over);
  }, [over, onOver, facultyId]);
  useEffect(() => () => onOver(facultyId, false), [onOver, facultyId]);
  if (q.isLoading) return <Skeleton className="h-16 w-full" />;
  if (!q.data) return <p className="type-callout text-label-2">{t("helper.facultyLimits.usageError")}</p>;
  return (
    <div className="flex flex-col gap-2">
      <p className="type-callout text-label-1">{t("helper.facultyLimits.used", { tokens: n(q.data.totals.tokens) })}</p>
      <h4 className="type-callout font-semibold text-label-1">{t("helper.facultyLimits.departments")}</h4>
      {rows.length ? (
        <>
          <p className="type-footnote text-label-2">{t("helper.facultyLimits.deptHint")}</p>
          <ul className="flex flex-col gap-2">
            {rows.map((d) => (
              <li key={d.id} className="grid items-center gap-1.5 sm:grid-cols-[1fr_12rem]">
                <Label htmlFor={`fl-${facultyId}-d${d.id}`} className="flex flex-col items-start">
                  <span>{d.name}</span>
                  <span className="type-footnote font-normal text-label-2">{t("helper.facultyLimits.deptRow", { tokens: n(d.tokens) })}</span>
                </Label>
                <Input
                  id={`fl-${facultyId}-d${d.id}`}
                  inputMode="numeric"
                  aria-label={t("helper.facultyLimits.deptFor", { department: d.name })}
                  value={deps[String(d.id)] ?? ""}
                  disabled={!canEdit}
                  onChange={(e) => setDep(String(d.id), e.target.value)}
                  className="text-base pointer-fine:sm:type-callout"
                />
              </li>
            ))}
          </ul>
          {allowance > 0 ? (
            <p className={over ? "type-callout text-status-infeasible-fg" : "type-callout text-label-2"} role={over ? "alert" : undefined} data-testid={`faculty-limit-sum-${facultyId}`} data-over={over || undefined}>
              {over ? t("helper.facultyLimits.over") : t("helper.facultyLimits.sum", { sum: n(sum), max: n(allowance) })}
            </p>
          ) : null}
        </>
      ) : (
        <p className="type-callout text-label-2">{t("helper.facultyLimits.noDepartments")}</p>
      )}
    </div>
  );
}

export function FacultyLimits({ data, canEdit }: { data: Limits; canEdit: boolean }) {
  const { t, locale, n } = useI18n();
  const uid = useId();
  const save = useSaveLimits();
  const list = useQuery({ queryKey: ["ai-admin", "faculty-list"], queryFn: () => catalogApi.faculties(), staleTime: 60_000, retry: false });
  const faculties = useMemo(() => list.data?.items ?? [], [list.data]);
  const [drafts, setDrafts] = useState<Record<string, FacultyDraft>>(() => Object.fromEntries(Object.entries(data.faculties).map(([k, v]) => [k, draftOf(v)])));
  const [deps, setDeps] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(data.departments).map(([k, v]) => [k, v.monthly_tokens ? String(v.monthly_tokens) : ""])));
  const [strict, setStrict] = useState(data.strict);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<{ faculty: string | null; text: string } | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [overIn, setOverIn] = useState<Record<string, boolean>>({});

  // E2EB-F19: with unsaved changes "Fakülte paylarını kaydet" is the phone's page-actions capsule (M-05), not 1200 px
  // down the tab; the same element changes class, so the focus stays
  const initial = useMemo(
    () => JSON.stringify([Object.fromEntries(Object.entries(data.faculties).map(([k, v]) => [k, draftOf(v)])), Object.fromEntries(Object.entries(data.departments).map(([k, v]) => [k, v.monthly_tokens ? String(v.monthly_tokens) : ""])), data.strict]),
    [data],
  );
  const dirty = JSON.stringify([drafts, deps, strict]) !== initial;
  const capsule = useDirtyCapsule(canEdit && dirty, "flex self-start");
  const draft = (id: string) => drafts[id] ?? draftOf(undefined);
  const setDraft = (id: string, patch: Partial<FacultyDraft>) => setDrafts((x) => ({ ...x, [id]: { ...draft(id), ...patch } }));
  // the in-browser check of the opened faculties: a department split over the allowance blocks the save
  const overAny = Object.values(overIn).some(Boolean);
  const reportOver = useCallback((facultyId: number, v: boolean) => setOverIn((x) => (!!x[facultyId] === v ? x : { ...x, [facultyId]: v })), []);

  const submit = () => {
    setError(null);
    setWarning(null);
    const body = facultyBody(faculties.map((f) => f.id), Object.fromEntries(faculties.map((f) => [String(f.id), draft(String(f.id))])), deps, data.departments, strict);
    if (!body) return setError({ faculty: null, text: t("helper.facultyLimits.invalid") });
    save.mutate(body, {
      onSuccess: (out) => {
        toast.success(t("helper.facultyLimits.saved"));
        const w = out.warnings[0];
        if (w) setWarning((locale === "en" ? w.message_en : w.message_tr) ?? null);
      },
      onError: (e) => setError({ faculty: facultyOfField(e), text: serverText(e, locale, t("aiAdmin.error.save")) }),
    });
  };

  return (
    <Card className="gap-3 px-4 py-4" data-testid="faculty-limits">
      <h3 className="type-headline text-label-1">{t("helper.facultyLimits.title")}</h3>
      <p className="type-footnote text-label-2">{t("helper.facultyLimits.lead")}</p>
      {list.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : list.isError ? (
        <Alert tone="error">{t("helper.facultyLimits.loadError")}</Alert>
      ) : !faculties.length ? (
        <p className="type-callout text-label-2">{t("helper.facultyLimits.empty")}</p>
      ) : (
        <ul className="flex flex-col">
          {faculties.map((f) => {
            const id = String(f.id);
            const d = draft(id);
            const tokens = wholeOrZero(d.tokens) ?? 0;
            return (
              <li key={f.id} className="flex flex-col gap-2 py-3 not-last:edge-hairline-b" data-testid={`faculty-limit-${id}`}>
                <div className="grid items-center gap-1.5 sm:grid-cols-[1fr_12rem]">
                  <Label htmlFor={`${uid}-f${id}`} className="flex flex-col items-start">
                    <span className="type-body font-medium">{f.name}</span>
                    <span className="type-footnote font-normal text-label-2">{tokens ? t("helper.facultyLimits.has", { tokens: n(tokens) }) : t("helper.facultyLimits.none")}</span>
                  </Label>
                  <Input
                    id={`${uid}-f${id}`}
                    inputMode="numeric"
                    aria-label={t("helper.facultyLimits.allowanceFor", { faculty: f.name })}
                    placeholder={t("helper.facultyLimits.allowance")}
                    value={d.tokens}
                    disabled={!canEdit}
                    onChange={(e) => setDraft(id, { tokens: e.target.value })}
                    className="text-base pointer-fine:sm:type-callout"
                  />
                </div>
                {error?.faculty === id ? (
                  <p role="alert" className="type-callout text-status-infeasible-fg">
                    {error.text}
                  </p>
                ) : null}
                <details className="rounded-lg bg-fill-3 px-3 py-1" onToggle={(e) => {
                    const isOpen = e.currentTarget.open;
                    setOpen((x) => ({ ...x, [id]: isOpen }));
                  }}>
                  <summary className="cursor-pointer py-1 type-callout font-medium text-label-1 pointer-coarse:min-h-11 pointer-coarse:py-3">{t("helper.facultyLimits.details")}</summary>
                  {open[id] ? (
                    <div className="flex flex-col gap-3 py-2">
                      <Departments
                        facultyId={f.id}
                        allowance={tokens}
                        deps={deps}
                        setDep={(k, v) => setDeps((x) => ({ ...x, [k]: v }))}
                        onOver={reportOver}
                        canEdit={canEdit}
                      />
                      <Field label={t("helper.facultyLimits.managers")} htmlFor={`${uid}-m${id}`} hint={t("helper.facultyLimits.managersHint")}>
                        <Input id={`${uid}-m${id}`} value={d.managers} disabled={!canEdit} onChange={(e) => setDraft(id, { managers: e.target.value })} className="text-base pointer-fine:sm:type-callout" />
                      </Field>
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <Label htmlFor={`${uid}-p${id}`} className="type-body">
                            {t("helper.facultyLimits.showPeople")}
                          </Label>
                          <p className="type-footnote text-label-2">{t("helper.facultyLimits.showPeopleHint")}</p>
                        </div>
                        <Switch id={`${uid}-p${id}`} checked={d.showPeople} disabled={!canEdit} onCheckedChange={(v) => setDraft(id, { showPeople: v })} />
                      </div>
                      <Field label={t("helper.facultyLimits.cost")} htmlFor={`${uid}-c${id}`} hint={t("aiAdmin.limits.zeroHint")}>
                        <Input id={`${uid}-c${id}`} inputMode="decimal" value={d.cost} disabled={!canEdit} onChange={(e) => setDraft(id, { cost: e.target.value })} className="text-base pointer-fine:sm:type-callout" />
                      </Field>
                    </div>
                  ) : null}
                </details>
              </li>
            );
          })}
        </ul>
      )}
      <details className="rounded-lg bg-fill-3 px-3 py-2" data-testid="faculty-limits-advanced">
        <summary className="cursor-pointer py-1 type-callout font-medium text-label-1 pointer-coarse:min-h-11 pointer-coarse:py-3">{t("helper.form.advanced")}</summary>
        <div className="flex items-center justify-between gap-3 py-2">
          <div className="min-w-0">
            <Label htmlFor={`${uid}-strict`} className="type-body">
              {t("helper.facultyLimits.strict")}
            </Label>
            <p className="type-footnote text-label-2">{t("helper.facultyLimits.strictHint")}</p>
          </div>
          <Switch id={`${uid}-strict`} checked={strict} disabled={!canEdit} onCheckedChange={setStrict} />
        </div>
      </details>
      {error && error.faculty === null ? <Alert tone="error" testId="faculty-limits-error">{error.text}</Alert> : null}
      {warning ? <Alert tone="warning" testId="faculty-limits-warning">{warning}</Alert> : null}
      {canEdit && faculties.length ? (
        <div {...capsule.props}>
          <Button variant="outline" onClick={submit} {...busyProps(save.isPending, overAny)} data-testid="faculty-limits-save">
            <BusyLabel busy={save.isPending} label={t("busy.saving")} icon={<Save aria-hidden />}>
              {t("helper.facultyLimits.save")}
            </BusyLabel>
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

