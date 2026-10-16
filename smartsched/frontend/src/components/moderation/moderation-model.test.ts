import { describe, expect, it } from "vitest";
import type { DiffOut, Matching, PersonRow, Place, Preference } from "@/lib/api/moderation";
import { refusal } from "@/lib/api/moderation";
import { HttpError } from "@/lib/api/client";
import {
  MAX_ANIMATED_MOVES,
  baselineOptions,
  chainText,
  changeLevel,
  changeSummary,
  animatedMoves,
  canPublish,
  chipCount,
  diffRows,
  filterMatchings,
  filterPeople,
  isDraftChild,
  matchingSentence,
  parseTab,
  placeText,
  prefSource,
  priorityDistribution,
  requestedText,
  sortMatchings,
  notifyTargets,
  termPreferences,
  tierForKey,
  tierOf,
  verdictKind,
} from "./moderation-model";
import { ownInstructorId } from "./moderation-console";
import { unsatisfiedStreak } from "./request-timeline";
import { compareChips, gridSpan } from "./compare-calendar";

const place = (over: Partial<Place> = {}): Place => ({ day: 2, start_period: 4, end_period: 5, time: "11:00–12:30", when: null, room_ids: [1, 2], rooms: ["A 306", "C 602"], weeks: [1], locked: false, origin: "SOLVER", ...over });

/** PHAR 114 §2 (Bahar R1156): asked A 306 + C 602 on Tuesday P4–P5, not placed (real row, moderation spec §0) */
const phar114 = (over: Partial<Matching> = {}): Matching => ({
  request_id: 1156,
  section_id: 77,
  term_id: 1,
  course_code: "PHAR 114",
  course_name: "English for Academic Purposes",
  section: "2",
  label: "PHAR 114 §2",
  program: "Eczacılık",
  faculty: "Eczacılık Fakültesi",
  enrolment: 30,
  instructors: [{ id: 9, name: "Öğr. Gör. S. K.", role: "PRIMARY" }],
  requested: { day: 2, days: [], start_period: 4, end_period: 5, time: "11:00–12:30", weeks: [], room_text: "A306/C602", rooms: ["A 306 + C 602"], building: null, tags: [], capacity: null, status: "PARSED" },
  definitive: { text: "A 306 / C 602", room_ids: [1, 2], rooms: ["A 306", "C 602"] },
  assigned: null,
  satisfied: { room: null, building: null, tags: null, day: null, period: null },
  verdict: "unplaced",
  verdict_text: { tr: "Yerleşmedi", en: "Not placed" },
  reason: { code: "locked_row_kept", text: { tr: "A 306 ve C 602 her hafta ING 402 ve SOS 404 §1 tarafından tutuluyor", en: "A 306 and C 602 are held every week by ING 402 and SOS 404 §1" }, culprits: [{ request_id: 402, label: "ING 402" }], policy_step: { step: 1, text: { tr: "adım 1 · kilit", en: "step 1 · lock" } } },
  priority: { value: 0, source: "default" },
  source: "run",
  provenance: { row: 1156, source_key: null },
  teacher_preferences: [],
  ...over,
});

describe("moderation model", () => {
  it("parses the tab from the URL with Kişiler as the default", () => {
    expect(parseTab("matchings")).toBe("matchings");
    expect(parseTab("nope")).toBe("people");
    expect(parseTab(null)).toBe("people");
  });

  it("maps every verdict to a tone, never colour alone (the word is the label)", () => {
    expect(verdictKind("satisfied")).toBe("feasible");
    expect(verdictKind("partial")).toBe("warning");
    expect(verdictKind("not_as_requested")).toBe("warning");
    expect(verdictKind("unplaced")).toBe("infeasible");
    expect(verdictKind("pending")).toBeNull();
  });

  it("reads priority tiers from the stored integer and the p 1/2/3 keys", () => {
    expect(tierOf(1)).toBe("high");
    expect(tierOf(7)).toBe("high");
    expect(tierOf(0)).toBe("normal");
    expect(tierOf(null)).toBe("normal");
    expect(tierOf(-1)).toBe("low");
    expect([tierForKey("1"), tierForKey("2"), tierForKey("3"), tierForKey("4")]).toEqual(["high", "normal", "low", null]);
  });

  it("warns when High exceeds 10 % of the requests", () => {
    expect(priorityDistribution([1, 0, 0, 0, 0, 0, 0, 0, 0, 0]).overLimit).toBe(false);
    const d = priorityDistribution([1, 1, 0, 0, 0, 0, 0, 0, 0, -1]);
    expect(d).toMatchObject({ high: 2, normal: 7, low: 1, overLimit: true });
  });

  it("writes requested → assigned sentences in both languages", () => {
    const m = phar114();
    expect(requestedText(m, "tr")).toBe("Sal P4–P5 · A 306 + C 602");
    expect(requestedText(m, "en")).toBe("Tue P4–P5 · A 306 + C 602");
    expect(placeText(place(), "tr")).toBe("Sal P4–P5 11:00–12:30 · A 306 + C 602");
    expect(matchingSentence(m, "tr")).toBe("İstenen Sal P4–P5 · A 306 + C 602; atanan yok");
    expect(matchingSentence({ ...m, assigned: place({ rooms: ["A 206"] }) }, "en")).toContain("assigned Tue P4–P5 11:00–12:30 · A 206");
  });

  it("filters matchings by quick chip and a Turkish-aware search", () => {
    const rows = [phar114(), phar114({ request_id: 545, label: "PHAR 240 §1", verdict: "satisfied", instructors: [{ id: 3, name: "Dr. Öğr. Üyesi E. Y.", role: "PRIMARY" }] }), phar114({ request_id: 9, label: "HEM 106", verdict: "partial" })];
    expect(filterMatchings(rows, "unsatisfied", "").map((r) => r.request_id)).toEqual([1156, 9]);
    expect(filterMatchings(rows, "satisfied", "").map((r) => r.request_id)).toEqual([545]);
    expect(filterMatchings(rows, "all", "öğr üyesi").map((r) => r.request_id)).toEqual([545]);
    expect(filterMatchings(rows, "all", "OGR UYESI").map((r) => r.request_id)).toEqual([545]);
    expect(sortMatchings(rows).map((r) => r.verdict)).toEqual(["unplaced", "partial", "satisfied"]);
    expect(chipCount({ satisfied: 639, partial: 6, not_as_requested: 3, unplaced: 36 }, "unsatisfied")).toBe(45);
    expect(chipCount({ satisfied: 639, partial: 6, not_as_requested: 3, unplaced: 36 }, "all")).toBe(684);
  });

  it("filters people by unmet requests and the streak badge", () => {
    const p = (id: number, counts: Record<string, number>, badge = false): PersonRow => ({ id, name: `P${id}`, title: null, unit: null, roles: [], sections: 1, requests: 1, counts, match_rate: null, active_preferences: 0, learned_priors: null, priority_max: 0, accessibility: "no", unsatisfied_streak: badge ? 2 : 0, badge: badge ? { tr: "2 dönemdir karşılanmadı", en: "not satisfied for 2 terms" } : null, linked_user: false, pending_preferences: 0, courses: [] });
    const rows = [p(1, { satisfied: 2 }), p(2, { unplaced: 1 }), p(3, { partial: 1 }, true)];
    expect(filterPeople(rows, "unmet", "").map((r) => r.id)).toEqual([2, 3]);
    expect(filterPeople(rows, "streak", "").map((r) => r.id)).toEqual([3]);
  });

  it("lists only the term's soft preferences in Tercihler and names their source", () => {
    const pref = (over: Partial<Preference>): Preference => ({ id: 1, term_id: 1, run_id: null, kind: "room_preference", params: {}, hardness: "soft", weight: 5, source: "LEARNED", nl_text: null, enabled: true, ...over });
    const rows = [pref({}), pref({ id: 2, hardness: "hard" }), pref({ id: 3, term_id: null, run_id: 8 }), pref({ id: 4, source: "UPLOAD" })];
    expect(termPreferences(rows).map((r) => r.id)).toEqual([1, 4]);
    expect(prefSource(rows[0]!)).toBe("learned");
    expect(prefSource(rows[3]!)).toBe("file");
  });

  const diff = (over: Partial<DiffOut> = {}): DiffOut => ({
    run_id: 21,
    base_run_id: 20,
    compare_to_run_id: 20,
    compared_to: "published",
    chain: [20],
    status: "OPTIMAL",
    mode: "repair",
    changed_request_ids: [1156],
    is_active: false,
    ready: true,
    counts: { moved: 2, moved_outside_scope: 2, moved_unexplained: 0, unchanged: 646, newly_placed: 1, unplaceable: 35, newly_unplaced: 0, affected_people: 3 },
    moved: [
      { request_id: 402, label: "ING 402", in_scope: false, instructor_ids: [5], from: place({ rooms: ["A 306"] }), to: place({ rooms: ["B 201"] }), causes: [{ code: "displaced_room", text: { tr: "PHAR 114 §2 dersliği aldığı için ING 402 taşındı", en: "ING 402 moved because PHAR 114 §2 took the room" } }] },
      { request_id: 404, label: "SOS 404 §1", in_scope: false, instructor_ids: [6], from: place({ rooms: ["C 602"] }), to: place({ rooms: ["C 501"] }), causes: [] },
    ],
    newly_placed: [{ request_id: 1156, label: "PHAR 114 §2", in_scope: true, instructor_ids: [9], to: place() }],
    unplaceable: [{ request_id: 9, label: "ENG 106", in_scope: false, instructor_ids: [9], was_placed: false, from: null, reason: { code: "no_room", text: { tr: "Bu saatte 70 kişilik boş oda yok", en: "No free room for 70 at this time" }, culprits: [], policy_step: null } }],
    affected_instructor_ids: [5, 6, 9],
    waived_rules: [],
    diagnosis: [],
    ...over,
  });

  it("groups the re-solve diff with reasons (Taşınan / Yeni yerleşen / Yerleşemeyen)", () => {
    const g = diffRows(diff(), "tr");
    expect(g.moved.map((r) => [r.label, r.before, r.after])).toEqual([
      ["ING 402", "Sal P4–P5 11:00–12:30 · A 306", "Sal P4–P5 11:00–12:30 · B 201"],
      ["SOS 404 §1", "Sal P4–P5 11:00–12:30 · C 602", "Sal P4–P5 11:00–12:30 · C 501"],
    ]);
    expect(g.moved[0]!.reason).toContain("PHAR 114 §2 dersliği aldığı için");
    expect(g.newly_placed[0]).toMatchObject({ label: "PHAR 114 §2", before: "—", reason: "Değiştirilen talep" });
    expect(g.unplaceable[0]).toMatchObject({ label: "ENG 106", after: "—", reason: "Bu saatte 70 kişilik boş oda yok" });
  });

  it("publishes only a finished, unpublished preview; edits only on a draft child", () => {
    expect(canPublish(diff())).toBe(true);
    expect(canPublish(diff({ ready: false }))).toBe(false);
    expect(canPublish(diff({ is_active: true }))).toBe(false);
    expect(canPublish(diff({ status: "INFEASIBLE" }))).toBe(false);
    expect(canPublish(undefined)).toBe(false);
    expect(isDraftChild(diff())).toBe(true);
    expect(isDraftChild(diff({ is_active: true }))).toBe(false);
  });

  it("animates at most 12 moved chips, only those in view", () => {
    const moves = Array.from({ length: 30 }, (_, i) => i);
    expect(animatedMoves(moves).size).toBe(MAX_ANIMATED_MOVES);
    expect([...animatedMoves(moves, (m) => m % 2 === 0)]).toEqual([0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]);
  });

  it("builds the compare grid from the changed classes only", () => {
    const chips = compareChips(diff());
    expect(chips.map((c) => [c.id, c.kind])).toEqual([[402, "moved"], [404, "moved"], [1156, "new"]]);
    expect(gridSpan(chips)).toEqual({ days: [1, 2, 3, 4, 5], first: 4, last: 5 });
  });

  it("summarises a server-side change: kind, new tier, the first labels and the rest", () => {
    const c = { audit_id: 9, ts: null, action: "section.priority", kind: "priority" as const, entity_type: "section", entity_id: 4, run_id: null, request_ids: [1, 2, 3, 4], labels: ["PSY 277 §1", "PSY 277 §1 lab", "PSY 277 §1 b", "x"], actor_id: 1, actor: "Admin", reason: "akreditasyon", before: { priority: 0 }, after: { priority: 10 } };
    expect(changeSummary(c)).toEqual({ kind: "priority", tier: "high", cleared: false, subjects: "PSY 277 §1, PSY 277 §1 lab, PSY 277 §1 b", more: 1 });
    expect(changeLevel(c)).toBe("section");
    expect(changeLevel({ ...c, action: "person.priority" })).toBe("person");
    expect(changeSummary({ ...c, after: { priority: null } }).cleared).toBe(true);
    expect(changeLevel({ ...c, kind: "pin", action: "moderation.pin" })).toBeNull();
  });

  it("offers the fixed baseline first, then the chain, never the run itself", () => {
    const d = { run_id: 44, base_run_id: 43, compare_to_run_id: 40, chain: [43, 41, 40] };
    expect(baselineOptions(d, 40)).toEqual([40, 43, 41]);
    expect(baselineOptions({ ...d, compare_to_run_id: 43 }, null)).toEqual([43, 41, 40]);
    expect(chainText(d)).toBe("#44 ← #43 ← #41 ← #40");
  });

  it("names the academicians the publish digest reaches (linked accounts only)", () => {
    const people = [{ id: 1, name: "S. K.", title: "Dr.", linked_user: true }, { id: 2, name: "T. E.", title: null, linked_user: false }, { id: 3, name: "Z", title: null, linked_user: true }];
    expect(notifyTargets([1, 2], people)).toEqual({ linked: [{ id: 1, label: "Dr. S. K." }], unlinked: 1 });
  });

  it("finds the own instructor of a teacher's requests (Q11 scope)", () => {
    const a = phar114({ instructors: [{ id: 9, name: "S. K.", role: "PRIMARY" }, { id: 4, name: "X", role: "SECONDARY" }] });
    const b = phar114({ request_id: 2, instructors: [{ id: 9, name: "S. K.", role: "PRIMARY" }] });
    expect(ownInstructorId([a, b])).toBe(9);
    expect(ownInstructorId([])).toBeNull();
  });

  it("counts the 'N dönemdir karşılanmadı' streak like the backend (empty terms neither count nor break)", () => {
    const term = (verdicts: Matching["verdict"][]) => ({ term_id: 1, term_code: "T", term_name: null, run: null, source: "run" as const, counts: {}, match_rate: null, items: verdicts.map((v) => ({ ...phar114({ verdict: v }), role: null, raw: { room_text: null, notes: null, row: null, source_row: null }, parsed: {}, planner_edits: [] })), bookings: [], learned: [] });
    expect(unsatisfiedStreak([term(["unplaced"]), term([]), term(["partial", "satisfied"]), term(["satisfied"])])).toBe(2);
    expect(unsatisfiedStreak([term(["satisfied"]), term(["unplaced"])])).toBe(0);
  });

  it("reads the publish guard's 409 reasons verbatim (and the scope-reduction variant)", () => {
    const guard = new HttpError(409, "409", { detail: { message: "run cannot be published", issues: ["run 21 breaks hard rules (hard score 98); fix or re-solve before publishing"] } });
    expect(refusal(guard, "tr")).toEqual({ message: "run cannot be published", issues: ["run 21 breaks hard rules (hard score 98); fix or re-solve before publishing"], scopeReduction: false });
    const scope = new HttpError(409, "409", { detail: { code: "scope_reduction", message: "run 21 covers weeks [3] only", message_tr: "#21 yalnız 3. haftaları kapsıyor", active: {}, new: {} } });
    expect(refusal(scope, "tr")).toMatchObject({ message: "#21 yalnız 3. haftaları kapsıyor", scopeReduction: true });
    expect(refusal(new HttpError(422, "a repair names the changed requests", "a repair names the changed requests"), "en").message).toBe("a repair names the changed requests");
  });
});
