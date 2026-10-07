"use client";

import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { checkMove, type GridEvent, type GridModel } from "./use-grid-model";

export interface MoveIntent {
  roomId: number;
  day: number;
  startPeriod: number;
  endPeriod: number;
}

export function reasonLabel(reason: string): string {
  const map: Record<string, string> = { locked: "locked", out_of_range: "outside P1–P18", unknown_room: "unknown room", not_bookable: "room not bookable", capacity: "capacity too small", tip: "TIP room (medicine only)", overlap: "slot occupied" };
  return map[reason] ?? reason;
}

/** Keyboard/touch alternative to drag-drop with the same live validity feedback. */
export function MoveDialog({ event, model, open, onOpenChange, onConfirm, pending }: { event: GridEvent | null; model: GridModel; open: boolean; onOpenChange: (o: boolean) => void; onConfirm: (intent: MoveIntent) => void; pending: boolean }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="move-dialog">
        {event ? <MoveForm key={event.id} event={event} model={model} onOpenChange={onOpenChange} onConfirm={onConfirm} pending={pending} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function MoveForm({ event, model, onOpenChange, onConfirm, pending }: { event: GridEvent; model: GridModel; onOpenChange: (o: boolean) => void; onConfirm: (intent: MoveIntent) => void; pending: boolean }) {
  const { t, locale } = useI18n();
  const [roomId, setRoomId] = useState<number>(event.roomId);
  const [day, setDay] = useState<number>(event.day);
  const [start, setStart] = useState<number>(event.startPeriod);
  const duration = event.endPeriod - event.startPeriod + 1;
  const check = useMemo(() => checkMove(model, event, { roomId, day, startPeriod: start }), [event, model, roomId, day, start]);
  const unchanged = roomId === event.roomId && day === event.day && start === event.startPeriod;
  const conflictLabels = check.conflictIds.map((id) => model.events.find((e) => e.id === id)?.label).filter(Boolean).join(", ");
  return (
    <>
        <DialogHeader>
          <DialogTitle>{t("grid.moveDialog")} · {event.label}</DialogTitle>
          <DialogDescription>{`${model.roomById.get(event.roomId)?.display_name} · ${dayName(event.day, locale)} ${periodRangeLabel(event.startPeriod, event.endPeriod)}`}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="mv-room">{t("grid.newRoom")}</Label>
            <NativeSelect id="mv-room" value={roomId} onChange={(e) => setRoomId(Number(e.target.value))}>
              {model.rooms.filter((r) => r.is_bookable).map((r) => <option key={r.id} value={r.id}>{r.display_name} · {r.capacity}{r.tags.length ? ` · ${r.tags.join(" ")}` : ""}</option>)}
            </NativeSelect>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="grid gap-1">
              <Label htmlFor="mv-day">{t("grid.newDay")}</Label>
              <NativeSelect id="mv-day" value={day} onChange={(e) => setDay(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{dayName(d, locale)}</option>)}</NativeSelect>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="mv-start">{t("grid.newStart")}</Label>
              <NativeSelect id="mv-start" value={start} onChange={(e) => setStart(Number(e.target.value))}>{PERIODS.filter((p) => p.index + duration - 1 <= 18).map((p) => <option key={p.index} value={p.index}>P{p.index} {p.start}</option>)}</NativeSelect>
            </div>
          </div>
          {check ? (
            <div role="status" className={cn("rounded-md border px-3 py-2 text-sm", check.ok ? "border-status-feasible-border bg-status-feasible text-status-feasible-fg" : "border-status-infeasible-border bg-status-infeasible text-status-infeasible-fg")} data-testid="move-preview">
              <p className="font-medium">{t("grid.preview")}: {model.roomById.get(roomId)?.display_name} · {dayName(day, locale)} {periodRangeLabel(start, start + duration - 1)}</p>
              {!check.ok ? <p className="text-xs">{check.reasons.map(reasonLabel).join(" · ")}{conflictLabels ? ` — ${t("grid.conflictWith", { labels: conflictLabels })}` : ""}</p> : null}
              {check.warnings.length ? <p className="text-xs opacity-80">P12 (30 min) inside span</p> : null}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button disabled={!check.ok || unchanged || pending} onClick={() => onConfirm({ roomId, day, startPeriod: start, endPeriod: start + duration - 1 })} data-testid="move-confirm">
            {pending ? <Loader2 className="animate-spin" /> : null} {t("grid.confirmMove")}
          </Button>
        </DialogFooter>
    </>
  );
}
