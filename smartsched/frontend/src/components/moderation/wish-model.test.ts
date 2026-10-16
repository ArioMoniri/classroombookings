/** P19-T2 "Tercih ekle" model, on the real Bahar rows the backend test uses (R601 PTL 102 §1, asked C 601). */
import { describe, expect, it } from "vitest";
import type { TeacherPref } from "@/lib/api/teacher-preferences";
import { buildingCode, buildingsOf, departmentAsk, emptyWish, filterGroups, fixedClasses, formIssues, groupWishes, isKnownError, roomCode, wishBody, wishSentence } from "./wish-model";

const pref = (over: Partial<TeacherPref> = {}): TeacherPref => ({
  id: 40,
  constraint_id: 40,
  term_id: 1,
  status: "pending",
  enabled: false,
  kind: "room_preference",
  kind_label: { tr: "Oda tercihi", en: "Room preference" },
  submission: "fe71960fd30a",
  request_ids: [574, 590],
  labels: ["PTL 152 §1", "PTL 102 §1"],
  instructor: { id: 266, name: "Doç. Dr. D. Ş." },
  wish: { room_ids: [32], rooms: ["C 301"] },
  department: { room_ids: [50], rooms: ["C 601"] },
  rank: "below_department",
  text: { tr: "PTL 152 §1, PTL 102 §1: oda tercihi C 301", en: "PTL 152 §1, PTL 102 §1: room preference C 301" },
  note: null,
  hardness: "soft",
  weight: 1,
  submitted_at: "2026-10-16T04:31:58+00:00",
  decided_at: null,
  decided_by: null,
  reason: null,
  reason_code: null,
  ...over,
});

describe("wish form", () => {
  it("refuses what the server refuses before sending", () => {
    const f = emptyWish();
    expect(formIssues(f)).toEqual(["noClasses", "noRoom"]);
    expect(formIssues({ ...f, requestIds: [590], roomIds: [1, 2, 3], roomCodes: ["C 301", "C 302", "C 303"] })).toEqual(["tooManyRooms"]);
    expect(formIssues({ ...f, requestIds: [590], kind: "building_preference" })).toEqual(["noBuilding"]);
    expect(formIssues({ ...f, requestIds: [590], kind: "day_window" })).toEqual(["noWindow"]);
    expect(formIssues({ ...f, requestIds: [590], kind: "day_window", earliest: 8, latest: 4 })).toEqual(["badWindow"]);
    expect(formIssues({ ...f, requestIds: [590], kind: "day_window", latest: 6 })).toEqual([]);
    expect(formIssues({ ...f, requestIds: [590], roomIds: [32], note: "x".repeat(501) })).toEqual(["noteLong"]);
  });

  it("sends only the fields of the chosen kind, never hardness or weight", () => {
    const f = { ...emptyWish([590, 574, 590]), roomIds: [32], roomCodes: ["C 302"], buildings: ["C"], earliest: 2, days: [2], note: "  deney düzeneği  " };
    expect(wishBody(f)).toEqual({ kind: "room_preference", request_ids: [590, 574], room_ids: [32], rooms: ["C 302"], note: "deney düzeneği" });
    expect(wishBody({ ...f, kind: "building_preference" })).toEqual({ kind: "building_preference", request_ids: [590, 574], buildings: ["C"], note: "deney düzeneği" });
    expect(wishBody({ ...f, kind: "day_window", days: [3, 2, 3] })).toEqual({ kind: "day_window", request_ids: [590, 574], earliest: 2, days: [2, 3], note: "deney düzeneği" });
    expect(wishBody({ ...f, note: "" })).not.toHaveProperty("note");
  });

  it("writes the sentence the server stores (teacher_preferences._texts)", () => {
    const f = { ...emptyWish([574, 590]), roomIds: [32] };
    expect(wishSentence(f, ["PTL 152 §1", "PTL 102 §1"], ["C 301"], "tr")).toBe(pref().text.tr);
    expect(wishSentence(f, ["PTL 152 §1", "PTL 102 §1"], ["C 301"], "en")).toBe(pref().text.en);
    expect(wishSentence({ ...f, kind: "building_preference", buildings: ["C"] }, ["PTL 102 §1"], [], "tr")).toBe("PTL 102 §1: C blok tercihi");
    expect(wishSentence({ ...f, kind: "day_window", latest: 6 }, ["A", "B", "C", "D"], [], "en")).toBe("A, B, C …: classes within P1–P6");
  });

  it("reads typed room codes and building letters the way the lists write them", () => {
    expect(roomCode("c301")).toBe("C 301");
    expect(roomCode("C-404")).toBe("C 404");
    expect(roomCode("c 404")).toBe("C 404");
    expect(roomCode("Z 10")).toBe("Z 10");
    expect(roomCode("salon")).toBeNull();
    expect(buildingCode("c")).toBe("C");
    expect(buildingCode("C Blok")).toBe("C");
    expect(buildingCode("ilk")).toBeNull();
    expect(buildingsOf([{ code: "C 601" }, { code: "A 306" }, { code: "C 301" }, { code: "" }])).toEqual(["A", "C"]);
  });

  it("finds the classes whose time the department form fixed", () => {
    const rows = [
      { request_id: 590, label: "PTL 102 §1", requested: { start_period: 4 } },
      { request_id: 801, label: "PTL 184 §1", requested: { start_period: null } },
    ] as unknown as Parameters<typeof fixedClasses>[0];
    expect(fixedClasses(rows, [590, 801]).map((m) => m.label)).toEqual(["PTL 102 §1"]);
    expect(fixedClasses(rows, [801])).toEqual([]);
  });

  it("knows every refusal code of the endpoint", () => {
    for (const code of ["not_linked", "not_yours", "hard", "weight", "kind", "no_classes", "fixed_by_department", "already_requested", "unknown_room", "unknown_building", "room_closed", "window", "days", "invalid_rule", "too_many_pending", "decided", "reason_required"]) {
      expect(isKnownError(code)).toBe(true);
    }
    expect(isKnownError("nope")).toBe(false);
  });
});

describe("wish lists", () => {
  it("groups the rules of one submission and puts pending first, then rejected, then accepted", () => {
    const groups = groupWishes([
      pref({ id: 41, submission: "a", status: "accepted", submitted_at: "2026-10-16T05:00:00Z" }),
      pref({ id: 42, submission: "b", status: "pending", submitted_at: "2026-10-15T05:00:00Z" }),
      pref({ id: 43, submission: "b", status: "pending", labels: ["PTL 184 §1"], request_ids: [801] }),
      pref({ id: 44, submission: "c", status: "rejected", reason: "C 301 bu saatlerde dolu" }),
    ]);
    expect(groups.map((g) => [g.key, g.status, g.items.length])).toEqual([
      ["b", "pending", 2],
      ["c", "rejected", 1],
      ["a", "accepted", 1],
    ]);
    expect(groups[0]!.labels).toEqual(["PTL 152 §1", "PTL 102 §1", "PTL 184 §1"]);
    expect(groups[0]!.requestIds.sort()).toEqual([574, 590, 801]);
  });

  it("filters the review by status and by course or person, Turkish-insensitive", () => {
    const groups = groupWishes([pref({ submission: "a" }), pref({ id: 50, submission: "z", status: "accepted", labels: ["PSY 277 §1"], instructor: { id: 9, name: "Öğr. Gör. İ. K." } })]);
    expect(filterGroups(groups, "pending", "").map((g) => g.key)).toEqual(["a"]);
    expect(filterGroups(groups, "all", "psy 277").map((g) => g.key)).toEqual(["z"]);
    expect(filterGroups(groups, "all", "ı. k").map((g) => g.key)).toEqual([]);
    expect(filterGroups(groups, "all", "İ. K").map((g) => g.key)).toEqual(["z"]);
  });

  it("names the department's own ask that ranks first", () => {
    expect(departmentAsk(pref())).toEqual(["C 601"]);
    expect(departmentAsk(pref({ kind: "building_preference", department: { buildings: ["C"] } }))).toEqual(["C"]);
    expect(departmentAsk(pref({ kind: "day_window", department: {} }))).toEqual([]);
  });
});
