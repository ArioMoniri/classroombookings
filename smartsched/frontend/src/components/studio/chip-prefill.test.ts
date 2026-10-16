import { describe, expect, it } from "vitest";
import { StudioMeta } from "@/lib/api/studio-schemas";
import { studioMeta } from "@/test/fixtures/studio-meta";
import { chipPrefill, programKeyOf, relatedPrograms } from "./chip-prefill";
import { appliesToDisplay, readAppliesTo } from "./rule-sentence";
import { fallbackSentence } from "./studio-data";

const meta = StudioMeta.parse(studioMeta());
// the 146-programme list of the real workbooks, abridged: the two nursing programmes, the nursing master's
// programmes (their year-1 rows are the ones that end after 17:30) and unrelated names
const programs = [
  "Tıp",
  "Eczacılık",
  "Hemşirelik",
  "Hemşirelik (İngilizce)",
  "Hemşirelik Esasları Tezli Yüksek Lisans",
  "Cerrahi Hastalıklar Hemşireliği Tezli Yüksek Lisans",
  "Hemşirelik Doktora Programı",
  "Beslenme ve Diyetetik",
];
const rooms = [{ id: 7, display_name: "A 204", building_code: "A" }];
const ctx = { templates: meta.templates, programs, rooms, kind: "COURSE" as const };

describe("example chips without an AI key (round-1 R1-S-08 / R1-M-13, T-R1-46)", () => {
  it("the Turkish nursing chip opens the after-hours template with both nursing programmes, year 1 and 17:30", () => {
    const p = chipPrefill("studio.write.chip.nursing", ctx);
    expect(p?.templateId).toBe("no_classes_after");
    expect(p?.hardness).toBe("hard");
    // P11 ends at 17:30: the rule is "no class after P11"
    expect(p?.params?.latest).toBe(11);
    const who = readAppliesTo(p?.params ?? {});
    expect(who).toEqual({ mode: "programs", programs: ["Hemşirelik", "Hemşirelik (İngilizce)"], year: 1 });
  });

  it("the other chips map to their templates (pharmacy → C block on Mondays, TIP → room only for Tıp, A 204 → room closed)", () => {
    const ecz = chipPrefill("studio.write.chip.pharmacy", ctx);
    expect(ecz?.templateId).toBe("keep_in_building");
    expect(ecz?.params).toMatchObject({ building: "C", days: [1], programs: ["Eczacılık"] });
    const tip = chipPrefill("studio.write.chip.tip", ctx);
    expect(tip?.templateId).toBe("room_only_for");
    // "TIP rooms only for Tıp" is stored for everyone else: the complement of the chosen programme
    expect(tip?.params?.forbidden_tags).toEqual(["TIP"]);
    expect(tip?.params?.programs).toEqual(programs.filter((p) => p !== "Tıp"));
    const a204 = chipPrefill("studio.write.chip.a204", ctx);
    expect(a204?.templateId).toBe("room_closed");
    expect(a204?.params).toMatchObject({ room_id: 7, days: [3], periods: [7, 8, 9, 10, 11] });
    expect(chipPrefill("studio.write.chip.evening", ctx)?.params).toEqual({ buildings: ["B", "C"] });
    expect(chipPrefill("studio.write.chip.sameRoom", ctx)?.templateId).toBe("same_room_every_week");
    expect(chipPrefill("studio.write.chip.fit", ctx)?.templateId).toBe("no_small_in_big");
  });

  it("a chip whose template is not offered for this draft kind (exam gap on a course draft) has no prefill", () => {
    expect(chipPrefill("studio.write.chip.examGap", ctx)).toBeNull();
    expect(chipPrefill("studio.write.chip.examGap", { ...ctx, kind: "EXAM" })?.templateId).toBe("exam_gap");
  });

  it("a chip whose programme is missing from the term still opens the template, with the programme left to choose", () => {
    const p = chipPrefill("studio.write.chip.nursing", { ...ctx, programs: ["Tıp"] });
    expect(p?.templateId).toBe("no_classes_after");
    expect(readAppliesTo(p?.params ?? {})).toEqual({ mode: "all" });
  });

  it("asks about the programmes with a similar name (the nursing master's year-1 rows end after 17:30)", () => {
    const related = relatedPrograms(["Hemşirelik", "Hemşirelik (İngilizce)"], programs);
    expect(related).toEqual(["Hemşirelik Esasları Tezli Yüksek Lisans", "Cerrahi Hastalıklar Hemşireliği Tezli Yüksek Lisans", "Hemşirelik Doktora Programı"]);
    expect(relatedPrograms(["Tıp"], programs)).toEqual([]);
    expect(relatedPrograms([], programs)).toEqual([]);
  });

  it("a stored rule shows the programme with its own capital letters, not the backend's lower-cased key", () => {
    // the backend normalises `PROG:<programme>:Y1` to its canonical (lower-cased) key when the rule is saved
    expect(programKeyOf("Hemşirelik (İngilizce)")).toBe("hemşirelik (ingilizce)");
    const shown = appliesToDisplay(readAppliesTo({ cohorts: ["PROG:hemşirelik (ingilizce):Y1", "PROG:hemşirelik:Y1"] }), { ...fallbackSentence, programs });
    expect(shown).toBe("Hemşirelik (İngilizce), Hemşirelik year 1");
  });
});
