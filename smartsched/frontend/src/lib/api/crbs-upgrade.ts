/**
 * Legacy classroombookings upgrade (P18-LEGACY): `POST /crbs-upgrade`, backend `app/api/v1/crbs_upgrade.py`.
 *
 * Multipart form: `files` (one or more SQL dumps / CRBS install scripts) **or** `dsn` (a live `mysql://` DSN,
 * read-only, administrators and allow-listed hosts only: `crbs_dsn.check_dsn`), `confirm` (default false) and,
 * with `confirm`, the `fingerprint` of the reviewed dry run. The whole endpoint needs `planning.admin`.
 *
 * - dry run (`confirm` false): the mapping runs inside a transaction that is rolled back; the report lists
 *   per SmartSched table the rows before / after, the importer's counts and warnings, and the CRBS source counts.
 * - commit (`confirm` true + `fingerprint`): the same mapping for real; a source that changed since the dry run
 *   answers 409 (run the dry run again). A term being written by another job answers 409 / 423 (term lock).
 */
import { z } from "zod";
import { request } from "./client";

const Count = z.record(z.string(), z.number());
const TableDiff = z.object({ before: z.number(), after: z.number(), delta: z.number() });

export const UpgradeReport = z.object({
  dry_run: z.boolean(),
  fingerprint: z.string(),
  source: Count.default({}),
  tables: z.record(z.string(), TableDiff).default({}),
  changed: z.record(z.string(), TableDiff).default({}),
  rows_new: z.number().default(0),
  importer: z
    .object({
      created: Count.default({}),
      updated: Count.default({}),
      rows_skipped_count: z.number().default(0),
      skip_reasons: Count.default({}),
      extra: z.record(z.string(), z.unknown()).default({}),
    })
    .partial()
    .default({}),
  warnings: z.array(z.string()).default([]),
});
export type UpgradeReport = z.infer<typeof UpgradeReport>;

export type UpgradeSource = { kind: "dump"; files: File[] } | { kind: "dsn"; dsn: string };

/** `.sql` / `.txt`, as the backend accepts (`_SQL_TYPES`) */
export const SQL_DUMP = /\.(sql|txt)$/i;

function form(source: UpgradeSource, confirm: boolean, fingerprint?: string): FormData {
  const fd = new FormData();
  if (source.kind === "dump") for (const f of source.files) fd.append("files", f);
  else fd.append("dsn", source.dsn.trim());
  fd.append("confirm", confirm ? "true" : "false");
  if (confirm && fingerprint) fd.append("fingerprint", fingerprint);
  return fd;
}

export const crbsUpgrade = {
  /** map the CRBS database and report the diff; nothing is written */
  dryRun: (source: UpgradeSource, signal?: AbortSignal) => request("/crbs-upgrade", { method: "POST", formData: form(source, false), schema: UpgradeReport, silent: true, signal }),
  /** import for real what the dry run with `fingerprint` showed */
  commit: (source: UpgradeSource, fingerprint: string, signal?: AbortSignal) =>
    request("/crbs-upgrade", { method: "POST", formData: form(source, true, fingerprint), schema: UpgradeReport, silent: true, signal }),
};

/** the "user-facing" summary: tables that change, largest first */
export function changedTables(rep: UpgradeReport): { table: string; before: number; after: number; delta: number }[] {
  return Object.entries(rep.changed)
    .map(([table, d]) => ({ table, ...d }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta) || a.table.localeCompare(b.table));
}

/** importer counts per entity (created + updated), entities with any change only */
export function importerRows(rep: UpgradeReport): { entity: string; created: number; updated: number }[] {
  const created = rep.importer.created ?? {};
  const updated = rep.importer.updated ?? {};
  const keys = [...new Set([...Object.keys(created), ...Object.keys(updated)])];
  return keys
    .map((entity) => ({ entity, created: created[entity] ?? 0, updated: updated[entity] ?? 0 }))
    .filter((r) => r.created || r.updated)
    .sort((a, b) => b.created + b.updated - (a.created + a.updated) || a.entity.localeCompare(b.entity));
}
