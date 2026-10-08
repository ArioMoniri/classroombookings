import { describe, expect, it } from "vitest";
import { StudioMeta } from "@/lib/api/studio-schemas";
import { studioMeta } from "@/mocks/studio-data";
import { fallbackSentence } from "./studio-data";
import { compactRange, defaultParams, importanceOf, missingRequired, parseTemplate, plainSentence, readAppliesTo, templateFor, tokens, writeAppliesTo, writeField } from "./rule-sentence";

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
