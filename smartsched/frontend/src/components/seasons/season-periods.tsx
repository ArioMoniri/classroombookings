"use client";
/**
 * AS-15 "Dönem takvimi": the dated period segments of one term (from the week kinds, the holidays and the admin
 * segments). Segments proposed by an import are drafts ("Öneri") and change nothing until an admin approves them.
 * Adding a segment (add/drop, midterm weeks) is behind "Gelişmiş": the calendar works without it.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Alert, Field, Loading, SectionTitle, SelectField } from "@/components/admin/kit";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiText, useProfileActions, useProfiles, useTermPeriods, type Period } from "@/lib/api/seasons";
import { useI18n } from "@/lib/i18n/provider";

const SEGMENT_KINDS = ["ADD_DROP", "MIDTERM", "EXAM", "MAKEUP", "BREAK"] as const;

export function SeasonPeriods() {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const { term, terms } = useActiveTerm();
  const [picked, setPicked] = useState<number | null>(null);
  const termId = picked ?? term?.id ?? null;
  const q = useTermPeriods(termId);
  const meta = useProfiles();
  const act = useProfileActions();
  const [kind, setKind] = useState<string>("MIDTERM");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const date = (d: string | null | undefined) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString(locale === "tr" ? "tr-TR" : "en-GB", { day: "numeric", month: "short" }) : "");
  const weeks = (p: Pick<Period, "week_from" | "week_to">) => (p.week_from == null ? "" : p.week_to != null && p.week_to !== p.week_from ? t("seasons.periods.weeks", { from: p.week_from, to: p.week_to }) : t("seasons.periods.week", { n: p.week_from }));
  const kindLabel = (k: string) => meta.data?.period_kinds.find((x) => x.key === k)?.label[lang] ?? k;

  const add = () => {
    const a = Number(from);
    const b = Number(to || from);
    if (termId === null || !Number.isInteger(a) || !Number.isInteger(b) || a < 1 || b < a) return toast.error(t("seasons.periods.weeksInvalid"));
    act.createSegment.mutate({ termId, body: { kind, week_from: a, week_to: b, status: "active" } }, { onSuccess: () => { toast.success(t("seasons.periods.added")); setFrom(""); setTo(""); }, onError: (e) => toast.error(apiText(e, locale)) });
  };

  return (
    <section aria-labelledby="season-periods" className="mt-3 flex flex-col gap-3" data-testid="season-periods">
      <SectionTitle id="season-periods">{t("seasons.periods.title")}</SectionTitle>
      <p className="-mt-2 type-callout text-label-2">{t("seasons.periods.lead")}</p>
      <label className="flex max-w-xs flex-col gap-1">
        <span className="type-footnote font-medium text-label-2">{t("seasons.periods.term")}</span>
        <SelectField value={termId ?? ""} onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)} data-testid="periods-term">
          {terms.map((x) => (
            <option key={x.id} value={x.id}>{x.name}</option>
          ))}
        </SelectField>
      </label>
      <Card className="py-0">
        {q.isLoading ? (
          <Loading className="px-4" />
        ) : q.isError ? (
          <div className="p-4"><Alert tone="error" title={t("seasons.loadError")}>{apiText(q.error, locale)}</Alert></div>
        ) : !q.data || q.data.periods.length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{q.data?.needs?.[lang] || t("seasons.periods.none")}</p>
        ) : (
          <ul data-testid="periods-list">
            {q.data.periods.map((p, i) => {
              const draft = p.status === "draft" && p.segment_id != null;
              return (
                <li key={`${p.kind}-${p.week_from}-${i}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 not-last:edge-hairline-b" data-testid="period-row" data-status={p.status}>
                  <span className="min-w-0 flex-1 type-callout text-label-1">
                    {p.label?.[lang] || p.kind_label?.[lang] || kindLabel(p.kind)}
                    {draft ? <Badge tone="warning" className="ml-2">{t("seasons.periods.proposal")}</Badge> : null}
                  </span>
                  <span className="type-footnote text-label-2 tabular-nums">
                    {[weeks(p), p.date_from ? `${date(p.date_from)}${p.date_to && p.date_to !== p.date_from ? `–${date(p.date_to)}` : ""}` : ""].filter(Boolean).join(" · ")}
                  </span>
                  {draft ? (
                    <span className="flex gap-2">
                      <Button size="sm" onClick={() => act.approveSegment.mutate(p.segment_id ?? 0, { onSuccess: () => toast.success(t("seasons.periods.approved")), onError: (e) => toast.error(apiText(e, locale)) })} data-testid="period-approve">
                        {t("seasons.periods.approve")}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => act.removeSegment.mutate(p.segment_id ?? 0, { onSuccess: () => toast.success(t("seasons.periods.removed")), onError: (e) => toast.error(apiText(e, locale)) })} data-testid="period-remove">
                        {t("seasons.periods.remove")}
                      </Button>
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      <details className="rounded-lg bg-fill-3 px-3 py-1" data-testid="periods-advanced">
        <summary className="flex min-h-11 cursor-pointer items-center type-callout font-medium text-label-1">{t("seasons.periods.advanced")}</summary>
        <div className="flex flex-wrap items-end gap-3 pb-3">
          <Field label={t("seasons.periods.kind")} htmlFor="seg-kind">
            <SelectField id="seg-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
              {SEGMENT_KINDS.map((k) => (
                <option key={k} value={k}>{kindLabel(k)}</option>
              ))}
            </SelectField>
          </Field>
          <Field label={t("seasons.periods.from")} htmlFor="seg-from">
            <Input id="seg-from" type="number" inputMode="numeric" min={1} value={from} onChange={(e) => setFrom(e.target.value)} className="w-24" />
          </Field>
          <Field label={t("seasons.periods.to")} htmlFor="seg-to">
            <Input id="seg-to" type="number" inputMode="numeric" min={1} value={to} onChange={(e) => setTo(e.target.value)} className="w-24" placeholder={from} />
          </Field>
          <Button variant="outline" onClick={add} disabled={act.createSegment.isPending || !from} data-testid="segment-add">
            {t("seasons.periods.add")}
          </Button>
        </div>
      </details>
    </section>
  );
}
