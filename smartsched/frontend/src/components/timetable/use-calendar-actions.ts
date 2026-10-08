"use client";
/**
 * Mutations shared by drag, keyboard move, the Move dialog, the inspector and the /classes bulk bar.
 * Every move is one undo entry (calendar.md §9.10) whose inverse restores the exact previous rows through
 * `POST …/assignments/restore`; the cached index is patched in place (no 1–3 MB refetch per move).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef } from "react";
import { toast } from "sonner";
import { HttpError } from "@/lib/api/client";
import { calendarApi, calKeys, patchIndex, type BulkMoveOut, type CalendarIndex, type IndexAssignment, type MoveItem, type UndoToken } from "@/lib/api/calendar";
import { useI18n } from "@/lib/i18n/provider";
import { useUndoStore } from "./model/undo-store";

export interface MoveOutcome {
  ok: boolean;
  applied: boolean;
  reason?: string;
  result?: BulkMoveOut;
}

function restoreLocally(index: CalendarIndex, undo: UndoToken): CalendarIndex {
  const snaps = new Map(undo.snapshots.map((s) => [s.id, s]));
  const gone = new Set(undo.delete_ids);
  const rows: IndexAssignment[] = [];
  for (const a of index.assignments) {
    if (gone.has(a.id)) continue;
    const s = snaps.get(a.id);
    rows.push(s ? { ...a, day: s.day, sp: s.start_period, ep: s.end_period, rooms: s.room_ids, weeks: s.weeks.length ? s.weeks : s.week ? [s.week] : a.weeks, locked: s.is_locked, origin: s.origin } : a);
  }
  return { ...index, assignments: rows };
}

export function useCalendarActions(runId: number | null, opts: { isAdmin?: boolean; announce?: (msg: string) => void } = {}) {
  const qc = useQueryClient();
  const { t, locale } = useI18n();
  const push = useUndoStore((s) => s.push);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lang = locale === "tr" ? "tr" : "en";

  const setIndex = useCallback(
    (fn: (old: CalendarIndex) => CalendarIndex) => {
      if (runId === null) return;
      qc.setQueryData<CalendarIndex>(calKeys.index(runId), (old) => (old ? fn(old) : old));
    },
    [qc, runId],
  );

  /** Conflict flags of *other* rows (the old clash partner) refresh quietly a moment later. */
  const refreshSoon = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      if (runId !== null) void qc.invalidateQueries({ queryKey: calKeys.index(runId) });
      void qc.invalidateQueries({ queryKey: ["classes"] });
      void qc.invalidateQueries({ queryKey: ["class-detail"] });
      void qc.invalidateQueries({ queryKey: ["calendar-heat"] });
    }, 1500);
  }, [qc, runId]);

  const reasonOf = useCallback((r: BulkMoveOut): string => {
    const bad = r.items.find((i) => i.hard.length);
    return bad ? bad.hard.map((h) => h.text[lang]).join("; ") : "";
  }, [lang]);

  const move = useCallback(
    async function run(items: MoveItem[], label: string, toRoom: string, force = false): Promise<MoveOutcome> {
      if (runId === null || items.length === 0) return { ok: false, applied: false };
      let res: BulkMoveOut;
      try {
        res = await calendarApi.bulkMove(runId, { moves: items, atomic: true, force });
      } catch (e) {
        const reason = e instanceof HttpError ? (e.status === 403 ? t("calendar.move.forceAdmin") : e.message) : String(e);
        toast.error(t("calendar.move.cannot", { reason }));
        return { ok: false, applied: false, reason };
      }
      if (!res.applied) {
        const reason = reasonOf(res);
        toast.error(t("calendar.move.cannot", { reason }), {
          description: opts.isAdmin ? undefined : t("calendar.move.forceAdmin"),
          action: opts.isAdmin ? { label: t("calendar.move.force"), onClick: () => void run(items, label, toRoom, true) } : undefined,
          duration: 8000,
        });
        opts.announce?.(t("calendar.move.cannot", { reason }));
        return { ok: false, applied: false, reason, result: res };
      }
      setIndex((old) => patchIndex(old, res.assignments));
      refreshSoon();
      const undo = res.undo;
      const msg = items.length === 1 ? t("calendar.toast.moved", { code: label, room: toRoom }) : t("calendar.toast.movedMany", { n: items.length });
      let current = undo;
      push({
        label: msg,
        inverse: async () => {
          await calendarApi.restore(runId, current);
          setIndex((old) => restoreLocally(old, current));
          refreshSoon();
        },
        forward: async () => {
          const again = await calendarApi.bulkMove(runId, { moves: items, atomic: true, force });
          if (!again.applied) throw new Error(reasonOf(again));
          current = again.undo;
          setIndex((old) => patchIndex(old, again.assignments));
          refreshSoon();
        },
      });
      opts.announce?.(msg);
      toast.success(msg, {
        duration: 6000,
        action: {
          label: t("calendar.toast.undo"),
          onClick: () => {
            void useUndoStore
              .getState()
              .undo()
              .then((e) => e && toast(t("calendar.toast.undone", { label: e.label })))
              .catch((err: unknown) => toast.error(t("calendar.toast.undoFailed", { reason: err instanceof Error ? err.message : String(err) })));
          },
        },
      });
      return { ok: res.ok, applied: true, result: res };
    },
    [runId, t, reasonOf, opts, setIndex, refreshSoon, push],
  );

  const lock = useCallback(
    async (ids: number[], locked: boolean, label: string) => {
      if (runId === null || ids.length === 0) return false;
      const apply = async (value: boolean) => {
        await calendarApi.bulkLock(runId, ids, value);
        setIndex((old) => ({ ...old, assignments: old.assignments.map((a) => (ids.includes(a.id) ? { ...a, locked: value } : a)) }));
        void qc.invalidateQueries({ queryKey: ["classes"] });
      };
      try {
        await apply(locked);
      } catch (err) {
        toast.error(t("calendar.toast.lockFailed", { reason: err instanceof Error ? err.message : String(err) }));
        return false;
      }
      const msg = ids.length > 1 ? t("calendar.toast.lockedMany", { n: ids.length }) : t(locked ? "calendar.toast.locked" : "calendar.toast.unlocked", { code: label });
      push({ label: msg, inverse: () => apply(!locked), forward: () => apply(locked) });
      opts.announce?.(msg);
      toast.success(msg, { action: { label: t("calendar.toast.undo"), onClick: () => void useUndoStore.getState().undo() } });
      return true;
    },
    [runId, setIndex, qc, t, push, opts],
  );

  const undo = useCallback(async () => {
    try {
      const e = await useUndoStore.getState().undo();
      if (e) {
        toast(t("calendar.toast.undone", { label: e.label }));
        opts.announce?.(t("calendar.toast.undone", { label: e.label }));
      }
    } catch (err) {
      toast.error(t("calendar.toast.undoFailed", { reason: err instanceof Error ? err.message : String(err) }));
    }
  }, [t, opts]);

  const redo = useCallback(async () => {
    try {
      const e = await useUndoStore.getState().redo();
      if (e) toast(t("calendar.toast.redone", { label: e.label }));
    } catch (err) {
      toast.error(t("calendar.toast.undoFailed", { reason: err instanceof Error ? err.message : String(err) }));
    }
  }, [t]);

  return { move, lock, undo, redo };
}
