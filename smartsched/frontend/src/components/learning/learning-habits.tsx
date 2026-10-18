"use client";
/**
 * RF-07 per-habit controls: every habit the system learned for the working term (`GET /learning/priors`), each with
 * one "Düzenle" that offers Kapat (never suggested again), Düzelt (the right value; it is learned as a planner
 * correction), Ağırlığı ayarla (1..5) or Varsayılana dön (`PUT /learning/priors/{id}/habit`). A search narrows the
 * list; at most 20 rows show at once.
 */
import { Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { SelectField } from "@/components/admin/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { usePriors, useLearningVersionActions, type HabitState, type Prior } from "@/lib/api/learning-versions";
import { apiText } from "@/lib/api/seasons";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

const SHOWN = 20;

/** "İnşaat" and "insaat" match (Turkish-insensitive, accents folded) */
export const foldTr = (s: string) => s.toLocaleLowerCase("tr-TR").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ı/g, "i");
type Choice = HabitState | "clear";

export function attributeLabel(t: (k: MessageKey) => string, attr: string): string {
  const k = `adaptive.habit.attr.${attr}` as MessageKey;
  const v = t(k);
  return v === k ? attr.replace(/_/g, " ") : v;
}

export function valueText(p: Pick<Prior, "value" | "value_label">, lang: "tr" | "en"): string {
  const l = p.value_label;
  if (typeof l === "string" && l) return l;
  if (l && typeof l === "object") return l[lang] || l.tr || p.value;
  return p.value;
}

/** priors matching a search (subject, attribute or value; Turkish-insensitive) */
export function filterPriors(list: readonly Prior[], q: string, lang: "tr" | "en", attr: (a: string) => string): Prior[] {
  const want = foldTr(q.trim());
  if (!want) return [...list];
  return list.filter((p) => foldTr(`${p.subject.label} ${attr(p.attribute)} ${valueText(p, lang)}`).includes(want));
}

export function LearningHabits({ termId }: { termId: number | null }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const q = usePriors(termId);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const list = useMemo(() => filterPriors(q.data ?? [], search, lang, (a) => attributeLabel(t, a)), [q.data, search, lang, t]);
  return (
    <section aria-labelledby="mem-habits" className="flex flex-col gap-2" data-testid="learning-habits">
      <h3 id="mem-habits" className="type-headline">{t("adaptive.habit.title")}</h3>
      <p className="type-footnote text-label-2">{t("adaptive.habit.hint")}</p>
      {q.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : q.isError ? (
        <p role="alert" className="type-footnote text-label-2">{t("learning.list.error")}</p>
      ) : (q.data ?? []).length === 0 ? (
        <p className="type-footnote text-label-2">{t("adaptive.habit.none")}</p>
      ) : (
        <>
          <label className="relative block max-w-sm">
            <span className="sr-only">{t("adaptive.habit.search")}</span>
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-label-3" aria-hidden />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("adaptive.habit.search")} className="pl-8" data-testid="habit-search" />
          </label>
          <ul data-testid="habit-list">
            {list.slice(0, all ? list.length : SHOWN).map((p) => (
              <HabitRow key={p.id} p={p} open={open === p.id} onToggle={() => setOpen(open === p.id ? null : p.id)} />
            ))}
          </ul>
          {list.length > SHOWN && !all ? (
            <Button size="xs" variant="secondary" className="self-start" onClick={() => setAll(true)}>{t("adaptive.showAll", { n: list.length })}</Button>
          ) : null}
        </>
      )}
    </section>
  );
}

function HabitRow({ p, open, onToggle }: { p: Prior; open: boolean; onToggle: () => void }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const id = useId();
  const act = useLearningVersionActions();
  const habit = p.evidence.habit ?? null;
  const [choice, setChoice] = useState<Choice>(habit?.state ?? "disabled");
  const [value, setValue] = useState(habit?.to ?? "");
  const [weight, setWeight] = useState(String(habit?.weight ?? 3));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const state = habit?.state;

  const save = () => {
    if (choice === "corrected" && !value.trim()) return setError(t("adaptive.habit.valueMissing"));
    setError(null);
    const body = choice === "clear" ? { state: null } : { state: choice, reason: reason.trim() || undefined, value: choice === "corrected" ? value.trim() : undefined, weight: choice === "tuned" ? Number(weight) : undefined };
    act.habit.mutate({ id: p.id, body }, { onSuccess: () => { toast.success(t("adaptive.habit.saved")); onToggle(); }, onError: (e) => setError(apiText(e, locale)) });
  };

  return (
    <li className="border-b border-hairline py-2" data-testid="habit-row" data-state={state ?? "none"}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-0 flex-1 type-callout text-label-1">
          {p.explanation?.[lang] || t("adaptive.habit.claim", { subject: p.subject.label, attr: attributeLabel(t, p.attribute), value: valueText(p, lang) })}
        </span>
        {state === "disabled" ? <Badge tone="preoccupied">{t("adaptive.habit.state.disabled")}</Badge> : null}
        {state === "corrected" ? <Badge tone="tint">{t("adaptive.habit.state.corrected", { to: habit?.to ?? "" })}</Badge> : null}
        {state === "tuned" ? <Badge tone="tint">{t("adaptive.habit.state.tuned", { n: habit?.weight ?? 0 })}</Badge> : null}
        <Button size="xs" variant="outline" aria-expanded={open} aria-controls={`${id}-form`} onClick={onToggle} data-testid="habit-edit">
          {t("adaptive.habit.edit")}
        </Button>
      </div>
      {open ? (
        <div id={`${id}-form`} className="mt-2 flex flex-col gap-2 rounded-lg bg-fill-3 p-3" data-testid="habit-form">
          <SegmentedControl<Choice>
            semantics="radiogroup"
            aria-label={t("adaptive.habit.edit")}
            value={choice}
            onValueChange={setChoice}
            options={[
              { value: "disabled", label: t("adaptive.habit.do.disabled"), testId: "habit-do-disabled" },
              { value: "corrected", label: t("adaptive.habit.do.corrected"), testId: "habit-do-corrected" },
              { value: "tuned", label: t("adaptive.habit.do.tuned"), testId: "habit-do-tuned" },
              ...(state ? [{ value: "clear" as const, label: t("adaptive.habit.do.clear"), testId: "habit-do-clear" }] : []),
            ]}
          />
          <p className="type-footnote text-label-2">{t(`adaptive.habit.doHint.${choice}`)}</p>
          {choice === "corrected" ? (
            <label className="flex flex-col gap-1 type-footnote">
              <span className="font-medium text-label-2">{t("adaptive.habit.value", { attr: attributeLabel(t, p.attribute) })}</span>
              <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder={valueText(p, lang)} className="max-w-xs" data-testid="habit-value" />
            </label>
          ) : null}
          {choice === "tuned" ? (
            <label className="flex flex-col gap-1 type-footnote">
              <span className="font-medium text-label-2">{t("adaptive.habit.weight")}</span>
              <SelectField value={weight} onChange={(e) => setWeight(e.target.value)} className="max-w-[10rem]" data-testid="habit-weight">
                {[1, 2, 3, 4, 5].map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </SelectField>
            </label>
          ) : null}
          {choice !== "clear" ? (
            <label className="flex flex-col gap-1 type-footnote">
              <span className="font-medium text-label-2">{t("adaptive.habit.reason")}</span>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} className="max-w-md" />
            </label>
          ) : null}
          {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
          <div className="flex gap-2">
            <Button size="sm" onClick={save} disabled={act.habit.isPending} data-testid="habit-save">{t("adaptive.habit.save")}</Button>
            <Button size="sm" variant="ghost" onClick={onToggle}>{t("crbs.common.cancel")}</Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}
