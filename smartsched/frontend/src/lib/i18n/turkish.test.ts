import { describe, expect, it } from "vitest";
import { fixed, ordinalWeek, pct, spokenTail, suffix, weekList, withSuffix } from "./turkish";

describe("Turkish grammar helpers (T-R1-38)", () => {
  it("percentages: % before the number, a decimal comma, the accusative of the spoken number", () => {
    expect(pct(0, { suffix: "acc" })).toBe("%0'ı");
    expect(pct(95, { suffix: "acc" })).toBe("%95'i");
    expect(pct(100)).toBe("%100");
    expect(pct(100, { suffix: "acc" })).toBe("%100'ü");
    expect(pct(0.6)).toBe("%0,6");
    expect(pct(0.6, { suffix: "acc" })).toBe("%0,6'yı");
    expect(pct(96, { suffix: "dat" })).toBe("%96'ya");
    // 3rd-person possessive (lane F ask, T-R1-38): "taleplerin %72'si", "%95'i", "%0'ı", "%100'ü", "%0,6'sı"
    expect(pct(72, { suffix: "poss" })).toBe("%72'si");
    expect(pct(95, { suffix: "poss" })).toBe("%95'i");
    expect(pct(0, { suffix: "poss" })).toBe("%0'ı");
    expect(pct(100, { suffix: "poss" })).toBe("%100'ü");
    expect(pct(0.6, { suffix: "poss" })).toBe("%0,6'sı");
    expect(withSuffix("B 201", "poss")).toBe("B 201'i");
    expect(withSuffix("Psikoloji", "poss")).toBe("Psikoloji'si");
    expect(pct(12.34, { digits: 1 })).toBe("%12,3");
    expect(pct(Number.NaN)).toBe("%0");
  });

  it("English percentages follow the number and take no suffix", () => {
    expect(pct(100, { locale: "en" })).toBe("100%");
    expect(pct(0.6, { locale: "en", suffix: "acc" })).toBe("0.6%");
  });

  it("the spoken tail decides the suffix (numbers and codes)", () => {
    expect(spokenTail("201")).toBe("bir");
    expect(spokenTail("30")).toBe("otuz");
    expect(spokenTail("1000")).toBe("bin");
    expect(spokenTail("A 101")).toBe("bir");
    expect(withSuffix("B 201", "dat")).toBe("B 201'e");
    expect(withSuffix("A 606", "dat")).toBe("A 606'ya");
    expect(withSuffix("LAB", "acc")).toBe("LAB'ı");
    expect(suffix("3", "loc")).toBe("te");
    expect(suffix("40", "abl")).toBe("tan");
    expect(suffix("2", "gen")).toBe("nin");
    expect(suffix("10", "loc")).toBe("da");
  });

  it("decimals use the locale's separator", () => {
    expect(fixed(12, 1)).toBe("12,0");
    expect(fixed(10, 1, "en")).toBe("10.0");
  });

  it("weeks: one week is singular, several are listed", () => {
    expect(ordinalWeek(3)).toBe("3. hafta");
    expect(ordinalWeek(3, "en")).toBe("week 3");
    expect(weekList([3])).toBe("3. hafta");
    expect(weekList([3, 3])).toBe("3. hafta");
    expect(weekList([5, 3])).toBe("3. ve 5. haftalar");
    expect(weekList([1, 2, 3, 4])).toBe("1.–4. haftalar");
    expect(weekList([1, 2, 3, 4, 6])).toBe("1.–4. ve 6. haftalar");
    expect(weekList([1, 2])).toBe("1. ve 2. haftalar");
    expect(weekList([3, 5], "en")).toBe("weeks 3 and 5");
    expect(weekList([1, 2, 3], "en")).toBe("weeks 1–3");
    expect(weekList([])).toBe("");
  });
});
