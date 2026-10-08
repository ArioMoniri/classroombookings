import { describe, expect, it } from "vitest";
import { StudioMeta } from "@/lib/api/studio-schemas";
import { studioMeta } from "@/test/fixtures/studio-meta";
import { fallbackSentence } from "./studio-data";
import { compactRange, defaultParams, importanceOf, missingRequired, parseTemplate, plainSentence, readAppliesTo, templateFor, templateIssues, tokens, writeAppliesTo, writeField } from "./rule-sentence";

const meta = StudioMeta.parse(studioMeta());
const tpl = (id: string) => {
  const t = meta.templates.find((x) => x.id === id);
  if (!t) throw new Error(id);
  return t;
};
const ctx = { ...fallbackSentence, roomCode: (id: number) => ({ 1: "A 204", 9: "A 206" })[id] ?? `#${id}`, programs: ["Tıp", "Eczacılık", "Hemşirelik"] };

describe("rule sentence model", () => {
  it("parses slots and optional groups", () => {
    expect(parseTemplate("Keep {a} in {b} [on {c}]")).toEqual([
      { kind: "text", text: "Keep " },
      { kind: "slot", name: "a" },
      { kind: "text", text: " in " },
      { kind: "slot", name: "b" },
      { kind: "text", text: " " },
      { kind: "optional", parts: [{ kind: "text", text: "on " }, { kind: "slot", name: "c" }] },
    ]);
  });

  it("renders a stored rule; optional parts only when filled", () => {
    const t = tpl("keep_in_building");
    expect(plainSentence(tokens(t, { building: "C", programs: ["Eczacılık"] }, ctx))).toBe("Keep Eczacılık in building C");
    expect(plainSentence(tokens(t, { building: "C", days: [1], programs: ["Eczacılık"] }, ctx))).toBe("Keep Eczacılık in building C on Monday");
    const builder = tokens(t, {}, ctx, { showEmptyOptional: true });
    expect(builder.filter((x) => x.kind === "slot").map((x) => (x.kind === "slot" ? x.slot.display : ""))).toEqual(["all classes", "choose…", "choose…"]);
  });

  it("round-trips 'applies to' through solver selectors (cohort keys for a year)", () => {
    const p = writeAppliesTo({ latest: 11, event_ids: [3] }, { mode: "programs", programs: ["Hemşirelik"], year: 1 });
    expect(p).toEqual({ latest: 11, cohorts: ["PROG:Hemşirelik:Y1"] });
    expect(readAppliesTo(p)).toEqual({ mode: "programs", programs: ["Hemşirelik"], year: 1 });
    expect(readAppliesTo({ event_ids: [1, 2] })).toEqual({ mode: "classes", event_ids: [1, 2] });
    expect(readAppliesTo({})).toEqual({ mode: "all" });
  });

  it("'TIP rooms only for Tıp' is stored as forbidden for everyone else", () => {
    const t = tpl("room_only_for");
    const field = t.fields.find((f) => f.name === "applies_to");
    if (!field) throw new Error("field");
    const p = writeField(field, { forbidden_tags: ["TIP"] }, ["Tıp"], ctx);
    expect(p.programs).toEqual(["Eczacılık", "Hemşirelik"]);
    expect(plainSentence(tokens(t, p, ctx))).toBe("TIP rooms only for Tıp");
  });

  it("picks the template that matches the stored params", () => {
    expect(templateFor("room_tags", { required_tags: ["PC"] }, meta.templates)?.id).toBe("needs_lab");
    expect(templateFor("room_tags", { forbidden_tags: ["TIP"] }, meta.templates)?.id).toBe("room_only_for");
    expect(templateFor("unknown_kind", {}, meta.templates)).toBeUndefined();
  });

  it("knows defaults, required fields and the Low/Normal/High scale", () => {
    expect(defaultParams(tpl("needs_lab"))).toEqual({ required_tags: ["PC"] });
    expect(missingRequired(tpl("never_use_room"), {}, ctx).map((f) => f.name)).toEqual(["rooms"]);
    expect(missingRequired(tpl("never_use_room"), { room_ids: [1] }, ctx)).toEqual([]);
    expect([2, 5, 8, 7].map((w) => importanceOf(w))).toEqual(["low", "normal", "high", "custom"]);
    expect(compactRange([1, 2, 3, 5, 7, 8])).toBe("1–3, 5, 7–8");
  });

  it("shows clock times for 'no classes after' (period end) and rooms by code", () => {
    expect(plainSentence(tokens(tpl("no_classes_after"), { latest: 11, cohorts: ["PROG:Hemşirelik:Y1"] }, ctx))).toBe("No classes after 17:30 for Hemşirelik year 1");
    expect(plainSentence(tokens(tpl("never_use_room"), { room_ids: [1, 9] }, ctx))).toBe("Never use room A 204, A 206 for all classes");
  });
});

// recording bug: "No classes after" could be saved with neither time, a blank hard rule the pre-check
// then reported as a clash. Every template is validated before "Add rule" is enabled.
describe("template validation (builder save gate)", () => {
  const codes = (id: string, params: Record<string, unknown>) => templateIssues(tpl(id), params, ctx).map((i) => `${i.code}${i.field ? `:${i.field.name}` : ""}`);

  it("no classes after: needs a latest or an earliest time, in the right order", () => {
    expect(codes("no_classes_after", {})).toEqual(["needOneTime"]);
    expect(codes("no_classes_after", { latest: 12 })).toEqual([]);
    expect(codes("no_classes_after", { earliest: 2 })).toEqual([]);
    expect(codes("no_classes_after", { latest: 4, earliest: 9 })).toEqual(["timeOrder"]);
    expect(codes("no_classes_after", { latest: 30 })).toEqual(["range:latest"]);
  });

  it("required fields, minimum counts and number ranges on the other templates", () => {
    expect(codes("keep_in_building", {})).toEqual(["missing:building"]);
    expect(codes("keep_in_building", { building: "C" })).toEqual([]);
    expect(codes("same_room_as", { event_ids: [3] })).toEqual(["minItems:courses"]);
    expect(codes("same_room_as", { event_ids: [3, 4] })).toEqual([]);
    expect(codes("room_closed", { room_id: 1 })).toEqual(["missing:days"]);
    expect(codes("exam_gap", { min_periods: 9 })).toEqual(["range:n"]);
    expect(codes("max_exams_per_day", { n: 0 })).toEqual(["range:n"]);
    expect(codes("max_exams_per_day", { n: 2 })).toEqual([]);
    expect(codes("no_small_in_big", defaultParams(tpl("no_small_in_big")))).toEqual([]);
    expect(codes("needs_lab", defaultParams(tpl("needs_lab")))).toEqual([]);
    expect(codes("same_room_every_week", {})).toEqual([]);
  });

  it("'room only for' needs at least one programme (none would keep everyone out of the rooms)", () => {
    expect(codes("room_only_for", { forbidden_tags: ["TIP"] })).toEqual(["missing:applies_to"]);
    const f = tpl("room_only_for").fields.find((x) => x.name === "applies_to")!;
    expect(codes("room_only_for", writeField(f, { forbidden_tags: ["TIP"] }, ["Tıp"], ctx))).toEqual([]);
  });

  it("every template starts invalid or valid on purpose: none can be saved blank when it would mean nothing", () => {
    const blankOk = new Set(["same_room_every_week", "no_small_in_big", "needs_lab"]);
    for (const t of meta.templates) {
      const issues = templateIssues(t, defaultParams(t), ctx);
      expect({ id: t.id, ok: issues.length === 0 }).toEqual({ id: t.id, ok: blankOk.has(t.id) });
    }
  });
});
