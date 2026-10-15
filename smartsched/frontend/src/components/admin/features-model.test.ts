import { describe, expect, it } from "vitest";
import { changedCells, parseOptions, readValue, templateCsv, valueLabel } from "./features-model";

const yesNo = { id: 1, name: "Projeksiyon", kind: "BOOLEAN" as const, options: [], unit: null };
const pcs = { id: 2, name: "PC sayısı", kind: "NUMBER" as const, options: [], unit: "adet" };
const seating = { id: 3, name: "Oturma düzeni", kind: "SELECT" as const, options: [{ id: 30, value: "SINIF DÜZENİ" }, { id: 31, value: "U; düzen" }], unit: null };
const av = { id: 4, name: "Donanım", kind: "MULTISELECT" as const, options: [{ id: 40, value: "Mikrofon" }, { id: 41, value: "Kayıt" }], unit: null };

describe("typed feature values", () => {
  it("reads the backend's typed values", () => {
    expect(readValue(yesNo, true)).toBe(true);
    expect(readValue(pcs, "4,5")).toBe(4.5);
    expect(readValue(seating, 30)).toBe(30);
    expect(readValue(av, [41, 40])).toEqual([41, 40]);
  });
  it("labels values like a person writes them", () => {
    const w = { yes: "evet", no: "hayır" };
    expect(valueLabel(yesNo, false, w)).toBe("hayır");
    expect(valueLabel(pcs, 4.5, w)).toBe("4,5");
    expect(valueLabel(av, [40, 41], w)).toBe("Mikrofon; Kayıt");
  });
  it("sends only the changed cells", () => {
    expect(changedCells([yesNo, pcs], { "1": true, "2": 20 }, { "1": true, "2": 24 })).toEqual({ "2": 24 });
  });
  it("writes a ';' template with a BOM, quoting cells that contain ';'", () => {
    const csv = templateCsv([{ code: "A101", fields: { "1": true, "2": 20, "3": 31 } }], [yesNo, pcs, seating]);
    expect(csv.startsWith("﻿kod;Projeksiyon;PC sayısı;Oturma düzeni\r\n")).toBe(true);
    expect(csv).toContain('A101;evet;20;"U; düzen"\r\n');
  });
  it("parses options one per line without duplicates", () => {
    expect(parseOptions("Sınıf\nsınıf\n U düzeni \n")).toEqual(["Sınıf", "U düzeni"]);
    expect(parseOptions("a, b")).toEqual(["a", "b"]);
  });
});
