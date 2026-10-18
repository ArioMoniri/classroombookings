// SmartSched charts (CH-02, docs/design/v3/charts.md §5.5): one column model drives both the table twin and the
// CSV, so the two always hold the same rows. Original work.
import type { Locale } from "@/lib/i18n";
import { makeChartFormat, toDate, type ChartFormat } from "./chart-format";

export type ChartColumnKind = "text" | "number" | "percent" | "date";

export interface ChartColumn<R> {
  key: keyof R & string;
  /** the header, already translated (never a raw key) */
  label: string;
  /** default "text"; "date" values are ISO days, "percent" values are ratios 0…1 */
  kind?: ChartColumnKind;
  /** the display format in the table (defaults per kind); the CSV keeps raw values */
  format?: (value: R[keyof R & string], row: R) => string;
}

/** Excel tr-TR opens `;` with decimal commas; English Excel and machines read `,`. */
export function csvSeparator(locale: Locale): string {
  return locale === "tr" ? ";" : ",";
}

const FORMULA = /^[=+\-@\t\r]/;

function cell(text: string, sep: string): string {
  // quoted when it holds the separator, a quote or a line break
  return /["\r\n]/.test(text) || text.includes(sep) ? `"${text.replace(/"/g, '""')}"` : text;
}

function rawNumber(value: number, locale: Locale): string {
  const text = String(Math.round(value * 1e6) / 1e6);
  return locale === "tr" ? text.replace(".", ",") : text;
}

/**
 * UTF-8 BOM + header + one line per row, CRLF. Dates get a readable column and an ISO column; numbers are raw
 * (no grouping) with the locale's decimal mark; percents are 0…100.
 */
export function toCsv<R>(rows: readonly R[], columns: readonly ChartColumn<R>[], locale: Locale, f: ChartFormat = makeChartFormat(locale)): string {
  const sep = csvSeparator(locale);
  const head: string[] = [];
  for (const c of columns) {
    const kind = c.kind ?? "text";
    if (kind === "date") head.push(c.label, `${c.label} (ISO)`);
    // a label that already names the unit ("Dolu derslik (%)") is not marked twice (e2e 2026-10-18)
    else if (kind === "percent") head.push(/\(%\)\s*$/.test(c.label) ? c.label : `${c.label} (%)`);
    else head.push(c.label);
  }
  const lines = [head.map((h) => cell(h, sep)).join(sep)];
  for (const row of rows) {
    const out: string[] = [];
    for (const c of columns) {
      const value = row[c.key] as unknown;
      const kind = c.kind ?? "text";
      if (kind === "date") {
        const d = toDate(value as string | Date);
        out.push(cell(c.format ? c.format(row[c.key], row) : f.dayLong(d), sep), f.isoDay(d));
      } else if (kind === "number") {
        out.push(typeof value === "number" ? rawNumber(value, locale) : "");
      } else if (kind === "percent") {
        out.push(typeof value === "number" ? rawNumber(value * 100, locale) : "");
      } else {
        const text = c.format ? c.format(row[c.key], row) : String(value ?? "");
        // a text cell that starts like a formula is neutralised (CSV injection)
        out.push(cell(FORMULA.test(text) ? `'${text}` : text, sep));
      }
    }
    lines.push(out.join(sep));
  }
  return `﻿${lines.join("\r\n")}`;
}

/** smartsched-<slug>-<from>_<to>.csv, ASCII only */
export function csvFilename(slug: string, from?: string, to?: string): string {
  const clean = slug
    .toLocaleLowerCase("tr")
    .normalize("NFKD")
    .replace(/ı/g, "i")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const range = from && to ? `-${from}_${to}` : "";
  return `smartsched-${clean}${range}.csv`;
}

export interface TableModel {
  head: string[];
  /** each row: the first cell is the row header */
  body: string[][];
}

/** The table twin's cells: the CSV's rows, formatted for reading (82.300, %86, 14 Ekim Çarşamba). */
export function tableModel<R>(rows: readonly R[], columns: readonly ChartColumn<R>[], f: ChartFormat, opts: { partialLast?: string } = {}): TableModel {
  const body = rows.map((row, i) =>
    columns.map((c, j) => {
      const value = row[c.key] as unknown;
      const kind = c.kind ?? "text";
      let text: string;
      if (c.format) text = c.format(row[c.key], row);
      else if (kind === "date") text = f.dayLong(value as string | Date);
      else if (kind === "number") text = typeof value === "number" ? f.num(value) : "";
      else if (kind === "percent") text = typeof value === "number" ? f.pct(value) : "";
      else text = String(value ?? "");
      return j === 0 && opts.partialLast && i === rows.length - 1 ? `${text} ${opts.partialLast}` : text;
    }),
  );
  return { head: columns.map((c) => c.label), body };
}

/** Hands a text file to the browser (no request; the rows are already here). */
export function downloadText(filename: string, text: string, type = "text/csv;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  downloadUrl(filename, url);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadUrl(filename: string, url: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
