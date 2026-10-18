"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5.3.3): the period control is the existing SegmentedControl
// (motion pattern 2, glass-morph pill); 44 px and full width on phones. `usePeriodParam` keeps the value in the URL
// (`?period=30d`) so a link reproduces the view. Original work.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { BELOW_MD, useMediaQuery } from "@/components/ui/use-media-query";

export interface PeriodOption<V extends string = string> {
  value: V;
  label: string;
  /** overrides the default `chart-period-<id>-<value>` test id (kept ids of a migrated surface) */
  testId?: string;
}

export interface PeriodPickerProps<V extends string> {
  value: V;
  options: readonly PeriodOption<V>[];
  onChange: (value: V) => void;
  label: string;
  id?: string;
}

export function PeriodPicker<V extends string>({ value, options, onChange, label, id }: PeriodPickerProps<V>) {
  const phone = useMediaQuery(BELOW_MD);
  return (
    <SegmentedControl<V>
      options={options.map((o) => ({ value: o.value, label: o.label, text: o.label, testId: o.testId ?? (id ? `chart-period-${id}-${o.value}` : undefined) }))}
      value={value}
      onValueChange={onChange}
      semantics="tablist"
      size="md"
      fill={phone}
      aria-label={label}
      data-testid={id ? `chart-period-${id}` : undefined}
    />
  );
}

/** `[value, setValue]` backed by `?<key>=` (replace, no scroll); an unknown value falls back. */
export function usePeriodParam<V extends string>(options: readonly V[], fallback: V, key = "period"): [V, (next: V) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params?.get(key);
  const value = raw && (options as readonly string[]).includes(raw) ? (raw as V) : fallback;
  const set = useCallback(
    (next: V) => {
      const q = new URLSearchParams(params?.toString() ?? "");
      if (next === fallback) q.delete(key);
      else q.set(key, next);
      const s = q.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [params, router, pathname, key, fallback],
  );
  return [value, set];
}
