"use client";

import { Lock, MoveRight, Unlock } from "lucide-react";
import { StatusBadge } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, periodRangeLabel } from "@/lib/time";
import { STATUS_TO_KIND, type GridEvent, type GridModel } from "./use-grid-model";

const STATUS_LABEL: Record<GridEvent["status"], MessageKey> = { ok: "grid.ok", locked: "grid.locked", conflict: "grid.conflict", warning: "grid.capacityWarning", block: "grid.block", tip: "grid.tip", pc: "grid.pc" };

export function EventSheet({ event, model, onClose, onMove, onToggleLock, readOnly }: { event: GridEvent | null; model: GridModel; onClose: () => void; onMove: (e: GridEvent) => void; onToggleLock: (e: GridEvent) => void; readOnly: boolean }) {
  const { t, locale } = useI18n();
  const room = event ? model.roomById.get(event.roomId) : undefined;
  const a = event?.assignment ?? null;
  const fit = event && room ? Math.round((event.size / Math.max(1, room.capacity)) * 100) : 0;
  return (
    <Sheet open={event !== null} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="right" className="w-full sm:max-w-[420px]" data-testid="event-sheet">
        {event ? (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2"><span className="font-mono">{event.label}</span><StatusBadge kind={STATUS_TO_KIND[event.status]} label={t(STATUS_LABEL[event.status])} /></SheetTitle>
              <SheetDescription>{a ? `${a.program_name ?? ""}${a.instructor ? ` · ${a.instructor}` : ""}` : event.block?.source ?? ""}</SheetDescription>
            </SheetHeader>
            <div className="space-y-4 px-4">
              {a && !readOnly ? (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => onToggleLock(event)} data-testid="sheet-lock">{a.is_locked ? <><Unlock /> {t("grid.unlockEvent")}</> : <><Lock /> {t("grid.lockEvent")}</>}</Button>
                  <Button size="sm" onClick={() => onMove(event)} disabled={a.is_locked} data-testid="sheet-move"><MoveRight /> {t("grid.move")}…</Button>
                </div>
              ) : null}
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">{t("grid.room")}</dt><dd className="font-mono">{room?.display_name} <span className="text-muted-foreground">· {room?.capacity} {t("common.seats")}</span></dd>
                <dt className="text-muted-foreground">{t("grid.time")}</dt><dd>{dayName(event.day, locale)} · P{event.startPeriod}–P{event.endPeriod} · {periodRangeLabel(event.startPeriod, event.endPeriod)}</dd>
                {a ? (
                  <>
                    <dt className="text-muted-foreground">{t("grid.size")}</dt>
                    <dd>
                      <span className="tabular-nums">{a.size} / {room?.capacity}</span>
                      <span className="mt-1 block h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden><span className="block h-full" style={{ width: `${Math.min(100, fit)}%`, background: fit > 100 ? "var(--status-infeasible-solid)" : fit > 75 ? "var(--seq-5)" : fit > 50 ? "var(--seq-4)" : "var(--seq-3)" }} /></span>
                    </dd>
                    <dt className="text-muted-foreground">{t("grid.program")}</dt><dd>{a.program_name ?? "—"}</dd>
                    <dt className="text-muted-foreground">{t("grid.instructor")}</dt><dd>{a.instructor ?? "—"}</dd>
                    <dt className="text-muted-foreground">Origin</dt><dd><Badge variant="outline">{a.origin}</Badge></dd>
                    {a.conflict_reason ? <><dt className="text-muted-foreground">{t("grid.conflict")}</dt><dd className="text-status-infeasible-fg">{a.conflict_reason}</dd></> : null}
                  </>
                ) : event.block ? (
                  <><dt className="text-muted-foreground">{t("requests.weeks")}</dt><dd>{event.block.weeks.length === 14 ? "1–14" : event.block.weeks.join(", ")}</dd></>
                ) : null}
              </dl>
              {room?.tags.length ? <div className="flex gap-1">{room.tags.map((tg) => <Badge key={tg} variant="outline">{tg}</Badge>)}</div> : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
