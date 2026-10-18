"use client";
/**
 * AS-16 what-if: "+N % öğrenci" for the whole institution, one faculty or one programme → how many classes no longer
 * fit a room and how many seat-hours fall short, today vs the scenario (`POST /analytics/forecast/what-if`). The
 * optional draft run ("Senaryo: …") is never published by itself; the answer links to it and to the comparison.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Field, SelectField } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useWhatIf, type WhatIfOut, type WhatIfScope } from "@/lib/api/adaptive";
import { catalogApi } from "@/lib/api/catalog-admin";
import { apiText } from "@/lib/api/seasons";
import { useI18n } from "@/lib/i18n/provider";
import { ConfidenceNote } from "./forecast-bits";

/** "+12" / "-5" / "12" → a whole percentage inside the backend's bounds (-90..200), else null */
export function parsePct(raw: string): number | null {
  const v = Number(raw.trim().replace(",", ".").replace(/^\+/, ""));
  if (!Number.isFinite(v) || v < -90 || v > 200) return null;
  return Math.round(v);
}

export function WhatIfForm({ termId }: { termId: number }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [pct, setPct] = useState("10");
  const [scope, setScope] = useState<WhatIfScope>("all");
  const [value, setValue] = useState("");
  const [solve, setSolve] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [out, setOut] = useState<WhatIfOut | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const m = useWhatIf();
  const options = useQuery({
    queryKey: ["adaptive", "scope-options", scope],
    queryFn: async () => (scope === "faculty" ? (await catalogApi.faculties()).items.map((f) => f.name) : (await catalogApi.programs()).items.map((p) => p.name)),
    enabled: scope !== "all",
    staleTime: 10 * 60_000,
  });
  useEffect(() => {
    if (out) resultRef.current?.focus();
  }, [out]);

  const submit = () => {
    const p = parsePct(pct);
    if (p === null) return setError(t("adaptive.whatIf.pctInvalid"));
    if (scope !== "all" && !value) return setError(t("adaptive.whatIf.scopeMissing"));
    setError(null);
    m.mutate({ term_id: termId, enrolment_pct: p, scope, scope_value: scope === "all" ? undefined : value, solve }, { onSuccess: setOut, onError: (e) => setError(apiText(e, locale)) });
  };

  const fit = (r: WhatIfOut["today"]) => t("adaptive.whatIf.fit", { noFit: n(r.no_fit), classes: n(r.classes), short: n(r.shortfall_total) });
  return (
    <section aria-labelledby="fc-whatif" className="flex flex-col gap-3" data-testid="whatif">
      <div>
        <h2 id="fc-whatif" className="type-title-3 text-label-1">{t("adaptive.whatIf.title")}</h2>
        <p className="type-footnote text-label-2">{t("adaptive.whatIf.hint")}</p>
      </div>
      <Card className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-end gap-4">
          <Field label={t("adaptive.whatIf.pct")} htmlFor="wi-pct" error={null}>
            <Input id="wi-pct" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} className="w-28" data-testid="wi-pct" />
          </Field>
          <div className="flex flex-col gap-1.5">
            <span id="wi-scope" className="type-footnote font-medium text-label-2">{t("adaptive.whatIf.scope")}</span>
            <SegmentedControl<WhatIfScope>
              semantics="radiogroup"
              aria-labelledby="wi-scope"
              value={scope}
              onValueChange={(v) => { setScope(v); setValue(""); }}
              options={[
                { value: "all", label: t("adaptive.whatIf.scopeAll"), testId: "wi-scope-all" },
                { value: "faculty", label: t("adaptive.whatIf.scopeFaculty"), testId: "wi-scope-faculty" },
                { value: "program", label: t("adaptive.whatIf.scopeProgram"), testId: "wi-scope-program" },
              ]}
            />
          </div>
          {scope !== "all" ? (
            <Field label={scope === "faculty" ? t("adaptive.whatIf.scopeFaculty") : t("adaptive.whatIf.scopeProgram")} htmlFor="wi-value" className="min-w-0 flex-1">
              <SelectField id="wi-value" value={value} onChange={(e) => setValue(e.target.value)} data-testid="wi-value">
                <option value="">{options.isLoading ? t("busy.loading") : t("adaptive.whatIf.pick")}</option>
                {(options.data ?? []).map((x) => (
                  <option key={x} value={x}>{x}</option>
                ))}
              </SelectField>
            </Field>
          ) : null}
        </div>
        <label className="flex min-h-11 items-center gap-2 type-callout">
          <Checkbox checked={solve} onCheckedChange={(v) => setSolve(Boolean(v))} data-testid="wi-solve" />
          {t("adaptive.whatIf.solve")}
        </label>
        {error ? <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="wi-error">{error}</p> : null}
        <Button className="self-start" onClick={submit} disabled={m.isPending} data-testid="wi-submit">
          <BusyLabel busy={m.isPending} label={t("busy.working")}>{t("adaptive.whatIf.submit")}</BusyLabel>
        </Button>
      </Card>
      {out ? (
        <div ref={resultRef} tabIndex={-1} className="flex flex-col gap-2 rounded-xl bg-card p-4 outline-hidden edge-hairline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" role="status" data-testid="wi-result">
          <p className="type-headline text-label-1">{out.scenario?.label?.[lang] || t("adaptive.whatIf.result")}</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 type-callout">
            <dt className="text-label-2">{t("adaptive.whatIf.today")}</dt>
            <dd>{fit(out.today)}</dd>
            <dt className="text-label-2">{t("adaptive.whatIf.scenario")}</dt>
            <dd className="font-semibold" data-testid="wi-scenario">{fit(out.what_if)}</dd>
          </dl>
          <p className="type-callout text-label-1">
            {out.delta.no_fit > 0 ? t("adaptive.whatIf.worse", { n: n(out.delta.no_fit) }) : out.delta.no_fit < 0 ? t("adaptive.whatIf.better", { n: n(-out.delta.no_fit) }) : t("adaptive.whatIf.same")}
          </p>
          <ConfidenceNote confidence={out.confidence} needs={out.needs?.[lang]} />
          {out.run_id ? (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" nativeButton={false} render={<Link href={`/runs/${out.run_id}`} />} data-testid="wi-run">
                {t("adaptive.whatIf.openRun", { id: out.run_id })}
              </Button>
              <Button size="sm" variant="ghost" nativeButton={false} render={<Link href="/runs/compare" />}>
                {t("adaptive.whatIf.compare")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
