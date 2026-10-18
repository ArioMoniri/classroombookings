import { describe, expect, it } from "vitest";
import { makeChartFormat } from "./chart-format";
import { csvFilename, tableModel, toCsv, type ChartColumn } from "./chart-csv";

type Row = { day: string; chat: number; share: number; note: string };
const rows: Row[] = [
  { day: "2026-10-13", chat: 37120.5, share: 0.42, note: "normal" },
  { day: "2026-10-14", chat: 82300, share: 0.86, note: "=SUM(A1)" },
  { day: "2026-10-15", chat: 1200, share: 0.1, note: 'with "quote"; and sep' },
];
const columns: ChartColumn<Row>[] = [
  { key: "day", label: "Gün", kind: "date" },
  { key: "chat", label: "Sohbet", kind: "number" },
  { key: "share", label: "Pay", kind: "percent" },
  { key: "note", label: "Not", kind: "text" },
];

describe("toCsv", () => {
  it("tr: UTF-8 BOM, `;` separator, decimal comma, ISO date column, CRLF", () => {
    const csv = toCsv(rows, columns, "tr");
    expect(csv.startsWith("﻿")).toBe(true);
    const lines = csv.slice(1).split("\r\n");
    expect(lines[0]).toBe("Gün;Gün (ISO);Sohbet;Pay (%);Not");
    expect(lines[1]).toBe("13 Ekim Salı;2026-10-13;37120,5;42;normal");
    expect(lines[2]).toBe("14 Ekim Çarşamba;2026-10-14;82300;86;'=SUM(A1)");
    expect(lines[3]).toBe('15 Ekim Perşembe;2026-10-15;1200;10;"with ""quote""; and sep"');
    expect(lines).toHaveLength(4);
  });

  it("en: `,` separator and decimal point", () => {
    const lines = toCsv(rows, columns, "en").slice(1).split("\r\n");
    expect(lines[0]).toBe("Gün,Gün (ISO),Sohbet,Pay (%),Not");
    expect(lines[1]).toBe("\"Tuesday, October 13\",2026-10-13,37120.5,42,normal");
  });

  it("names the file after the chart and its range", () => {
    expect(csvFilename("ai-daily-tokens", "2026-09-17", "2026-10-16")).toBe("smartsched-ai-daily-tokens-2026-09-17_2026-10-16.csv");
    expect(csvFilename("Günlük Token!")).toBe("smartsched-gunluk-token.csv");
  });
});

describe("tableModel (the table twin) matches the CSV rows", () => {
  it("has one body row per CSV data row, in the same order, formatted for reading", () => {
    const f = makeChartFormat("tr");
    const model = tableModel(rows, columns, f);
    const csvLines = toCsv(rows, columns, "tr").slice(1).split("\r\n").slice(1);
    expect(model.head).toEqual(["Gün", "Sohbet", "Pay", "Not"]);
    expect(model.body).toHaveLength(csvLines.length);
    model.body.forEach((cells, i) => {
      expect(csvLines[i]!.startsWith(cells[0]!)).toBe(true);
    });
    expect(model.body[1]).toEqual(["14 Ekim Çarşamba", "82.300", "%86", "=SUM(A1)"]);
  });

  it("marks the unfinished last row", () => {
    const model = tableModel(rows, columns, makeChartFormat("tr"), { partialLast: "(eksik)" });
    expect(model.body[2]![0]).toBe("15 Ekim Perşembe (eksik)");
    expect(model.body[1]![0]).toBe("14 Ekim Çarşamba");
  });
});
