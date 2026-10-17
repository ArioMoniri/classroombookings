/**
 * Pure helpers of the scenario comparison page (backend services/scenario_compare.py): which class changes a
 * filter shows, the verdict of a metric (better / worse / same / neutral, always as words + a glyph, never colour
 * alone) and the number formats.
 */
import type { ChangeKind, ClassItem, CompareData, Metric } from "@/lib/api/analytics";
import type { ScheduleRun } from "@/lib/api/schemas";

export type ClassFilter = "moved" | "only_in_a" | "only_in_b";
export const CLASS_FILTERS: readonly ClassFilter[] = ["moved", "only_in_a", "only_in_b"];
export const CHANGE_KINDS: readonly ChangeKind[] = ["time", "room", "time_room", "weeks", "split"];

export interface ClassRow extends ClassItem {
  bucket: ClassFilter;
}

const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i");

/** the rows of one bucket, narrowed to a change kind (moved only) and a free-text query (class, rooms, time) */
export function classRows(data: CompareData | undefined, filter: ClassFilter, change: ChangeKind | "all", query: string): ClassRow[] {
  if (!data) return [];
  const list = data.classes[filter] ?? [];
  const q = fold(query.trim());
  return list
    .filter((r) => filter !== "moved" || change === "all" || r.change === change)
    .filter((r) => {
      if (!q) return true;
      const hay = [r.label, ...(r.a?.rooms ?? []), ...(r.b?.rooms ?? []), r.a?.time ?? "", r.b?.time ?? "", r.instructor_text ?? ""].join(" ");
      return fold(hay).includes(q);
    })
    .map((r) => ({ ...r, bucket: filter }));
}

export type Verdict = "better" | "worse" | "same" | "neutral" | "na" | "incomparable";

/** B (the scenario) against A (the baseline): the backend's `better` read from B's side. A metric one run has no data
 * for (`comparable: false`, round-1 R1-M-10) is "karşılaştırılamaz", never better or worse. */
export function verdict(m: Pick<Metric, "better" | "direction" | "delta"> & { comparable?: boolean }): Verdict {
  if (m.comparable === false) return "incomparable";
  if (m.delta === null || m.delta === undefined) return "na";
  if (m.better === "same" || m.delta === 0) return "same";
  if (m.direction === 0 || m.better === null) return "neutral";
  return m.better === "b" ? "better" : "worse";
}

/** percentages print with a % sign, counts as integers, loads with one decimal */
export function metricValue(key: string, v: number | null, locale: string): string {
  if (v === null || v === undefined) return "—";
  const f = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  return key.endsWith("_pct") ? (locale.startsWith("tr") ? `%${f.format(v)}` : `${f.format(v)}%`) : f.format(v);
}

/** runs that can be compared with `a`: same term and kind, not itself */
export function comparableWith(runs: readonly ScheduleRun[], a: ScheduleRun | undefined): ScheduleRun[] {
  if (!a) return [...runs];
  return runs.filter((r) => r.id !== a.id && r.term_id === a.term_id && r.kind === a.kind);
}

/** a sensible default pair: the published run of the kind as A (baseline) and the newest other run as B */
export function defaultPair(runs: readonly ScheduleRun[]): { a: number; b: number } | null {
  const byKey = new Map<string, ScheduleRun[]>();
  for (const r of runs) {
    const k = `${r.term_id}:${r.kind}`;
    byKey.set(k, [...(byKey.get(k) ?? []), r]);
  }
  for (const list of byKey.values()) {
    if (list.length < 2) continue;
    const sorted = [...list].sort((x, y) => y.id - x.id);
    const a = sorted.find((r) => r.is_active) ?? sorted[1]!;
    const b = sorted.find((r) => r.id !== a.id)!;
    return { a: a.id, b: b.id };
  }
  return null;
}
