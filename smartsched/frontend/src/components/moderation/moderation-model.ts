/**
 * Pure view logic of the moderation tab (docs/design/v2/phase19-moderation.md, phase19-priority-policy.md):
 * verdict → glyph + word, priority tiers, requested → assigned sentences, quick filters, the re-solve diff
 * groups and the "staged changes" list kept until the next re-solve. No React, no fetching: unit-tested.
 */
import type { DiffOut, Matching, PersonRow, Place, Preference, Reason, TierCode, Verdict } from "@/lib/api/moderation";
import type { StatusKind } from "@/components/common/status-badge";
import { fold } from "@/components/timetable/model/filters";
import { dayName, periodRangeLabel } from "@/lib/time";

export type Lang = "tr" | "en";

/* ------------------------------------------------------------------ tabs */

export const TABS = ["classes", "people", "requests", "preferences", "matchings"] as const;
export type ModerationTab = (typeof TABS)[number];
export function parseTab(v: string | null | undefined): ModerationTab {
  return (TABS as readonly string[]).includes(v ?? "") ? (v as ModerationTab) : "people";
}

/* ------------------------------------------------------------------ verdicts (G4: glyph + word) */

/** the status tone of a verdict; `null` = not judged (plain label-2 text, "(planlayıcı)" suffix when no run) */
export function verdictKind(v: Verdict): StatusKind | null {
  switch (v) {
    case "satisfied":
      return "feasible";
    case "partial":
    case "not_as_requested":
      return "warning";
    case "unplaced":
      return "infeasible";
    default:
      return null;
  }
}

export const UNSATISFIED: readonly Verdict[] = ["partial", "not_as_requested", "unplaced"];
export const isUnsatisfied = (v: Verdict) => UNSATISFIED.includes(v);

/* ------------------------------------------------------------------ priority (three tiers, never colour only) */

/** the backend stores an int (high 1 / normal 0 / low -1; any positive int is "high") */
export function tierOf(value: number | null | undefined): TierCode {
  if (value === null || value === undefined || value === 0) return "normal";
  return value > 0 ? "high" : "low";
}
export const TIERS: readonly TierCode[] = ["high", "normal", "low"];

/** `p 1/2/3` sets Yüksek / Normal / Düşük (priority-policy spec §5.3) */
export function tierForKey(key: string): TierCode | null {
  return key === "1" ? "high" : key === "2" ? "normal" : key === "3" ? "low" : null;
}

/** Yüksek count above 10 % of the requests: priority inflation warning (spec §0, P6) */
export function priorityDistribution(values: readonly number[]): { high: number; normal: number; low: number; highShare: number; overLimit: boolean } {
  let high = 0;
  let low = 0;
  for (const v of values) {
    const t = tierOf(v);
    if (t === "high") high++;
    else if (t === "low") low++;
  }
  const normal = values.length - high - low;
  const highShare = values.length ? high / values.length : 0;
  return { high, normal, low, highShare, overLimit: highShare > 0.1 };
}

/* ------------------------------------------------------------------ text */

export function placeText(p: Pick<Place, "day" | "start_period" | "end_period" | "rooms" | "time"> | null | undefined, locale: Lang): string {
  if (!p) return "—";
  const day = dayName(p.day, locale, "short");
  const span = `P${p.start_period}${p.end_period !== p.start_period ? `–P${p.end_period}` : ""}`;
  const rooms = p.rooms.length ? p.rooms.join(" + ") : locale === "tr" ? "oda yok" : "no room";
  return `${day} ${span} ${p.time ?? periodRangeLabel(p.start_period, p.end_period)} · ${rooms}`;
}

export function requestedText(m: Pick<Matching, "requested" | "definitive">, locale: Lang): string {
  const r = m.requested;
  const days = r.day ? [r.day] : r.days;
  const when = days.length && r.start_period !== null ? `${days.map((d) => dayName(d, locale, "short")).join("/")} P${r.start_period}${r.end_period !== null && r.end_period !== r.start_period ? `–P${r.end_period}` : ""}` : locale === "tr" ? "saat yok" : "no time";
  const where = r.rooms.length ? r.rooms.join(" / ") : r.room_text ?? (r.building ? `${r.building} ${locale === "tr" ? "blok" : "block"}` : r.tags.length ? r.tags.join(", ") : locale === "tr" ? "oda fark etmez" : "any room");
  return `${when} · ${where}`;
}

/** the accessible sentence of a matching ("İstenen Salı 11:00, A 306 ve C 602; atanan yok"), spec §11 */
export function matchingSentence(m: Matching, locale: Lang): string {
  const asked = requestedText(m, locale);
  if (locale === "tr") return `İstenen ${asked}; ${m.assigned ? `atanan ${placeText(m.assigned, locale)}` : "atanan yok"}`;
  return `Requested ${asked}; ${m.assigned ? `assigned ${placeText(m.assigned, locale)}` : "nothing assigned"}`;
}

export function pairText(p: { tr: string; en: string } | null | undefined, lang: Lang): string {
  if (!p) return "";
  return (lang === "tr" ? p.tr : p.en) || p.tr || p.en;
}

export function reasonText(r: Reason | null | undefined, lang: Lang): string {
  return r ? pairText(r.text, lang) : "";
}

/* ------------------------------------------------------------------ quick filters and search */

export type MatchChip = "unsatisfied" | "partial" | "satisfied" | "all";
export const MATCH_CHIPS: readonly MatchChip[] = ["unsatisfied", "partial", "satisfied", "all"];

export function chipCount(counts: Record<string, number>, chip: MatchChip): number {
  switch (chip) {
    case "unsatisfied":
      return UNSATISFIED.reduce((n, v) => n + (counts[v] ?? 0), 0);
    case "partial":
      return (counts.partial ?? 0) + (counts.not_as_requested ?? 0);
    case "satisfied":
      return counts.satisfied ?? 0;
    default:
      return Object.values(counts).reduce((a, b) => a + b, 0);
  }
}

function chipAllows(chip: MatchChip, v: Verdict): boolean {
  switch (chip) {
    case "unsatisfied":
      return isUnsatisfied(v);
    case "partial":
      return v === "partial" || v === "not_as_requested";
    case "satisfied":
      return v === "satisfied";
    default:
      return true;
  }
}

/** Turkish-aware search over course, name, section, program and people (İ/ı casefold) */
export function matchesQuery(m: Matching, q: string): boolean {
  const words = q.trim().split(/\s+/).map(fold).filter(Boolean);
  if (!words.length) return true;
  const hay = fold([m.label, m.course_code, m.course_name, m.program, m.faculty, ...m.instructors.map((i) => i.name), ...(m.assigned?.rooms ?? []), ...m.requested.rooms].filter(Boolean).join(" "));
  return words.every((w) => hay.includes(w));
}

export function filterMatchings(items: readonly Matching[], chip: MatchChip, q: string): Matching[] {
  return items.filter((m) => chipAllows(chip, m.verdict) && matchesQuery(m, q));
}

/** Eşleşmeler order: not satisfied first (unplaced, not as requested, partial), then the rest, by label */
export function sortMatchings(items: readonly Matching[]): Matching[] {
  const rank: Record<string, number> = { unplaced: 0, not_as_requested: 1, partial: 2, satisfied: 3, pending: 4, not_evaluated: 5 };
  const collator = new Intl.Collator("tr", { numeric: true, sensitivity: "base" });
  return [...items].sort((a, b) => (rank[a.verdict] ?? 9) - (rank[b.verdict] ?? 9) || collator.compare(a.label, b.label));
}

/** Talepler order: requests without a parsed time or room (review needed) first */
export function sortRequests(items: readonly Matching[]): Matching[] {
  const collator = new Intl.Collator("tr", { numeric: true, sensitivity: "base" });
  const review = (m: Matching) => (m.requested.status === "NEEDS_REVIEW" ? 0 : m.requested.status === "NEW" ? 1 : 2);
  return [...items].sort((a, b) => review(a) - review(b) || collator.compare(a.label, b.label));
}

export type PeopleChip = "unmet" | "streak" | "all";
export function unmetOf(p: PersonRow): number {
  return UNSATISFIED.reduce((n, v) => n + (p.counts[v] ?? 0), 0);
}
export function filterPeople(items: readonly PersonRow[], chip: PeopleChip, q: string): PersonRow[] {
  const needle = fold(q.trim());
  return items.filter((p) => (chip === "unmet" ? unmetOf(p) > 0 : chip === "streak" ? p.badge !== null : true) && (!needle || fold(`${p.title ?? ""} ${p.name} ${p.unit ?? ""}`).includes(needle)));
}

/* ------------------------------------------------------------------ preferences (Tercihler) */

export type PrefSource = "file" | "admin" | "ai" | "learned" | "other";
export function prefSource(p: Preference): PrefSource {
  switch (p.source) {
    case "UPLOAD":
    case "FILE":
      return "file";
    case "ADMIN":
      return "admin";
    case "AI":
      return "ai";
    case "LEARNED":
      return "learned";
    default:
      return "other";
  }
}
/** soft preferences of the term (term rules; run-only drafts are not the term's preferences) */
export function termPreferences(rows: readonly Preference[]): Preference[] {
  return rows.filter((r) => r.hardness === "soft" && r.term_id !== null && r.source !== "BUILTIN");
}

/* ------------------------------------------------------------------ re-solve diff */

export const DIFF_GROUPS = ["moved", "newly_placed", "unplaceable", "unchanged"] as const;
export type DiffGroup = (typeof DIFF_GROUPS)[number];

export interface DiffRow {
  group: DiffGroup;
  requestId: number;
  label: string;
  before: string;
  after: string;
  reason: string;
  inScope: boolean;
  people: number[];
  from: Place | null;
  to: Place | null;
}

export function diffRows(d: DiffOut, locale: Lang): Record<Exclude<DiffGroup, "unchanged">, DiffRow[]> {
  const moved = d.moved.map<DiffRow>((m) => ({ group: "moved", requestId: m.request_id, label: m.label, before: placeText(m.from, locale), after: placeText(m.to, locale), reason: m.causes.map((c) => pairText(c.text, locale)).join(" · "), inScope: m.in_scope, people: m.instructor_ids, from: m.from, to: m.to }));
  const newly = d.newly_placed.map<DiffRow>((m) => ({ group: "newly_placed", requestId: m.request_id, label: m.label, before: "—", after: placeText(m.to, locale), reason: m.in_scope ? (locale === "tr" ? "Değiştirilen talep" : "Edited request") : "", inScope: m.in_scope, people: m.instructor_ids, from: null, to: m.to }));
  const unplaceable = d.unplaceable.map<DiffRow>((m) => ({ group: "unplaceable", requestId: m.request_id, label: m.label, before: m.from ? placeText(m.from, locale) : "—", after: "—", reason: reasonText(m.reason, locale), inScope: m.in_scope, people: m.instructor_ids, from: m.from ?? null, to: null }));
  return { moved, newly_placed: newly, unplaceable };
}

export function diffCount(d: DiffOut, g: DiffGroup): number {
  const c = d.counts;
  if (!c) return 0;
  return g === "moved" ? c.moved : g === "newly_placed" ? c.newly_placed : g === "unplaceable" ? c.unplaceable : c.unchanged;
}

/** motion §3.9: only moved chips in the viewport travel, and never more than 12 at once */
export const MAX_ANIMATED_MOVES = 12;
export function animatedMoves<T>(moved: readonly T[], inView: (m: T) => boolean = () => true): Set<T> {
  const out = new Set<T>();
  for (const m of moved) {
    if (out.size >= MAX_ANIMATED_MOVES) break;
    if (inView(m)) out.add(m);
  }
  return out;
}

/** "Onayla ve yayınla" is enabled only on a ready, finished, unpublished preview (spec M7) */
export function canPublish(d: DiffOut | undefined): boolean {
  return !!d && d.ready && !d.is_active && ["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"].includes(d.status);
}

/** a preview run accepts pin / prefer / unlock edits (a draft child, never the published run) */
export function isDraftChild(d: DiffOut | undefined): boolean {
  return !!d && d.ready && !d.is_active;
}

/* ------------------------------------------------------------------ staged changes (until the next re-solve) */

/**
 * The requests edited since the last re-solve (priority edits here; the backend has no
 * `changes-since-publish` read yet, P19-M-07). Kept per term in localStorage, newest first, de-duplicated.
 */
export interface StagedChange {
  requestIds: number[];
  label: string;
  at: string;
}
export function addStaged(list: readonly StagedChange[], change: StagedChange): StagedChange[] {
  return [change, ...list].slice(0, 200);
}
export function stagedRequestIds(list: readonly StagedChange[]): number[] {
  return [...new Set(list.flatMap((c) => c.requestIds))].sort((a, b) => a - b);
}
