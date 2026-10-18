import { describe, expect, it } from "vitest";
import type { Profile } from "@/lib/api/seasons";
import { appliesText, groupProfiles, nextRowKey, profileKey, weightOverrides } from "./season-model";

const p = (over: Partial<Profile>): Profile => ({
  id: 1,
  key: "final_pc",
  version: 1,
  name: { tr: "Final PC", en: "Final PC" },
  name_tr: "Final PC",
  name_en: "Final PC",
  applies_to: [],
  solver_weights: {},
  booking_overlays: [],
  peak_threshold_pct: 85,
  status: "draft",
  builtin: false,
  origin: "admin",
  parent_id: null,
  approved_at: null,
  explanation: {},
  evidence: {},
  source: "",
  weights_diff: [],
  ...over,
});

describe("groupProfiles", () => {
  it("stands a key on its active version and keeps a newer draft as the pending edit", () => {
    const list = [p({ id: 1, version: 1, status: "retired" }), p({ id: 2, version: 2, status: "active", parent_id: 1 }), p({ id: 3, version: 3, status: "draft", parent_id: 2 })];
    const [g] = groupProfiles(list);
    expect(g?.current.id).toBe(2);
    expect(g?.draft?.id).toBe(3);
    expect(g?.versions.map((v) => v.version)).toEqual([3, 2, 1]);
  });

  it("a key with only a draft stands on the draft (no pending edit) and built-ins come first", () => {
    const list = [p({ id: 5, key: "a", version: 1, status: "draft", name: { tr: "A", en: "A" } }), p({ id: null, key: "standard", builtin: true, status: "active", name: { tr: "Standart", en: "Standard" } })];
    const groups = groupProfiles(list);
    expect(groups.map((g) => g.key)).toEqual(["standard", "a"]);
    expect(groups[1]?.current.id).toBe(5);
    expect(groups[1]?.draft).toBeNull();
  });
});

describe("profileKey", () => {
  it("folds Turkish letters and never answers a built-in key", () => {
    expect(profileKey("Final haftası (PC)")).toBe("final_haftasi_pc");
    expect(profileKey("Güz – ders dönemi")).toBe("guz_ders_donemi");
    expect(profileKey("Standard")).toBe("standard_1");
    expect(profileKey("   ")).toBe("profil");
  });
});

describe("appliesText", () => {
  it("reads the server's labels and names '*' plainly", () => {
    const seasons = [{ key: "FINAL", label: { tr: "Final", en: "Final exams" } }];
    const kinds = [{ key: "EXAM", label: { tr: "Sınav dönemi", en: "Exam period" } }];
    expect(appliesText([{ season: "FINAL", period_kind: "EXAM" }, { season: "*", period_kind: "*" }], seasons, kinds, "tr", { season: "Her dönem", kind: "her hafta" })).toBe("Final · Sınav dönemi; Her dönem · her hafta");
  });
});

describe("weightOverrides", () => {
  it("sends only changed, valid integers; blank keeps the standard", () => {
    const out = weightOverrides({ building_preference: "8", room_preference: "10", stability: "", capacity: "-1", exam_gap: "2.5" }, { building_preference: 5, room_preference: 10, stability: 1, capacity: 50, exam_gap: 10 });
    expect(out.weights).toEqual({ building_preference: 8 });
    expect(out.invalid.sort()).toEqual(["capacity", "exam_gap"]);
  });
});

describe("nextRowKey", () => {
  it("moves focus to the next row, else the previous one", () => {
    expect(nextRowKey(["a", "b", "c"], "b")).toBe("c");
    expect(nextRowKey(["a", "b", "c"], "c")).toBe("b");
    expect(nextRowKey(["a"], "a")).toBeNull();
  });
});
