/**
 * Planner-facing run report (usability B2): the backend renders TR/EN text from `code` + `params`
 * (`diagnosis.text`); the fix options still arrive as English solver strings, so they are formatted here
 * from their structured params. Order: unplaced first, then rule clashes, then input data, then info;
 * identical texts are collapsed into one card with a count.
 */
import { tr } from "@/components/common/tr-suffix";
import type { Diagnosis } from "@/lib/api/schemas";
import type { Locale } from "@/lib/i18n";
import { PERIODS, dayName } from "@/lib/time";

export type Suggestion = Diagnosis["suggestions"][number];

/** "A204" → "A 204", "C501" → "C 501"; already spaced codes and names stay as they are. */
export function roomLabel(code: string): string {
  return code.replace(/^([A-Za-zÇĞİÖŞÜçğıöşü]+)\s?(\d)/u, "$1 $2");
}

/** "Perşembe 13:30–15:50" from a day (1 = Monday) and a period span. */
export function slotLabel(day: number | undefined, start: number | undefined, end: number | undefined, locale: Locale): string {
  const parts: string[] = [];
  if (day) parts.push(dayName(day, locale));
  const a = start ? PERIODS[start - 1]?.start : undefined;
  const b = end ? PERIODS[end - 1]?.end : undefined;
  if (a && b) parts.push(`${a}–${b}`);
  return parts.join(" ");
}

const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);

/** One fix option in the planner's language, or `null` when it has nothing to apply (manual advice). */
export function formatSuggestion(s: Suggestion, locale: Locale): string | null {
  const p = s.params;
  const room = str(p.room_code) ? roomLabel(String(p.room_code)) : undefined;
  const slot = slotLabel(num(p.day), num(p.start_period), num(p.end_period), locale);
  const holders = Array.isArray(p.holder_event_ids) ? p.holder_event_ids.length : 0;
  switch (s.action) {
    case "release_room":
      if (!room) break;
      return locale === "tr"
        ? `${tr(room, "acc")} ${slot ? `${slot} için ` : ""}boşalt${holders ? ` (oradaki ${holders} ders başka dersliğe alınır)` : ""}`
        : `Free ${room}${slot ? ` on ${slot}` : ""}${holders ? ` (its ${holders} ${holders === 1 ? "class moves" : "classes move"} elsewhere)` : ""}`;
    case "move":
      if (!room && !slot) break;
      return locale === "tr" ? `${slot ? `${slot} saatine` : "Başka saate"}${room ? `, ${tr(room, "dat")}` : ""} taşı` : `Move to ${slot || "another time"}${room ? ` in ${room}` : ""}`;
    case "split": {
      const n = num(p.max_rooms) ?? 2;
      return locale === "tr" ? `Grubu en fazla ${n} dersliğe böl` : `Split the group across up to ${n} rooms`;
    }
    case "unlock":
      return locale === "tr" ? "Kilitlerden birini kaldır, çözücü yeni derslik bulsun" : "Unlock one of them and let the solver find a room";
    case "relax":
    case "add_constraint":
      return s.applicable ? (locale === "tr" ? "Kuralı gevşet ve yeniden çöz" : "Relax the rule and solve again") : null;
    case "manual":
      return null;
  }
  return s.applicable ? s.text : null;
}

/** The backend's planner text in the UI language; never the raw solver message when a template exists. */
export function plannerText(d: Pick<Diagnosis, "text" | "message">, locale: Locale): string {
  const local = d.text ? (locale === "tr" ? d.text.tr : d.text.en) : "";
  if (local) return local;
  if (d.text?.en) return d.text.en;
  // last resort: strip internal ids ("(#783)") from the solver message
  return d.message.replace(/\s*\(#\d+\)/g, "").replace(/#\d+\s*/g, "");
}

export type ReportSection = "unplaced" | "rules" | "input" | "info";
export const SECTION_ORDER: ReportSection[] = ["unplaced", "rules", "input", "info"];

/** Codes that summarise the run (shown in the header, not as cards). */
export const SUMMARY_CODES = new Set(["partial", "unplaced_summary"]);

export function sectionOf(d: Pick<Diagnosis, "code" | "message" | "severity">): ReportSection {
  const code = d.code ?? "";
  if (code === "unplaced" || (!code && /cannot be placed|yerleşemedi/i.test(d.message))) return "unplaced";
  if (/locked_overlap|shared_room|locked_room_blocked|rule|pin|forbid/.test(code)) return "rules";
  if (/input_conflict|trusted_lock|outside_room_pool|board_vs_list|missing|capacity|data|week_room/.test(code)) return "input";
  return d.severity === "low" ? "info" : code ? "input" : "rules";
}

export interface CollapsedDiagnosis {
  d: Diagnosis;
  /** how many diagnoses had exactly this text */
  count: number;
  /** all collapsed indexes (the first one is applied) */
  indexes: number[];
}

/** Sections in report order, summaries dropped, identical texts collapsed (first occurrence kept). */
export function groupDiagnoses(list: Diagnosis[], locale: Locale): { section: ReportSection; codes: Map<string, CollapsedDiagnosis[]> }[] {
  const out = new Map<ReportSection, Map<string, CollapsedDiagnosis[]>>();
  const seen = new Map<string, CollapsedDiagnosis>();
  for (const d of list) {
    if (SUMMARY_CODES.has(d.code ?? "")) continue;
    const section = sectionOf(d);
    const code = d.code || "other";
    const key = `${section}|${code}|${plannerText(d, locale)}`;
    const dup = seen.get(key);
    if (dup) {
      dup.count += 1;
      dup.indexes.push(d.index ?? Number(d.id));
      continue;
    }
    const row: CollapsedDiagnosis = { d, count: 1, indexes: [d.index ?? Number(d.id)] };
    seen.set(key, row);
    const byCode = out.get(section) ?? new Map<string, CollapsedDiagnosis[]>();
    byCode.set(code, [...(byCode.get(code) ?? []), row]);
    out.set(section, byCode);
  }
  return SECTION_ORDER.filter((s) => out.has(s)).map((section) => ({ section, codes: out.get(section) ?? new Map() }));
}
