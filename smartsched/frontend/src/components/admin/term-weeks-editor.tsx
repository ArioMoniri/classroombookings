"use client";
/**
 * RF-09: /admin/weeks "Dönem haftaları", the term's week calendar (rf-b API.md §4). Each week's kind (Ders, Sınav,
 * Tatil, Bütünleme) is changed on its own with `PATCH /terms/{id}/weeks/{index}`; a week an admin changed carries
 * "Elle değiştirildi" (`edited`) and is kept by the next board import. Adding a week sits under "Gelişmiş"
 * (`PUT /terms/{id}/weeks` with the whole list); the server's duplicate-week refusal is shown at the number field.
 */
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { NativeSelect } from "@/components/common/native-select";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { refusalCode, serverMessage } from "@/lib/api/error-text";
import { TERM_WEEK_KINDS, termWeeksApi, termWeeksKey, useTermWeeks, type TermWeek } from "@/lib/api/rf-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { Field, Loading } from "./kit";

const kindKey = (k: string): MessageKey | null => ((TERM_WEEK_KINDS as readonly string[]).includes(k) ? (`rf.weeks.kind.${k}` as MessageKey) : null);

export function TermWeeksEditor() {
  const { t } = useI18n();
  const { term, terms } = useActiveTerm();
  const [pick, setPick] = useState<number | null>(null);
  const termId = pick ?? term?.id;
  const weeks = useTermWeeks(termId);
  const [advanced, setAdvanced] = useState(false);
  const id = useId();
  // no planning access (GET /terms/{id}/weeks refused): the section is left out, like AS-F's profiles on 403
  if (!termId || weeks.isError) return null;
  return (
    <Card className="gap-4 px-5" data-testid="term-weeks">
      <section aria-labelledby={`${id}-title`} className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h2 id={`${id}-title`} className="type-title-3 font-semibold text-label-1">
              {t("rf.weeks.title")}
            </h2>
            <p className="type-callout text-label-2">{t("rf.weeks.lead")}</p>
          </div>
          {terms.length > 1 ? (
            <Field label={t("rf.weeks.term")} htmlFor={`${id}-term`} className="w-full sm:w-64">
              <NativeSelect id={`${id}-term`} value={String(termId)} onChange={(e) => setPick(Number(e.target.value))}>
                {terms.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          ) : null}
        </div>
        {weeks.isLoading ? (
          <Loading />
        ) : (weeks.data ?? []).length === 0 ? (
          <p className="type-callout text-label-2">{t("rf.weeks.none")}</p>
        ) : (
          <ul className="divide-y divide-hairline rounded-xl edge-hairline">
            {(weeks.data ?? []).map((w) => (
              <WeekRow key={w.index} termId={termId} week={w} />
            ))}
          </ul>
        )}
        <div className="flex flex-col gap-3">
          <Button type="button" variant="ghost" className="self-start pointer-coarse:h-11" aria-expanded={advanced} aria-controls={`${id}-adv`} onClick={() => setAdvanced((v) => !v)} data-testid="term-weeks-advanced">
            <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", advanced && "rotate-180")} />
            {t("rf.weeks.advanced")}
          </Button>
          {advanced ? (
            <div id={`${id}-adv`}>
              <AddWeek termId={termId} weeks={weeks.data ?? []} />
            </div>
          ) : null}
        </div>
      </section>
    </Card>
  );
}

/** the shared ["weeks", termId] lists (timetable, studio) refresh; this editor's own list keeps the server's answer */
function useWeeksWrite(termId: number) {
  const qc = useQueryClient();
  return (next: (list: TermWeek[]) => TermWeek[]) => {
    qc.setQueryData<TermWeek[]>(termWeeksKey(termId), (list) => next(list ?? []));
    void qc.invalidateQueries({ queryKey: ["weeks", termId], predicate: (q) => q.queryKey[2] !== "admin" });
  };
}

function WeekRow({ termId, week }: { termId: number; week: TermWeek }) {
  const { t, locale } = useI18n();
  const write = useWeeksWrite(termId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const change = async (kind: string) => {
    setBusy(true);
    setError(null);
    try {
      const out = await termWeeksApi.patch(termId, week.index, { kind });
      write((list) => list.map((w) => (w.index === out.index ? out : w)));
      const k = kindKey(out.kind);
      toast.success(t("rf.weeks.saved", { n: out.index, kind: k ? t(k) : out.kind }));
    } catch (e) {
      setError(serverMessage(e, locale) ?? t("glass.import.failed"));
    } finally {
      setBusy(false);
    }
  };
  const known = kindKey(week.kind) !== null;
  return (
    <li className="flex flex-col gap-1 px-3 py-2" data-testid={`term-week-${week.index}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="type-callout font-medium text-label-1">{t("rf.weeks.week", { n: week.index })}</p>
          <p className="truncate type-footnote text-label-2">{[week.start_date ? formatDate(week.start_date, locale, { year: "numeric" }) : t("rf.weeks.noDate"), week.label].filter(Boolean).join(" · ")}</p>
        </div>
        {week.edited ? <Badge variant="secondary">{t("rf.weeks.edited")}</Badge> : null}
        <NativeSelect
          className="w-40"
          aria-label={t("rf.weeks.kindNamed", { n: week.index })}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-err` : undefined}
          value={week.kind}
          disabled={busy}
          aria-busy={busy || undefined}
          onChange={(e) => void change(e.target.value)}
        >
          {known ? null : <option value={week.kind}>{week.kind}</option>}
          {TERM_WEEK_KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`rf.weeks.kind.${k}`)}
            </option>
          ))}
        </NativeSelect>
      </div>
      {error ? (
        <p id={`${id}-err`} role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function AddWeek({ termId, weeks }: { termId: number; weeks: TermWeek[] }) {
  const { t, locale } = useI18n();
  const write = useWeeksWrite(termId);
  const next = weeks.length ? Math.max(...weeks.map((w) => w.index)) + 1 : 1;
  const [index, setIndex] = useState(String(next));
  const [start, setStart] = useState("");
  const [kind, setKind] = useState<string>("LECTURE");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; atIndex: boolean } | null>(null);
  const id = useId();
  const num = Number(index);
  const valid = Number.isInteger(num) && num >= 1 && num <= 60;
  const add = async () => {
    setBusy(true);
    setError(null);
    try {
      // the whole calendar with the new week; the server refuses a number that is already taken
      const body = [...weeks.map((w) => ({ index: w.index, start_date: w.start_date, kind: w.kind, label: w.label })), { index: num, start_date: start || null, kind, label: label.trim() || null }];
      const out = await termWeeksApi.replace(termId, body);
      write(() => out);
      toast.success(t("rf.weeks.added", { n: num }));
      setIndex(String(Math.max(num, ...out.map((w) => w.index)) + 1));
      setStart("");
      setLabel("");
    } catch (e) {
      const atIndex = refusalCode(e) === "week_index_duplicate";
      setError({ message: serverMessage(e, locale) ?? t("glass.import.failed"), atIndex });
      requestAnimationFrame(() => document.getElementById(atIndex ? `${id}-index` : `${id}-err`)?.focus());
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="flex flex-col gap-3 rounded-xl bg-fill-3 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void add();
      }}
    >
      <h3 className="type-headline text-label-1">{t("rf.weeks.addTitle")}</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label={t("rf.weeks.index")} htmlFor={`${id}-index`}>
          <Input id={`${id}-index`} inputMode="numeric" value={index} onChange={(e) => (setIndex(e.target.value), setError(null))} aria-invalid={error?.atIndex ? true : undefined} aria-describedby={error?.atIndex ? `${id}-index-err` : undefined} />
          {error?.atIndex ? (
            <p id={`${id}-index-err`} role="alert" className="type-footnote text-status-infeasible-fg" data-testid="term-week-add-error">
              {error.message}
            </p>
          ) : null}
        </Field>
        <Field label={t("rf.weeks.startDate")} htmlFor={`${id}-start`}>
          <Input id={`${id}-start`} type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label={t("rf.weeks.kindLabel")} htmlFor={`${id}-kind`}>
          <NativeSelect id={`${id}-kind`} value={kind} onChange={(e) => setKind(e.target.value)}>
            {TERM_WEEK_KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`rf.weeks.kind.${k}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label={t("rf.weeks.label")} htmlFor={`${id}-label`}>
          <Input id={`${id}-label`} maxLength={128} value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
      </div>
      {error && !error.atIndex ? (
        <p id={`${id}-err`} tabIndex={-1} role="alert" className="type-footnote text-status-infeasible-fg outline-hidden" data-testid="term-week-add-error">
          {error.message}
        </p>
      ) : null}
      <div>
        <Button type="submit" variant="outline" {...busyProps(busy, !valid)} data-testid="term-week-add">
          <BusyLabel busy={busy} label={t("busy.saving")} icon={<Plus aria-hidden />}>
            {t("rf.weeks.add")}
          </BusyLabel>
        </Button>
      </div>
    </form>
  );
}
