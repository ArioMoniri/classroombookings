"use client";
/**
 * HX-10 (ROADMAP HX-10; backend HB-10 / HB-11 `GET /ai/faculty/usage`, `PUT /ai/faculty/allocations`): the faculty
 * manager's view (`ai.usage_faculty`, or an admin). Totals, departments and the trend in sentences (no KPI wall),
 * led by the share of the allowance and the requests; the word "token" never shows, the raw counts are "yapay zekâ
 * birimi" under "Gelişmiş" and in the split editor's label (HX-18 M8),
 * people only when the faculty shows them, and "Bölümlere paylaştır": the department split is checked against the
 * faculty's allowance before saving, and the server's 422 message is shown inline.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Alert, SectionTitle } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { helperRefusal, useFacultyUsage, useSaveFacultyAllocations, type FacultyUsage as Usage } from "@/lib/api/helper";
import { intlLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

/** Whole per cent of `used` against `of` (null when there is no allowance). */
export function percentOf(used: number, of: number | null | undefined): number | null {
  if (!of || of <= 0) return null;
  return Math.round((used / of) * 100);
}

/** The department split's total and whether it fits the faculty's monthly allowance (null = no allowance). */
export function shareCheck(split: Record<string, number | null>, allowance: number | null | undefined): { sum: number; over: boolean } {
  const sum = Object.values(split).reduce<number>((a, v) => a + (v ?? 0), 0);
  return { sum, over: allowance !== null && allowance !== undefined && sum > allowance };
}

function Split({ data }: { data: Usage }) {
  const { t, locale, n } = useI18n();
  const save = useSaveFacultyAllocations();
  const [split, setSplit] = useState<Record<string, number | null>>(() => Object.fromEntries(data.by_department.map((d) => [String(d.id), d.allocation?.monthly_tokens ?? null])));
  const [error, setError] = useState<string | null>(null);
  const allowance = data.allocation?.monthly_tokens ?? null;
  const { sum, over } = shareCheck(split, allowance);
  const deptLine = (d: Usage["by_department"][number]) => {
    const pct = percentOf(d.tokens, d.allocation?.monthly_tokens);
    return pct === null ? t("helper.faculty.deptRowNoShare", { calls: n(d.calls) }) : t("helper.faculty.deptRow", { calls: n(d.calls), pct: n(pct) });
  };
  const submit = async () => {
    if (!data.faculty || over) return;
    setError(null);
    try {
      await save.mutateAsync({ facultyId: data.faculty.id, departments: Object.fromEntries(Object.entries(split).map(([k, v]) => [k, { monthly_tokens: v }])) });
      toast(t("helper.faculty.saved"));
    } catch (err) {
      const r = helperRefusal(err);
      setError((locale === "en" ? r.en : r.tr) ?? t("helper.error.provider"));
    }
  };
  return (
    <div className="flex flex-col gap-3" data-testid="faculty-share">
      <h3 className="type-headline text-label-1">{t("helper.faculty.share")}</h3>
      <ul className="flex flex-col gap-2">
        {data.by_department.map((d) => (
          <li key={d.id} className="grid items-center gap-1.5 sm:grid-cols-[1fr_12rem]" data-testid={`faculty-row-${d.id}`}>
            <Label htmlFor={`fa-${d.id}`} className="flex flex-col items-start">
              <span>{d.name}</span>
              <span className="type-footnote font-normal text-label-2">{deptLine(d)}</span>
            </Label>
            <Input
              id={`fa-${d.id}`}
              type="number"
              min={0}
              inputMode="numeric"
              aria-label={`${d.name}: ${t("helper.faculty.deptShare")}`}
              value={split[String(d.id)] ?? ""}
              onChange={(e) => setSplit((p) => ({ ...p, [String(d.id)]: e.target.value === "" ? null : Math.max(0, Math.round(Number(e.target.value))) }))}
              className="text-base pointer-fine:sm:type-callout"
            />
          </li>
        ))}
      </ul>
      {allowance !== null ? (
        <p className={over ? "type-callout text-status-infeasible-fg" : "type-callout text-label-2"} role={over ? "alert" : undefined} data-testid="faculty-share-sum">
          {over ? t("helper.faculty.shareOver") : t("helper.faculty.shareSum", { sum: n(sum), max: n(allowance) })}
        </p>
      ) : null}
      {error ? <Alert tone="error" testId="faculty-share-error">{error}</Alert> : null}
      <Button className="self-start" disabled={over || save.isPending} onClick={() => void submit()} data-testid="faculty-share-save">
        {save.isPending ? t("busy.saving") : t("helper.faculty.share")}
      </Button>
    </div>
  );
}

export function FacultyUsageView() {
  const { t, locale, n } = useI18n();
  const totalLine = (u: Usage) => {
    const pct = percentOf(u.totals.tokens, u.allocation?.monthly_tokens);
    return pct === null ? t("helper.faculty.totalNoShare", { calls: n(u.totals.calls) }) : t("helper.faculty.total", { pct: n(pct), calls: n(u.totals.calls) });
  };
  const [facultyId, setFacultyId] = useState<number | null>(null);
  const q = useFacultyUsage(facultyId);
  const d = q.data;
  const refusal = q.error ? helperRefusal(q.error) : null;
  const [advanced, setAdvanced] = useState(false);
  const busiest = d?.trend.reduce<{ day: string; tokens: number } | null>((a, x) => (!a || x.tokens > a.tokens ? x : a), null);
  const topFeature = d?.by_feature.slice().sort((a, b) => b.tokens - a.tokens)[0];
  return (
    <section aria-labelledby="fa-title" className="flex flex-col gap-4" data-testid="faculty-usage">
      <SectionTitle id="fa-title">{t("helper.faculty.title")}</SectionTitle>
      {q.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : refusal ? (
        <Alert tone={refusal.status === 403 ? "info" : "error"}>
          {refusal.code === "no_faculty" ? t("helper.faculty.none") : refusal.code === "faculty_not_managed" ? t("helper.faculty.notManaged") : t("helper.faculty.loadError")}
        </Alert>
      ) : d ? (
        <Card variant="glass" className="gap-4 px-4">
          {d.faculties.length > 1 ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fa-pick">{t("helper.faculty.pick")}</Label>
              <NativeSelect id="fa-pick" value={String(d.faculty?.id ?? "")} onChange={(e) => setFacultyId(Number(e.target.value) || null)}>
                {d.faculties.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : d.faculty ? (
            <p className="type-headline text-label-1">{d.faculty.name}</p>
          ) : null}
          <div className="flex flex-col gap-1 type-callout text-label-1">
            <p data-testid="faculty-total">{totalLine(d)}</p>
            {d.allocation?.monthly_tokens ? null : <p className="text-label-2">{t("helper.faculty.noAllocation")}</p>}
            {busiest && busiest.tokens > 0 ? (
              <p className="text-label-2">
                {t("helper.faculty.trend", { day: new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "long", timeZone: "UTC" }).format(new Date(busiest.day)) })}
              </p>
            ) : null}
            {topFeature ? <p className="text-label-2">{t("helper.faculty.features", { feature: (locale === "en" ? topFeature.label_en : topFeature.label_tr) ?? topFeature.feature })}</p> : null}
          </div>
          {d.faculty && d.by_department.length ? <Split key={d.faculty.id} data={d} /> : null}
          <div className="flex flex-col gap-1">
            <Button variant="ghost" size="sm" className="-ml-2 self-start" aria-expanded={advanced} onClick={() => setAdvanced((v) => !v)} data-testid="faculty-advanced">
              {t("helper.faculty.advanced")}
            </Button>
            {advanced ? (
              <div className="flex flex-col gap-1 type-callout text-label-2" data-testid="faculty-units">
                <p>{d.allocation?.monthly_tokens ? t("helper.faculty.units", { used: n(d.totals.tokens), max: n(d.allocation.monthly_tokens) }) : t("helper.faculty.unitsNoShare", { used: n(d.totals.tokens) })}</p>
                <p className="type-footnote">{t("helper.faculty.unitsHint")}</p>
              </div>
            ) : null}
          </div>
          {d.show_people && d.people?.length ? (
            <div className="flex flex-col gap-1">
              <h3 className="type-headline text-label-1">{t("helper.faculty.people")}</h3>
              <ul className="type-callout text-label-1">
                {d.people.map((p, i) => (
                  <li key={i} className="py-1 not-last:edge-hairline-b">
                    {p.label}
                    {p.department ? <span className="text-label-2"> · {p.department}</span> : null}
                    {d.totals.tokens > 0 ? <span className="text-label-2"> · {t("helper.faculty.personRow", { pct: n(percentOf(p.tokens, d.totals.tokens) ?? 0) })}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>
      ) : null}
    </section>
  );
}
