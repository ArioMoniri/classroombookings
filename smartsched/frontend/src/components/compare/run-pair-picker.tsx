"use client";
/**
 * Two-run picker: A (baseline, "before") and B (scenario, "after"). The backend compares two runs of the same
 * term and kind, so B lists only those (the others stay visible, disabled, with the reason in the label) and a
 * new A that does not match B clears B. Native selects: full keyboard and the OS picker on phones.
 */
import { ArrowLeftRight } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { pageActionsCapsule } from "@/components/admin/kit";
import { Button, IconButton } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { comparableWith } from "./compare-model";
import { useRunText } from "./run-text";

export function RunPairPicker({
  runs,
  a: initialA,
  b: initialB,
  onApply,
  loading,
  compact = false,
  className,
}: {
  runs: readonly ScheduleRun[] | undefined;
  a: number | null;
  b: number | null;
  onApply: (a: number, b: number) => void;
  loading?: boolean;
  /** stacked fields (dialogs, phones) */
  compact?: boolean;
  className?: string;
}) {
  const { t } = useI18n();
  const id = useId();
  const runText = useRunText();
  const [a, setA] = useState<number | null>(initialA);
  const [b, setB] = useState<number | null>(initialB);
  // follow the URL when it changes from outside (state adjusted during render, no effect)
  const [synced, setSynced] = useState(`${initialA}|${initialB}`);
  if (synced !== `${initialA}|${initialB}`) {
    setSynced(`${initialA}|${initialB}`);
    setA(initialA);
    setB(initialB);
  }
  const list = useMemo(() => runs ?? [], [runs]);
  const runA = list.find((r) => r.id === a);
  const okForB = useMemo(() => new Set(comparableWith(list, runA).map((r) => r.id)), [list, runA]);
  const terms = useMemo(() => {
    const m = new Map<string, ScheduleRun[]>();
    for (const r of list) m.set(r.term_code ?? `#${r.term_id}`, [...(m.get(r.term_code ?? `#${r.term_id}`) ?? []), r]);
    return [...m.entries()];
  }, [list]);
  const valid = a !== null && b !== null && a !== b && okForB.has(b);
  const floating = !compact && valid && (a !== initialA || b !== initialB);

  const options = (forB: boolean) =>
    terms.map(([code, rs]) => (
      <optgroup key={code} label={code}>
        {rs.map((r) => {
          const off = forB && runA !== undefined && !okForB.has(r.id);
          return (
            <option key={r.id} value={r.id} disabled={off}>
              {runText(r)}
              {off ? ` (${r.id === runA?.id ? t("compare.picker.same") : t("compare.picker.otherKind")})` : ""}
            </option>
          );
        })}
      </optgroup>
    ));

  return (
    <form
      className={cn("flex flex-col gap-3", !compact && "md:flex-row md:items-end", className)}
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onApply(a, b);
      }}
      data-testid="compare-picker"
    >
      <label className="flex min-w-0 flex-1 flex-col gap-1" htmlFor={`${id}-a`}>
        <span className="type-footnote font-medium text-label-2">{t("compare.picker.a")}</span>
        <NativeSelect
          id={`${id}-a`}
          value={a ?? ""}
          disabled={loading}
          onChange={(e) => {
            const v = e.target.value ? Number(e.target.value) : null;
            setA(v);
            const ra = list.find((r) => r.id === v);
            if (b !== null && (!ra || !comparableWith(list, ra).some((r) => r.id === b))) setB(null);
          }}
          data-testid="compare-pick-a"
        >
          <option value="">{loading ? t("compare.picker.loading") : t("compare.picker.choose")}</option>
          {options(false)}
        </NativeSelect>
      </label>
      <IconButton
        type="button"
        label={t("compare.picker.swap")}
        variant="outline"
        className={cn("self-center", !compact && "md:mb-0 md:self-end")}
        disabled={a === null || b === null}
        onClick={() => {
          setA(b);
          setB(a);
        }}
        data-testid="compare-swap"
      >
        <ArrowLeftRight aria-hidden />
      </IconButton>
      <label className="flex min-w-0 flex-1 flex-col gap-1" htmlFor={`${id}-b`}>
        <span className="type-footnote font-medium text-label-2">{t("compare.picker.b")}</span>
        <NativeSelect id={`${id}-b`} value={b ?? ""} disabled={loading || a === null} onChange={(e) => setB(e.target.value ? Number(e.target.value) : null)} data-testid="compare-pick-b">
          <option value="">{a === null ? t("compare.picker.chooseAFirst") : t("compare.picker.choose")}</option>
          {options(true)}
        </NativeSelect>
      </label>
      {/* MOBILE.md M-05 (mobile-b phase 2: compare-apply sat at y 375): once a new pair is picked, the one primary
          floats in the page-actions capsule above the tab bar below lg; in a dialog (compact) it stays in flow */}
      <div data-slot="page-actions" className={cn("flex", floating && pageActionsCapsule)} data-floating={floating || undefined}>
        <Button type="submit" disabled={!valid} className="max-md:h-11" data-testid="compare-apply">
          {t("compare.picker.apply")}
        </Button>
      </div>
    </form>
  );
}
