/**
 * Typed room features (P10, docs/product/wave1-api.md §2): how a typed value reads in the values grid and the
 * CSV template, and which draft cells changed. Pure functions, unit-tested in features-model.test.ts.
 */
import type { Feature } from "@/lib/api/wave1";

export type FeatureValue = boolean | number | number[] | string | null;

/** A stored value (`AdminRoom.fields[id]`, typed by the backend) for the grid control. */
export function readValue(f: Pick<Feature, "kind">, raw: unknown): FeatureValue {
  if (f.kind === "BOOLEAN") return raw === true || raw === "1" || raw === 1;
  if (f.kind === "NUMBER") return typeof raw === "number" ? raw : typeof raw === "string" && raw.trim() !== "" && !Number.isNaN(Number(raw.replace(",", "."))) ? Number(raw.replace(",", ".")) : null;
  if (f.kind === "SELECT") return typeof raw === "number" ? raw : typeof raw === "string" && /^\d+$/.test(raw) ? Number(raw) : null;
  if (f.kind === "MULTISELECT") return Array.isArray(raw) ? raw.map(Number).filter((x) => !Number.isNaN(x)) : [];
  return typeof raw === "string" ? raw : raw == null ? null : String(raw);
}

/** Human text (CSV template, read-only cells): yes/no words, option texts, numbers as typed. */
export function valueLabel(f: Pick<Feature, "kind" | "options" | "unit">, v: FeatureValue, words: { yes: string; no: string }): string {
  if (f.kind === "BOOLEAN") return v === true ? words.yes : words.no;
  if (v === null || v === "" || (Array.isArray(v) && v.length === 0)) return "";
  if (f.kind === "SELECT") return f.options.find((o) => o.id === v)?.value ?? "";
  if (f.kind === "MULTISELECT") return (v as number[]).map((id) => f.options.find((o) => o.id === id)?.value).filter(Boolean).join("; ");
  if (f.kind === "NUMBER") return String(v).replace(".", ",");
  return String(v);
}

const same = (a: FeatureValue, b: FeatureValue) => JSON.stringify(a) === JSON.stringify(b);

/** Only the cells that differ from what is stored: `{field id: value}` for `PUT /room-admin/rooms/{id}/features`. */
export function changedCells(features: Pick<Feature, "id" | "kind">[], stored: Record<string, unknown>, draft: Record<string, FeatureValue>): Record<string, FeatureValue> {
  const out: Record<string, FeatureValue> = {};
  for (const f of features) {
    const k = String(f.id);
    if (!(k in draft)) continue;
    if (!same(readValue(f, stored[k]), draft[k] ?? null)) out[k] = draft[k] ?? null;
  }
  return out;
}

function csvCell(s: string, sep: string): string {
  return /["\r\n]/.test(s) || s.includes(sep) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * The bulk-values template: `kod;<feature>;…` then one row per room with its current values (Excel in
 * Turkish opens `;` files directly; a BOM keeps İ/ş/ğ intact). Edit, save, upload: empty cells change nothing.
 */
export function templateCsv(
  rooms: { code: string; fields: Record<string, unknown> }[],
  features: Pick<Feature, "id" | "name" | "kind" | "options" | "unit">[],
  words: { yes: string; no: string } = { yes: "evet", no: "hayır" },
  sep = ";",
): string {
  const head = ["kod", ...features.map((f) => f.name)].map((c) => csvCell(c, sep)).join(sep);
  const lines = rooms.map((r) => [r.code, ...features.map((f) => valueLabel(f, readValue(f, r.fields[String(f.id)]), words))].map((c) => csvCell(c, sep)).join(sep));
  return `﻿${[head, ...lines].join("\r\n")}\r\n`;
}

/** Options typed one per line (or comma separated on one line), trimmed, no duplicates (Turkish case-fold). */
export function parseOptions(text: string): string[] {
  const parts = text.includes("\n") ? text.split("\n") : text.split(",");
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of parts) {
    const v = p.replace(/ /g, " ").trim();
    const k = v.toLocaleLowerCase("tr-TR");
    if (!v || seen.has(k)) continue;
    seen.add(k);
    out.push(v);
  }
  return out;
}
