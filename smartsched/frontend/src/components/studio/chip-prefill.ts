/**
 * Example chips → a pre-filled template (round-1 R1-S-08 / R1-M-13, T-R1-46). Without an AI key the composer cannot
 * turn a sentence into a rule, so a chip opens the structured template that says the same thing, with its fields set
 * from the term's own data (programmes, rooms). Pure: the Studio passes what it has loaded.
 */
import type { RuleTemplate } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import type { Params } from "./rule-sentence";
import { writeAppliesTo } from "./rule-sentence";
import type { BuilderPrefill } from "./template-gallery";

export interface ChipContext {
  templates: readonly RuleTemplate[];
  /** every programme name of the term (display case) */
  programs: readonly string[];
  rooms: readonly { id: number; display_name: string; building_code: string }[];
  kind: "COURSE" | "EXAM";
}

/** The backend's canonical programme key (`importers.normalize.program_key`): lower-cased in Turkish, one space. */
export function programKeyOf(name: string): string {
  return name.trim().toLocaleLowerCase("tr-TR").replace(/\s+/g, " ");
}

/** Programmes whose key is `key` or starts with `key (` ("Hemşirelik", "Hemşirelik (İngilizce)"; not the master's). */
function programsNamed(programs: readonly string[], key: string): string[] {
  return programs.filter((p) => {
    const k = programKeyOf(p);
    return k === key || k.startsWith(`${key} (`);
  });
}

/**
 * Programmes with a similar name that are not chosen ("Hemşirelik Esasları Tezli Yüksek Lisans" next to "Hemşirelik"):
 * the builder asks whether the rule should reach them too (their year-1 rows are the only ones after 17:30).
 * The stem is the first six letters of a chosen programme's first word (Turkish suffixes change the ending).
 */
export function relatedPrograms(chosen: readonly string[], programs: readonly string[]): string[] {
  const stems = [...new Set(chosen.map((p) => programKeyOf(p).split(" ")[0] ?? "").filter((w) => w.length >= 5).map((w) => w.slice(0, 6)))];
  if (!stems.length) return [];
  const taken = new Set(chosen.map(programKeyOf));
  return programs.filter((p) => !taken.has(programKeyOf(p)) && stems.some((s) => programKeyOf(p).split(" ").some((w) => w.startsWith(s))));
}

const AFTERNOON = [7, 8, 9, 10, 11];

/** The template and field values a chip stands for; null when the chip has no template in this draft kind. */
export function chipPrefill(chip: MessageKey, ctx: ChipContext): BuilderPrefill | null {
  const has = (id: string) => ctx.templates.find((x) => x.id === id && (ctx.kind === "EXAM" || x.topic !== "exams"));
  const build = (id: string, params: Params, hardness?: "hard" | "soft"): BuilderPrefill | null => (has(id) ? { templateId: id, params, hardness } : null);
  switch (chip) {
    case "studio.write.chip.nursing": {
      const who = programsNamed(ctx.programs, "hemşirelik");
      return build("no_classes_after", writeAppliesTo({ latest: 11 }, who.length ? { mode: "programs", programs: who, year: 1 } : { mode: "all" }), "hard");
    }
    case "studio.write.chip.pharmacy": {
      const who = programsNamed(ctx.programs, "eczacılık");
      return build("keep_in_building", writeAppliesTo({ building: "C", days: [1] }, who.length ? { mode: "programs", programs: who, year: null } : { mode: "all" }));
    }
    case "studio.write.chip.tip": {
      const allowed = new Set(programsNamed(ctx.programs, "tıp").map(programKeyOf));
      const others = ctx.programs.filter((p) => !allowed.has(programKeyOf(p)));
      return build("room_only_for", writeAppliesTo({ forbidden_tags: ["TIP"] }, allowed.size && others.length ? { mode: "programs", programs: others, year: null } : { mode: "all" }), "hard");
    }
    case "studio.write.chip.evening":
      return build("evening_in_buildings", { buildings: ["B", "C"] });
    case "studio.write.chip.sameRoom":
      return build("same_room_every_week", {});
    case "studio.write.chip.fit":
      return build("no_small_in_big", {});
    case "studio.write.chip.a204": {
      const room = ctx.rooms.find((r) => r.display_name.replace(/\s+/g, "").toLocaleUpperCase("tr-TR") === "A204");
      return build("room_closed", { ...(room ? { room_id: room.id } : {}), days: [3], periods: AFTERNOON });
    }
    case "studio.write.chip.examGap":
      return build("exam_gap", { min_periods: 1 });
    default:
      return null;
  }
}
