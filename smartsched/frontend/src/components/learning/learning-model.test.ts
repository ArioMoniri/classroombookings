import { describe, expect, it } from "vitest";
import type { ResetRow, Suggestion } from "@/lib/api/learning";
import { evidenceText, levelCode, meterSteps, reasonOk, resetStatus, splitSuggestions, trOfTerms, typedConfirmOk } from "./learning-model";

export const suggestion = (over: Partial<Suggestion> = {}): Suggestion => ({
  id: 1,
  scope: null,
  persistent_accept: null,
  term_id: 2,
  subject: { type: "instructor", id: 3, label: "Dr. Öğr. Üyesi E. Y." },
  attribute: "room",
  value: "12",
  value_label: { tr: "A 206", en: "A 206" },
  claim: { tr: "Dr. Öğr. Üyesi E. Y. için A 206 tercih edilsin mi?", en: "Prefer A 206 for Dr. Öğr. Üyesi E. Y.?" },
  explanation: { tr: "Dr. Öğr. Üyesi E. Y. 2 dönemdir A 206'da: 3/4 kayıt (2026-BAHAR: 2/2, 2026-GÜZ: 1/2).", en: "…" },
  if_accepted: { tr: "Kabul ederseniz yumuşak bir tercih (ağırlık 5) eklenir; kesin kural değildir.", en: "If accepted: adds a soft preference (weight 5), not a hard rule." },
  proposal: { kind: "room_preference", params: { room_ids: [12], event_ids: [545] }, hardness: "soft", weight: 5 },
  support: { rows: 3, total: 4, seen_terms: 2 },
  score: 2.5,
  confidence: 0.66,
  level: { code: "medium", tr: "Orta", en: "Medium" },
  cross_season: false,
  evidence: { terms: [{ term_id: 1, code: "2026-BAHAR", pos: 2, total: 2 }, { term_id: 2, code: "2026-GÜZ", pos: 1, total: 2 }], request_ids: [545], excluded: [] },
  impact: { request_ids: [545], covered_request_ids: [] },
  state: "open",
  hidden_reason: null,
  snoozed_until: null,
  snooze_mode: null,
  constraint_id: null,
  decided_at: null,
  decided_by: null,
  ...over,
});

describe("learning model", () => {
  it("turns confidence into a 3-step meter and a word (Yüksek ≥ 0.80, Orta ≥ 0.60, Düşük ≥ 0.50)", () => {
    expect([meterSteps(0.85), meterSteps(0.8), meterSteps(0.7), meterSteps(0.55), meterSteps(0.3)]).toEqual([3, 3, 2, 1, 0]);
    expect(levelCode({ level: null, confidence: 0.81 })).toBe("high");
    expect(levelCode(suggestion())).toBe("medium");
  });

  it("writes the evidence count with the Turkish possessive locative", () => {
    expect(trOfTerms(2, 2)).toBe("2 dönemin 2'sinde");
    expect(trOfTerms(3, 4)).toBe("4 dönemin 3'ünde");
    expect(trOfTerms(4, 4)).toBe("4 dönemin 4'ünde");
    expect(trOfTerms(1, 3)).toBe("3 dönemin 1'inde");
    expect(trOfTerms(6, 8)).toBe("8 dönemin 6'sında");
    expect(trOfTerms(10, 12)).toBe("12 dönemin 10'unda");
    expect(evidenceText(suggestion(), "tr")).toBe("2 dönemin 2'sinde");
    expect(evidenceText(suggestion(), "en")).toBe("in 2 of 2 terms");
    expect(evidenceText(suggestion({ evidence: { terms: [{ term_id: 1, code: "2026-BAHAR", pos: 3, total: 3 }] }, support: { rows: 3, total: 3, seen_terms: 1 } }), "tr")).toBe("tek dönemde 3 kez");
  });

  it("splits Bekleyen / Geçmiş and never shows hidden ones", () => {
    const list = [suggestion({ id: 1 }), suggestion({ id: 2, state: "accepted" }), suggestion({ id: 3, state: "hidden" }), suggestion({ id: 4, state: "snoozed" })];
    const { pending, history } = splitSuggestions(list);
    expect(pending.map((s) => s.id)).toEqual([1]);
    expect(history.map((s) => s.id)).toEqual([2, 4]);
  });

  it("accepts SIFIRLA or RESET, Turkish-aware, in either locale", () => {
    expect(typedConfirmOk("SIFIRLA")).toBe(true);
    expect(typedConfirmOk("sıfırla")).toBe(true);
    expect(typedConfirmOk(" sifirla ")).toBe(true);
    expect(typedConfirmOk("reset")).toBe(true);
    expect(typedConfirmOk("SIFIRLAMA")).toBe(false);
    expect(typedConfirmOk("")).toBe(false);
    expect(reasonOk("ab")).toBe(false);
    expect(reasonOk("görev değişikliği")).toBe(true);
  });

  it("names the state of a reset row (30-day undo, purge, KVKK erasure)", () => {
    const r = (over: Partial<ResetRow>): ResetRow => ({ id: 1, kind: "RESET", scope: "person", value: "3", reason: "x", actor_id: 1, created_at: "2026-10-15T15:02:00", undo_until: "2026-11-14T15:02:00", days_left: 27, undoable: true, undone_at: null, purged_at: null, counts: {}, ...over });
    expect(resetStatus(r({}))).toBe("undoable");
    expect(resetStatus(r({ undoable: false, undone_at: "2026-10-16" }))).toBe("undone");
    expect(resetStatus(r({ undoable: false, purged_at: "2026-11-14" }))).toBe("purged");
    expect(resetStatus(r({ kind: "ERASURE", undoable: false, purged_at: "2026-10-15" }))).toBe("erased");
    expect(resetStatus(r({ undoable: false }))).toBe("expired");
  });
});
