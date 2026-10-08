"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api/endpoints";
import { sk } from "@/lib/api/studio-hooks";
import type { ClassPage, ClassRow, MeetingPatch } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { useStudio } from "./studio-context";

/** class-list field → the ClassRow fields it writes (for changed markers and undo) */
export const FIELD_GROUPS = {
  students: ["enrolment"],
  mode: ["mode"],
  dayTime: ["day", "days", "start_period", "end_period", "flexible_day"],
  weeks: ["weeks"],
  rooms: ["requested_room_ids", "requested_building", "requested_tags"],
} as const;
export type FieldGroup = keyof typeof FIELD_GROUPS;

export function changedIn(row: ClassRow, group: FieldGroup): ClassRow["changed_fields"] {
  const fields = FIELD_GROUPS[group] as readonly string[];
  return row.changed_fields.filter((c) => fields.includes(c.field));
}

function applyLocal(row: ClassRow, patch: MeetingPatch): ClassRow {
  const next = { ...row, ...(patch as Partial<ClassRow>) };
  if (patch.locked !== undefined) next.locked = patch.locked;
  if (patch.start_period !== undefined || patch.end_period !== undefined) {
    const s = next.start_period;
    const e = next.end_period;
    next.time_label = s && e ? `${PERIODS[s - 1]?.start ?? ""}-${PERIODS[e - 1]?.end ?? ""}` : null;
  }
  if (patch.day !== undefined) next.days = patch.day ? [patch.day] : [];
  return next;
}

function inverse(row: ClassRow, patch: MeetingPatch): MeetingPatch {
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(patch)) out[k] = k === "locked" ? row.locked : (row as unknown as Record<string, unknown>)[k];
  return out as MeetingPatch;
}

/** Optimistic class edits (write-through to the real meeting/section with an imported snapshot), with
 * rollback on failure, capacity warnings and undo. */
export function useClassEdit() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { termId, kind, store } = useStudio();
  const key = sk.classes(termId, kind);
  const [warnings, setWarnings] = useState<Record<number, string[]>>({});

  const patchCache = useCallback(
    (fn: (rows: ClassRow[]) => ClassRow[]) => qc.setQueryData<ClassPage>(key, (old) => (old ? { ...old, items: fn(old.items) } : old)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [qc, termId, kind],
  );

  const send = useCallback(
    async (items: { id: number; patch: MeetingPatch }[]): Promise<boolean> => {
      const before = qc.getQueryData<ClassPage>(key)?.items ?? [];
      const byId = new Map(before.map((r) => [r.id, r]));
      patchCache((rows) => rows.map((r) => {
        const it = items.find((x) => x.id === r.id);
        return it ? applyLocal(r, it.patch) : r;
      }));
      try {
        const res = await api.studio.bulkEdit({ items });
        const fresh = new Map(res.rows.map((r) => [r.id, r]));
        patchCache((rows) => rows.map((r) => fresh.get(r.id) ?? r));
        const failed = res.results.filter((r) => !r.ok);
        if (failed.length) {
          // roll the failed rows back
          patchCache((rows) => rows.map((r) => (failed.some((f) => f.id === r.id) ? (byId.get(r.id) ?? r) : r)));
          toast.error(t("studio.classes.saveFailed", { reason: failed.flatMap((f) => f.errors).join("; ") }));
        }
        const warn = Object.fromEntries(res.results.filter((r) => r.warnings.length).map((r) => [r.id, r.warnings]));
        setWarnings((w) => {
          const next = { ...w };
          for (const it of items) delete next[it.id];
          return { ...next, ...warn };
        });
        store.getState().touch();
        return failed.length === 0;
      } catch (e) {
        patchCache(() => before);
        toast.error(t("studio.classes.saveFailed", { reason: e instanceof Error ? e.message : String(e) }), {
          action: { label: t("common.retry"), onClick: () => void send(items) },
        });
        return false;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [qc, patchCache, store, t, termId, kind],
  );

  const edit = useCallback(
    async (rows: ClassRow[], patch: MeetingPatch, label?: string) => {
      const items = rows.map((r) => ({ id: r.id, patch }));
      const undoItems = rows.map((r) => ({ id: r.id, patch: inverse(r, patch) }));
      const ok = await send(items);
      if (ok)
        store.getState().record({
          label: label ?? t("studio.history.classEdited"),
          undo: () => send(undoItems),
          redo: () => send(items),
        });
      return ok;
    },
    [send, store, t],
  );

  const revert = useCallback(
    async (row: ClassRow, fields?: readonly string[]) => {
      const current = Object.fromEntries((fields ?? row.changed_fields.map((c) => c.field)).map((f) => [f, (row as unknown as Record<string, unknown>)[f]])) as MeetingPatch;
      const fresh = await api.studio.revert(row.id, fields ? [...fields] : undefined);
      patchCache((rows) => rows.map((r) => (r.id === row.id ? fresh : r)));
      store.getState().record({ label: t("studio.history.reverted"), undo: () => send([{ id: row.id, patch: current }]), redo: () => api.studio.revert(row.id, fields ? [...fields] : undefined).then((r) => patchCache((rows) => rows.map((x) => (x.id === r.id ? r : x)))) });
    },
    [patchCache, send, store, t],
  );

  const revertAll = useCallback(
    async (rows: ClassRow[]) => {
      const fresh = await api.studio.revertMany(rows.map((r) => r.id));
      const byId = new Map(fresh.map((r) => [r.id, r]));
      patchCache((list) => list.map((r) => byId.get(r.id) ?? r));
      store.getState().touch();
      toast.success(t("studio.classes.revertedAll", { n: rows.length }));
    },
    [patchCache, store, t],
  );

  return { edit, revert, revertAll, warnings };
}
