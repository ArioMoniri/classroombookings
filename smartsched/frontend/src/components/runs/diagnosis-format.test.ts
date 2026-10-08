import { describe, expect, it } from "vitest";
import * as adapt from "@/lib/api/adapters";
import { ScheduleRun } from "@/lib/api/schemas";
import { formatSuggestion, groupDiagnoses, plannerText, roomLabel, slotLabel } from "./diagnosis-format";

// trimmed from a real FEASIBLE_PARTIAL run (Bahar week 3, 660/683) on the SQLite backend, 2026-10-08
const raw = [
  { code: "partial", severity: "warning", message: "best effort: 660 of 683 events placed", event_ids: [1], constraint_kinds: [], suggestions: [], text: { tr: "660/683 ders yerleşti", en: "660 of 683 classes placed" } },
  { code: "input_conflict", severity: "warning", message: "input conflict: MAT 112 §1 (#1) and MAT 102 §1 (#786)", event_ids: [1, 786], constraint_kinds: ["no_instructor_overlap"], suggestions: [{ id: "s0", index: 0, text: "move MAT 112 §1 or MAT 102 §1 to another period", action: "manual", applicable: false, params: {} }], text: { tr: "MAT 112 §1 ve MAT 102 §1 sabit saatlerde çakışıyor.", en: "MAT 112 §1 and MAT 102 §1 overlap at their fixed times." } },
  { code: "input_conflict", severity: "warning", message: "input conflict: MAT 112 §1 (#1) and MAT 102 §1 (#786)", event_ids: [1, 786], constraint_kinds: ["no_cohort_overlap"], suggestions: [], text: { tr: "MAT 112 §1 ve MAT 102 §1 sabit saatlerde çakışıyor.", en: "MAT 112 §1 and MAT 102 §1 overlap at their fixed times." } },
  {
    code: "unplaced",
    severity: "error",
    message: "MAT 112 §1 (#1) (size 180, 3 period(s), day 4 P7-P9) cannot be placed",
    event_ids: [1],
    constraint_kinds: ["no_room_overlap"],
    suggestions: [
      { id: "s0", index: 0, text: "release A204 (156) at day 4 P7-P9 held by ING 202 (#783), HEM 236 (#1020)", action: "release_room", applicable: true, params: { event_id: 1, room_code: "A204", day: 4, start_period: 7, end_period: 9, holder_event_ids: [783, 1020] } },
      { id: "s1", index: 1, text: "allow splitting across rooms (max_rooms > 1)", action: "split", applicable: false, params: { event_ids: [1], max_rooms: 3 } },
      { id: "s2", index: 2, text: "alternative periods on the same day: P11-P13 in A204", action: "move", applicable: true, params: { event_id: 1, room_code: "A204", day: 4, start_period: 11, end_period: 13 } },
    ],
    text: { tr: "MAT 112 §1 (180 öğrenci, Perşembe 13:30–15:50) yerleşemedi: kapasite sorunu.", en: "MAT 112 §1 (180 students, Thursday 13:30–15:50) could not be placed: a capacity problem." },
  },
  { code: "locked_overlap", severity: "error", message: "locked assignments overlap: ING 302 (#530) and FZT 132 (#620) both hold A106", event_ids: [530, 620], constraint_kinds: [], suggestions: [{ id: "s0", index: 0, text: "unlock ING 302 or FZT 132", action: "unlock", applicable: true, params: { event_ids: [530, 620] } }], text: { tr: "ING 302 ve FZT 132 aynı dersliğe (A106) kilitli.", en: "ING 302 and FZT 132 are both locked to A106." } },
];
const base = { id: 5, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, status: "FEASIBLE_PARTIAL", hard_score: 100, soft_score: 82, params: {}, objective_value: null, parent_run_id: null, prompt_text: null, created_at: "2026-10-08T10:00:00Z", finished_at: "2026-10-08T10:00:44Z", stats: { placed: 660, events_total: 683 } };
const run = ScheduleRun.parse(adapt.run({ ...base, diagnosis: raw }));

describe("planner-facing run report", () => {
  it("formats rooms and slots like the planner's board", () => {
    expect(roomLabel("A204")).toBe("A 204");
    expect(roomLabel("C 501")).toBe("C 501");
    expect(slotLabel(4, 7, 9, "tr")).toBe("Perşembe 13:30–15:50");
    expect(slotLabel(4, 7, 9, "en")).toBe("Thursday 13:30–15:50");
  });

  it("writes fix options from structured params, in Turkish with suffix harmony", () => {
    const [release, split, move] = run.diagnosis.find((d) => d.code === "unplaced")?.suggestions ?? [];
    expect(release && formatSuggestion(release, "tr")).toBe("A 204'ü Perşembe 13:30–15:50 için boşalt (oradaki 2 ders başka dersliğe alınır)");
    expect(release && formatSuggestion(release, "en")).toBe("Free A 204 on Thursday 13:30–15:50 (its 2 classes move elsewhere)");
    expect(move && formatSuggestion(move, "tr")).toBe("Perşembe 16:50–18:40 saatine, A 204'e taşı");
    expect(split && formatSuggestion(split, "tr")).toBe("Grubu en fazla 3 dersliğe böl");
    expect(formatSuggestion({ id: "s0", text: "x", action: "manual", applicable: false, params: {} }, "tr")).toBeNull();
  });

  it("puts unplaced classes first, drops summaries and collapses duplicate texts", () => {
    const groups = groupDiagnoses(run.diagnosis, "tr");
    expect(groups.map((g) => g.section)).toEqual(["unplaced", "rules", "input"]);
    const input = groups[2]?.codes.get("input_conflict") ?? [];
    expect(input).toHaveLength(1);
    expect(input[0]?.count).toBe(2);
    expect(plannerText(run.diagnosis[3]!, "tr")).toContain("yerleşemedi");
  });

  it("never shows raw ids when there is no template", () => {
    expect(plannerText({ message: "ING 302 (#530) and FZT 132 (#620) clash", text: undefined }, "tr")).toBe("ING 302 and FZT 132 clash");
  });
});
