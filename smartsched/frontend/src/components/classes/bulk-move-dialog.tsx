"use client";
/**
 * Bulk "Taşı…" (all-classes.md §10): target room / day / shift by ±n periods, a server dry run listing
 * "28 uygun · 3 çakışma" with per-row reasons, then "28'ini taşı" (the fitting ones, one undo entry).
 */
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { calendarApi, type BulkMoveOut, type MoveItem } from "@/lib/api/calendar";
import type { ClassRow } from "@/lib/api/classes";
import { useRooms } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS_PER_DAY, dayName } from "@/lib/time";

export function BulkMoveDialog({ open, onOpenChange, rows, runId, onApply }: { open: boolean; onOpenChange: (o: boolean) => void; rows: ClassRow[]; runId: number | null; onApply: (items: MoveItem[]) => Promise<boolean> }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const rooms = useRooms();
  const [room, setRoom] = useState<number | null>(null);
  const [day, setDay] = useState<number | null>(null);
  const [shift, setShift] = useState(0);
  const [preview, setPreview] = useState<BulkMoveOut | null>(null);
  const [busy, setBusy] = useState(false);
  const movable = rows.filter((r) => r.placement && r.placement.assignment_ids.length);
  const items = useMemo<MoveItem[]>(
    () =>
      movable.map((r) => {
        const p = r.placement!;
        const sp = Math.min(PERIODS_PER_DAY, Math.max(1, p.start_period + shift));
        return { aid: p.assignment_ids[0], day: day ?? p.day, start_period: sp, end_period: Math.min(PERIODS_PER_DAY, sp + (p.end_period - p.start_period)), room_ids: room !== null ? [room] : p.room_ids, scope: "all" };
      }),
    [movable, shift, day, room],
  );
  const check = async () => {
    if (runId === null || !items.length) return;
    setBusy(true);
    try {
      setPreview(await calendarApi.bulkMove(runId, { moves: items, dry_run: true }));
    } finally {
      setBusy(false);
    }
  };
  const okItems = preview ? items.filter((it) => preview.items.find((x) => x.aid === it.aid)?.ok) : [];
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setPreview(null); }}>
      <DialogContent className="sm:max-w-[560px]" data-testid="bulk-move-dialog">
        <DialogHeader>
          <DialogTitle>{t("classes.bulkMove.title", { n: movable.length })}</DialogTitle>
          <DialogDescription>{t("calendar.move.dialogHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
            {t("classes.bulkMove.room")}
            <select className="h-8 rounded-lg bg-fill-2 px-2 text-[13px] font-normal text-label-1" value={room ?? ""} onChange={(e) => { setRoom(e.target.value ? Number(e.target.value) : null); setPreview(null); }}>
              <option value="">{t("classes.bulkMove.keepRoom")}</option>
              {(rooms.data ?? []).filter((r) => r.is_bookable).map((r) => <option key={r.id} value={r.id}>{r.display_name} · {r.capacity}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
            {t("classes.bulkMove.day")}
            <select className="h-8 rounded-lg bg-fill-2 px-2 text-[13px] font-normal text-label-1" value={day ?? ""} onChange={(e) => { setDay(e.target.value ? Number(e.target.value) : null); setPreview(null); }}>
              <option value="">{t("classes.bulkMove.keepDay")}</option>
              {[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{dayName(d, locale)}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
            {t("classes.bulkMove.shift")}
            <input type="number" min={-6} max={6} value={shift} onChange={(e) => { setShift(Number(e.target.value) || 0); setPreview(null); }} className="h-8 rounded-lg bg-fill-2 px-2 text-[13px] font-normal text-label-1 tabular-nums" />
          </label>
        </div>
        {preview ? (
          <div className="flex flex-col gap-2">
            <p className="text-[13px] font-semibold" role="status">{t("classes.bulkMove.preview", { ok: preview.ok_count, bad: preview.conflict_count })}</p>
            <ul className="max-h-56 overflow-y-auto text-[12px]">
              {preview.items.map((it) => (
                <li key={it.aid} className="flex gap-2 py-0.5">
                  <span className={it.ok ? "text-status-feasible-fg" : "text-status-infeasible-fg"} aria-hidden>{it.ok ? "✓" : "✕"}</span>
                  <span className="w-24 shrink-0 font-semibold">{it.label}</span>
                  <span className="min-w-0 flex-1">{it.room_codes.join(" + ")} · {dayName(it.day, locale, "short")} P{it.start_period}–P{it.end_period}{it.hard[0] ? ` — ${it.hard[0].text[lang]}` : it.soft[0] ? ` — ${it.soft[0].text[lang]}` : ""}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("calendar.insp.cancel")}</Button>
          {preview ? (
            <Button disabled={busy || okItems.length === 0} onClick={async () => { setBusy(true); const ok = await onApply(okItems); setBusy(false); if (ok) onOpenChange(false); }} data-testid="bulk-move-apply">
              {t("classes.bulkMove.apply", { n: okItems.length })}
            </Button>
          ) : (
            <Button disabled={busy || !items.length} onClick={() => void check()}>{t("classes.bulkMove.check")}</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
