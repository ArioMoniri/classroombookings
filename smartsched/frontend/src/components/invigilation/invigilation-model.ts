/**
 * Pure helpers of the Gözetmen ataması screens: grouping the diagnoses (errors first, INFEASIBLE never hidden,
 * shortages staffed by hand afterwards last and marked resolved), the progress of a running plan (the backend's own
 * phase and percentage; while solving, the elapsed time against the limit), the posts by date with filters, the
 * unavailability rows of a pool member and the plan's status tone.
 */
import type { Diagnosis, PlanBrief, PlanParams, Post, ProgressPhase, Unavailable } from "@/lib/api/invigilation";
import { changedParams, paramsFrom, PLAN_DEFAULTS, PROGRESS_PHASES } from "@/lib/api/invigilation";
import type { ScheduleRun } from "@/lib/api/schemas";

export type Tone = "feasible" | "warning" | "infeasible" | "neutral" | "tint";

/** A finished plan with nothing to assign (round-1 R1-M-11): 0 room-sessions or 0 required duties. */
export function planIsEmpty(p: Pick<PlanBrief, "status" | "counts"> & { empty?: boolean }): boolean {
  if (p.empty) return true;
  if (p.status === "QUEUED" || p.status === "RUNNING" || p.status === "FAILED" || p.status === "ERROR") return false;
  return p.counts.posts === 0 || p.counts.required === 0;
}

/** The status word key: an empty plan is "Boş plan", never "En iyi". */
export function planStatusKey(p: Pick<PlanBrief, "status" | "counts"> & { empty?: boolean }): string {
  return planIsEmpty(p) ? "invigilation.status.EMPTY" : `invigilation.status.${p.status}`;
}

export function planTone(p: Pick<PlanBrief, "status" | "counts"> & { empty?: boolean }): Tone {
  if (planIsEmpty(p)) return "warning";
  if (p.status === "QUEUED") return "neutral";
  if (p.status === "RUNNING") return "tint";
  if (p.status === "OPTIMAL" || p.status === "FEASIBLE") return (p.counts.missing ?? 0) > 0 ? "warning" : "feasible";
  return "infeasible";
}

/* ------------------------------------------------------------------ pool (round-1 T-R1-42) */

/** the plan found nobody to assign: the backend's `pool_empty` error with its Turkish / English reason */
export function poolEmptyDiag(list: readonly Diagnosis[] | undefined): Diagnosis | undefined {
  return list?.find((d) => d.code === "pool_empty" && d.severity === "error");
}

/** the one-tap fix of an empty pool: the plan's own parameters with the pool widened to every instructor */
export function allInstructorsParams(parent: PlanParams | null | undefined): PlanParams {
  return { ...changedParams(paramsFrom(parent)), instructor_pool: "all" };
}

/**
 * An imported board offered as an exam run (grid import: `params.source` GRID_IMPORT, no solver stats, no prompt):
 * its rows carry no exam link, so an invigilation plan on it has no room session to staff (R1-S-14). Shown with
 * "sınav bağlantısı yok" and never picked by default while a solved exam run exists.
 */
export function isBoardRun(r: Pick<ScheduleRun, "params" | "label"> & { stats?: ScheduleRun["stats"]; prompt_text?: string | null; diagnosis?: unknown[] }): boolean {
  const src = (r.params as { source?: unknown } | undefined)?.source;
  if (src === "GRID_IMPORT" || src === "COUNCIL_BASELINE") return true;
  if (typeof src === "string") return false;
  return r.stats !== undefined && r.stats.solver === undefined && r.stats.events === undefined && !r.prompt_text && !(r.diagnosis?.length ?? 0) && /^grid import/i.test(r.label ?? "");
}

export interface DiagGroup {
  code: string;
  severity: Diagnosis["severity"];
  /** every item of the group is `resolved` (its posts were staffed by hand after the solve) */
  resolved: boolean;
  items: Diagnosis[];
  /** posts named by the group's items, de-duplicated */
  posts: number;
}

const SEV = { error: 0, warning: 1, info: 2 } as const;

/**
 * One group per code (open items) plus one per code of the resolved items; open errors first, then by size,
 * resolved groups last. Every item is kept (the list pages them, it never drops one).
 */
export function groupDiagnoses(list: readonly Diagnosis[]): DiagGroup[] {
  const m = new Map<string, DiagGroup>();
  for (const d of list) {
    const resolved = d.resolved === true;
    const key = `${resolved ? "resolved" : "open"}:${d.severity}:${d.code}`;
    const g = m.get(key) ?? { code: d.code, severity: d.severity, resolved, items: [], posts: 0 };
    g.items.push(d);
    m.set(key, g);
  }
  for (const g of m.values()) g.posts = new Set(g.items.flatMap((d) => d.post_keys ?? [])).size;
  return [...m.values()].sort((a, b) => Number(a.resolved) - Number(b.resolved) || SEV[a.severity] - SEV[b.severity] || b.items.length - a.items.length || a.code.localeCompare(b.code));
}

/** the header counts: open errors, open warnings / info, resolved */
export function diagCounts(list: readonly Diagnosis[]): { errors: number; others: number; resolved: number } {
  let errors = 0;
  let others = 0;
  let resolved = 0;
  for (const d of list) {
    if (d.resolved === true) resolved += 1;
    else if (d.severity === "error") errors += 1;
    else others += 1;
  }
  return { errors, others, resolved };
}

/* ------------------------------------------------------------------ progress */

/** a phase the messages name (`invigilation.phase.*`); anything else is shown as sent */
export const knownPhase = (p: string): p is ProgressPhase => (PROGRESS_PHASES as readonly string[]).includes(p);

export interface ProgressView {
  /** the backend's phase (`queued` / `running` when the job has not reported yet) */
  phase: string;
  /** the backend's percentage, 0-100; null when it sent none (never made up) */
  pct: number | null;
  /** CP-SAT runs: the percentage stays at 30, the elapsed time against the limit is what moves */
  solving: boolean;
  limit: number;
  /** seconds since the plan was created, clamped to the limit for the meter; null without a start time */
  elapsed: number | null;
  meter: number | null;
}

export function progressView(p: Pick<PlanBrief, "status" | "progress" | "params">, elapsed: number | null): ProgressView {
  const phase = p.progress?.phase || (p.status === "QUEUED" ? "queued" : p.status === "RUNNING" ? "running" : "done");
  const raw = p.progress?.pct;
  const pct = typeof raw === "number" && Number.isFinite(raw) ? Math.min(100, Math.max(0, Math.round(raw))) : null;
  const limitRaw = Number(p.params?.time_limit_s ?? PLAN_DEFAULTS.time_limit_s);
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : PLAN_DEFAULTS.time_limit_s;
  const solving = phase === "solving";
  return { phase, pct, solving, limit, elapsed, meter: solving && elapsed !== null ? Math.min(limit, Math.max(0, elapsed)) : null };
}

/** suggestion texts across a group, counted (e.g. "Add 2 people free at that time" × 312) */
export function suggestionSummary(items: readonly Diagnosis[], lang: "tr" | "en"): { text: string; count: number; people: number }[] {
  const m = new Map<string, { text: string; count: number; people: number }>();
  for (const d of items)
    for (const s of d.suggestions ?? []) {
      const e = m.get(s.code) ?? { text: s.text[lang] || s.text.tr, count: 0, people: 0 };
      e.count += 1;
      e.people += typeof s.count === "number" ? s.count : 0;
      m.set(s.code, e);
    }
  return [...m.values()].sort((a, b) => b.count - a.count);
}

export function postDates(posts: readonly Post[]): string[] {
  return [...new Set(posts.map((p) => p.date))].sort();
}

const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i");

export interface PostFilter {
  date: string | "all";
  query: string;
  onlyMissing: boolean;
}

/** the posts of one date (or all), matching room / building / exam / person text, optionally only under-staffed */
export function filterPosts(posts: readonly Post[], f: PostFilter): Post[] {
  const q = fold(f.query.trim());
  return posts
    .filter((p) => f.date === "all" || p.date === f.date)
    .filter((p) => !f.onlyMissing || p.missing > 0)
    .filter((p) => {
      if (!q) return true;
      const hay = [p.room, p.building ?? "", p.time, ...p.exams.map((e) => `${e.label} ${e.instructor_text ?? ""}`), ...p.assigned.map((d) => d.person_name)].join(" ");
      return fold(hay).includes(q);
    })
    .sort((a, b) => a.date.localeCompare(b.date) || a.start_period - b.start_period || a.room.localeCompare(b.room, "tr", { numeric: true }));
}

/** posts grouped by start time within a date (one heading per session) */
export function bySession(posts: readonly Post[]): { key: string; time: string; date: string; posts: Post[] }[] {
  const m = new Map<string, { key: string; time: string; date: string; posts: Post[] }>();
  for (const p of posts) {
    const k = `${p.date}|${p.start_period}-${p.end_period}`;
    const e = m.get(k) ?? { key: k, time: p.time, date: p.date, posts: [] };
    e.posts.push(p);
    m.set(k, e);
  }
  return [...m.values()];
}

/** the editable rows of an unavailability list: a date or a weekday, the whole day or a period range */
export interface UnavailRow {
  id: string;
  mode: "date" | "day";
  date: string;
  day: number;
  whole: boolean;
  start: number;
  end: number;
  note: string;
}

let seq = 0;
export const newRow = (): UnavailRow => ({ id: `u${++seq}`, mode: "date", date: "", day: 1, whole: true, start: 1, end: 18, note: "" });

export function toRows(list: readonly Unavailable[] | null | undefined): UnavailRow[] {
  return (list ?? []).map((u) => ({
    id: `u${++seq}`,
    mode: u.date ? "date" : "day",
    date: u.date ?? "",
    day: u.day ?? 1,
    whole: u.start_period === undefined || u.start_period === null,
    start: u.start_period ?? 1,
    end: u.end_period ?? 18,
    note: u.note ?? "",
  }));
}

export type RowProblem = "date" | "range" | null;

export function rowProblem(r: UnavailRow): RowProblem {
  if (r.mode === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(r.date)) return "date";
  if (!r.whole && !(r.start >= 1 && r.start <= r.end && r.end <= 18)) return "range";
  return null;
}

/** rows → the API body (backend _check_unavailable: a date or a day; both periods or neither) */
export function fromRows(rows: readonly UnavailRow[]): Unavailable[] {
  return rows.map((r) => {
    const out: Unavailable = r.mode === "date" ? { date: r.date } : { day: r.day };
    if (!r.whole) {
      out.start_period = r.start;
      out.end_period = r.end;
    }
    if (r.note.trim()) out.note = r.note.trim();
    return out;
  });
}

/** a post key's readable parts: "2026-06-01|6|1-2" → date, room id, periods */
export function parsePostKey(key: string): { date: string; roomId: number; start: number; end: number } | null {
  const m = /^(\d{4}-\d{2}-\d{2})\|(\d+)\|(\d+)-(\d+)$/.exec(key);
  return m ? { date: m[1]!, roomId: Number(m[2]), start: Number(m[3]), end: Number(m[4]) } : null;
}
