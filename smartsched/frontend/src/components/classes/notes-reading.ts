/**
 * A-04 (academician persona, 2026-10-15): the request's free-text notes ("Derse Özel Açıklama") and what the
 * importer read from them. The importer (`app/importers/preference_rules.py`) turns every wish of the notes
 * column into a soft `FILE` rule on the request (`params.event_ids = [request id]`, `nl_text` = the wish's
 * wording, switched off until reviewed) and reports the wishes it could not read as `unparsed_preference`
 * items of `GET /runs/{id}/data-issues`. Without that report (no run yet, or it failed) a note that produced
 * no rule is flagged as unread as a whole.
 */
import type { Constraint } from "@/lib/api/schemas";
import { fold } from "@/components/timetable/model/filters";

export type NoteRuleState = "on" | "pending";
export interface NoteRule {
  id: number;
  text: string;
  kind: string;
  state: NoteRuleState;
}
export interface UnparsedWish {
  text: string;
  reason: string;
}
export interface NotesReading {
  notes: string;
  rules: NoteRule[];
  unparsed: UnparsedWish[];
  /** nothing was read from the note at all */
  unread: boolean;
}

const eventIds = (c: Constraint): number[] => {
  const v = c.params.event_ids;
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === "number") : [];
};

export function readNotes(requestId: number, notes: string | null | undefined, constraints: readonly Constraint[], unparsed: UnparsedWish[] | null): NotesReading | null {
  const text = (notes ?? "").trim();
  if (!text) return null;
  const hay = fold(text);
  const rules = constraints
    .filter((c) => c.source === "FILE" && c.nl_text && eventIds(c).includes(requestId) && hay.includes(fold(c.nl_text)))
    .map((c): NoteRule => ({ id: c.id, text: c.nl_text ?? "", kind: c.kind, state: c.enabled ? "on" : "pending" }));
  const mine = (unparsed ?? []).filter((u) => u.text && hay.includes(fold(u.text)));
  return { notes: text, rules, unparsed: mine, unread: rules.length === 0 && mine.length === 0 };
}

type IssueGroupLike = { code: string; items: { request_ids?: unknown; params?: Record<string, unknown> }[] };

/** This request's `unparsed_preference` items; `null` when the report is not available. */
export function unparsedFromIssues(groups: readonly IssueGroupLike[] | undefined, requestId: number): UnparsedWish[] | null {
  if (!groups) return null;
  return groups
    .filter((g) => g.code === "unparsed_preference")
    .flatMap((g) => g.items)
    .filter((i) => Array.isArray(i.request_ids) && (i.request_ids as unknown[]).includes(requestId))
    .map((i) => ({ text: String(i.params?.text ?? ""), reason: String(i.params?.reason ?? "") }));
}
