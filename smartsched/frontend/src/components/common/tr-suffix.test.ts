import { describe, expect, it } from "vitest";
import { harmoniseAfter, lastNumberWord, spokenTail, tr, trPercent, trSuffix } from "./tr-suffix";

describe("Turkish suffix harmony", () => {
  it("reads numbers the Turkish way", () => {
    expect(lastNumberWord(204)).toBe("dört");
    expect(lastNumberWord(240)).toBe("kırk");
    expect(lastNumberWord(100)).toBe("yüz");
    expect(lastNumberWord(1500)).toBe("yüz");
    expect(lastNumberWord(2000)).toBe("bin");
    expect(lastNumberWord(0)).toBe("sıfır");
    expect(spokenTail("17:30")).toBe("otuz");
    expect(spokenTail("13:00")).toBe("üç");
    expect(spokenTail("BME")).toBe("e");
  });

  it("fixes the usability-test sentences (m2)", () => {
    expect(tr("17:30", "abl")).toBe("17:30'dan");
    expect(tr("4. hafta", "abl")).toBe("4. haftadan");
    expect(tr("A 204", "abl")).toBe("A 204'ten");
    expect(tr("A 206", "dat")).toBe("A 206'ya");
    expect(tr("C 501", "loc")).toBe("C 501'de");
    expect(tr("PHAR 240", "abl")).toBe("PHAR 240'tan");
  });

  it("covers vowel endings, codes and names", () => {
    expect(tr("MAT 112 §1", "acc")).toBe("MAT 112 §1'i");
    expect(tr("Perşembe", "dat")).toBe("Perşembe'ye");
    expect(tr("BME", "dat")).toBe("BME'ye");
    expect(tr("Hemşirelik", "abl")).toBe("Hemşirelik'ten");
    expect(tr("Eczacılık", "gen")).toBe("Eczacılık'ın");
    expect(tr("Pazartesi", "loc")).toBe("Pazartesi'de");
    expect(trSuffix("İstanbul", "loc")).toBe("da");
    expect(tr("13:00", "abl")).toBe("13:00'ten");
  });

  it("formats percentages with the sign first in Turkish", () => {
    expect(trPercent(0.44, "tr")).toBe("%44");
    expect(trPercent(0.001, "tr", 1)).toBe("%0,1");
    expect(trPercent(0.44, "en")).toBe("44%");
    expect(tr("%44", "acc")).toBe("%44'ü");
  });

  it("re-harmonises template suffixes after a slot", () => {
    expect(harmoniseAfter("4. hafta", "'den itibaren")).toBe("dan itibaren");
    expect(harmoniseAfter("17:30", "'den sonra ders olmasın")).toBe("'dan sonra ders olmasın");
    expect(harmoniseAfter("A 204", "'de kalsın")).toBe("'te kalsın");
    expect(harmoniseAfter("Perşembe 13:30", "'de")).toBe("'da");
    expect(harmoniseAfter("A 204", " dersliğinde")).toBe(" dersliğinde");
  });
});
