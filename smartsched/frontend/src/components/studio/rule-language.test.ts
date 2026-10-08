import { describe, expect, it } from "vitest";
import { StudioMeta, type StudioRule } from "@/lib/api/studio-schemas";
import { studioMeta } from "@/test/fixtures/studio-meta";
import { translate } from "@/lib/i18n";
import { dayName } from "@/lib/time";
import { detectTextLang, ruleDisplay } from "./rule-helpers";
import { plainSentence, type SentenceContext } from "./rule-sentence";

const meta = StudioMeta.parse(studioMeta());
const ctxFor = (locale: "en" | "tr"): SentenceContext => ({
  locale,
  roomCode: (id) => `#${id}`,
  classLabel: (id) => `#${id}`,
  programs: ["Tıp", "Eczacılık"],
  dayName: (d) => dayName(d, locale),
  tagLabel: (x) => x,
  words: {
    allClasses: translate(locale, "studio.rule.allClasses"),
    nClasses: (n) => translate(locale, "studio.rule.nClasses", { n }),
    year: (y) => translate(locale, "studio.classes.yearN", { n: y }),
    choose: translate(locale, "studio.rule.choose"),
    fromWeek: (w) => translate(locale, "studio.rule.fromWeek", { n: w }),
    weeks: (w) => translate(locale, "studio.rule.weeks", { w }),
  },
});
const rule = (over: Partial<StudioRule>): StudioRule => ({ id: 1, kind: "building_preference", params: { building: "C", programs: ["Eczacılık"] }, hardness: "soft", weight: 5, source: "ADMIN", nl_text: null, enabled: true, in_play: true, title: { tr: "Blok tercihi", en: "Building preference" }, affected_count: 3, ...over });

describe("rule language (recording bug: English rule sentences in the Turkish UI)", () => {
  it("detects the language of a free-text rule", () => {
    expect(detectTextLang("Keep the pharmacy classes in building C")).toBe("en");
    expect(detectTextLang("Eczacılık dersleri C blokta olsun")).toBe("tr");
    expect(detectTextLang("ders yok cuma sonra")).toBe("tr");
    expect(detectTextLang("BIO 101 → A 204")).toBeNull();
  });

  it("a rule built from a template renders in the UI language from its params; the stored English sentence is not shown", () => {
    const r = rule({ nl_text: "Keep Eczacılık in building C", source: "ADMIN" });
    const tr = ruleDisplay(r, meta, ctxFor("tr"));
    expect(tr.tokens && plainSentence(tr.tokens)).toBe("Eczacılık derslerini C blokta tut");
    expect(tr.nlText).toBeNull();
    expect(tr.writtenIn).toBeNull();
    const en = ruleDisplay(r, meta, ctxFor("en"));
    expect(en.tokens && plainSentence(en.tokens)).toBe("Keep Eczacılık in building C");
  });

  it("a free-text rule keeps its original words with a 'written in' tag when the language differs", () => {
    const r = rule({ nl_text: "Keep the pharmacy classes in building C please", source: "AI" });
    const tr = ruleDisplay(r, meta, ctxFor("tr"));
    expect(tr.tokens && plainSentence(tr.tokens)).toBe("Eczacılık derslerini C blokta tut");
    expect(tr.nlText).toBe("Keep the pharmacy classes in building C please");
    expect(tr.writtenIn).toBe("en");
    expect(ruleDisplay(r, meta, ctxFor("en")).writtenIn).toBeNull();
  });

  it("a free-text rule without a template shows the catalogue title in the UI language and the original text", () => {
    const r = rule({ kind: "something_new", params: {}, nl_text: "Pazartesi sabahları laboratuvar kapalı", source: "FILE" });
    const en = ruleDisplay(r, meta, ctxFor("en"));
    expect(en.tokens).toBeNull();
    expect(en.fallback).not.toContain("Pazartesi");
    expect(en.nlText).toBe("Pazartesi sabahları laboratuvar kapalı");
    expect(en.writtenIn).toBe("tr");
  });
});
