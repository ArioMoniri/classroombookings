/** The /timetable run picker's option text: short enough for the sidebar (ROADMAP UI polish), full in `title`; a run's own label leads. */
type RunLike = { id: number; kind: string; status: string; horizon: string; horizon_params: { weeks: readonly number[] }; label?: string | null };
type T = (key: string, vars?: Record<string, string | number>) => string;

/** [1,2,3,5,7,8] → "1–3, 5, 7–8" */
export function weekRanges(weeks: readonly number[]): string {
  const s = [...new Set(weeks)].sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < s.length; ) {
    let j = i;
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++;
    out.push(j > i ? `${s[i]}–${s[j]}` : String(s[i]));
    i = j + 1;
  }
  return out.join(", ");
}

export function runOptionLabel<K extends string>(r: RunLike, t: (key: K, vars?: Record<string, string | number>) => string, mixedKinds: boolean): { short: string; full: string } {
  const tt = t as unknown as T;
  const kind = r.kind === "EXAM" ? tt("classes.kind.exams") : tt("classes.kind.meetings");
  const status = tt(`runs.status.${r.status}`);
  const weeks = r.horizon === "WEEK" && r.horizon_params.weeks.length ? tt("calendar.nav.weekShort", { n: weekRanges(r.horizon_params.weeks) }) : "";
  const parts = (withKind: boolean) => [`#${r.id}`, withKind ? kind : "", status, weeks].filter(Boolean).join(" · ");
  // a named run reads by its name in the narrow sidebar ("#4 · Bahar 3. hafta (A)"); the tooltip keeps everything
  const label = r.label?.trim();
  if (label) return { short: [`#${r.id}`, label, mixedKinds ? kind : ""].filter(Boolean).join(" · "), full: [`#${r.id}`, label, kind, status, weeks].filter(Boolean).join(" · ") };
  return { short: parts(mixedKinds), full: parts(true) };
}
