"use client";

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
  type KeyboardCoordinateGetter,
} from "@dnd-kit/core";
import { AlertTriangle, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useGrid, useLockAssignment, useMoveAssignment, usePrograms } from "@/lib/api/hooks";
import type { Room, RoomTag } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, formatDate, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { AgendaView } from "./agenda-view";
import { DayGrid, ROOM_COL_W } from "./day-grid";
import { EventBody } from "./grid-event";
import { EventSheet } from "./event-sheet";
import { Legend } from "./legend";
import { MoveDialog, reasonLabel, type MoveIntent } from "./move-dialog";
import type { DropTarget } from "./timetable-types";
import { checkMove, useGridModel, type GridEvent } from "./use-grid-model";
import { WeekGrid } from "./week-grid";

export interface TimetableProps {
  runId: number;
  week?: number;
  day?: number;
  zoom?: "day" | "week";
  readOnly?: boolean;
  className?: string;
  onWeekChange?: (week: number) => void;
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [query]);
  return matches;
}

const BUILDINGS = ["A", "B", "C", "D"];
const TAGS: RoomTag[] = ["TIP", "PC"];

export function Timetable({ runId, week: weekProp, day: dayProp, zoom: zoomProp, readOnly = false, className, onWeekChange }: TimetableProps) {
  const { t, locale } = useI18n();
  const reduce = useReducedMotion();
  const [week, setWeek] = useState(weekProp ?? 7);
  const [day, setDay] = useState(dayProp ?? 3);
  const [zoom, setZoom] = useState<"day" | "week">(zoomProp ?? "day");
  const [buildings, setBuildings] = useState<string[]>([]);
  const [tags, setTags] = useState<RoomTag[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<GridEvent | null>(null);
  const [moveFor, setMoveFor] = useState<GridEvent | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [target, setTarget] = useState<DropTarget | null>(null);
  const [announce, setAnnounce] = useState("");
  const isMobile = !useMediaQuery("(min-width: 768px)");
  const density = useUiStore((s) => s.density);
  const highlightIds = useUiStore((s) => s.highlightAssignmentIds);
  const changedIds = useUiStore((s) => s.changedAssignmentIds);
  const setSelectedAssignmentId = useUiStore((s) => s.setSelectedAssignmentId);

  const grid = useGrid(runId, week);
  const programs = usePrograms();
  const move = useMoveAssignment(runId);
  const lock = useLockAssignment(runId);
  const rooms = useMemo(() => grid.data?.rooms ?? [], [grid.data]);
  const model = useGridModel(grid.data, programs.data ?? [], rooms);
  const weeks = grid.data?.weeks ?? [];
  const weekInfo = weeks.find((w) => w.index === week);
  const examWeek = weekInfo?.kind === "EXAM";

  const filteredRooms = useMemo<Room[]>(() => {
    const q = query.trim().toLocaleLowerCase("tr-TR").replace(/\s+/g, "");
    return rooms.filter((r) => (buildings.length === 0 || buildings.includes(r.building_code)) && (tags.length === 0 || tags.some((tg) => r.tags.includes(tg))) && (!q || r.code.toLocaleLowerCase("tr-TR").includes(q) || (model.byRoom.get(r.id) ?? []).some((e) => e.label.toLocaleLowerCase("tr-TR").replace(/\s+/g, "").includes(q))));
  }, [rooms, buildings, tags, query, model.byRoom]);

  const changeWeek = useCallback(
    (next: number) => {
      const clamped = Math.max(1, Math.min(weeks.length || 16, next));
      setWeek(clamped);
      onWeekChange?.(clamped);
    },
    [weeks.length, onWeekChange],
  );

  const highlightSet = useMemo(() => new Set(highlightIds), [highlightIds]);
  const changedSet = useMemo(() => new Set(changedIds), [changedIds]);
  const conflictSet = useMemo(() => new Set(target && !target.ok ? target.conflictIds : []), [target]);

  // Keyboard shortcuts scoped to the grid: [ ] weeks · 1–7 day · d/w zoom
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "[") changeWeek(week - 1);
      else if (e.key === "]") changeWeek(week + 1);
      else if (/^[1-7]$/.test(e.key) && zoom === "day") setDay(Number(e.key));
      else if (e.key === "d") setZoom("day");
      else if (e.key === "w") setZoom("week");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [week, zoom, changeWeek]);

  const keyboardCoordinates: KeyboardCoordinateGetter = (event, { currentCoordinates }) => {
    const rowH = density === "compact" ? 28 : 40;
    switch (event.code) {
      case "ArrowRight": return { ...currentCoordinates, x: currentCoordinates.x + ROOM_COL_W };
      case "ArrowLeft": return { ...currentCoordinates, x: currentCoordinates.x - ROOM_COL_W };
      case "ArrowDown": return { ...currentCoordinates, y: currentCoordinates.y + rowH };
      case "ArrowUp": return { ...currentCoordinates, y: currentCoordinates.y - rowH };
      default: return undefined;
    }
  };
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: keyboardCoordinates, keyboardCodes: { start: ["Space"], cancel: ["Escape"], end: ["Space", "Enter"] } }),
  );

  const activeEvent = activeId ? model.events.find((e) => e.id === activeId) ?? null : null;

  const onDragStart = (e: DragStartEvent) => {
    setActiveId(String(e.active.id));
    setTarget(null);
  };
  const onDragOver = (e: DragOverEvent) => {
    const data = e.over?.data.current as { roomId: number; day: number; period: number } | undefined;
    const ev = model.events.find((x) => x.id === String(e.active.id));
    if (!data || !ev) {
      setTarget(null);
      return;
    }
    const check = checkMove(model, ev, { roomId: data.roomId, day: data.day, startPeriod: data.period });
    setTarget({ roomId: data.roomId, day: data.day, startPeriod: data.period, endPeriod: data.period + (ev.endPeriod - ev.startPeriod), ok: check.ok, reasons: check.reasons, conflictIds: check.conflictIds });
  };
  const onDragEnd = (e: DragEndEvent) => {
    const ev = model.events.find((x) => x.id === String(e.active.id));
    const tgt = target;
    setActiveId(null);
    setTarget(null);
    if (!ev || !tgt || !e.over) return;
    if (tgt.roomId === ev.roomId && tgt.day === ev.day && tgt.startPeriod === ev.startPeriod) return;
    if (!tgt.ok) {
      const labels = tgt.conflictIds.map((id) => model.events.find((x) => x.id === id)?.label).filter(Boolean).join(", ");
      toast.error(t("grid.moveFailed", { reason: `${tgt.reasons.map(reasonLabel).join(", ")}${labels ? ` (${labels})` : ""}` }));
      return;
    }
    void commitMove(ev, { roomId: tgt.roomId, day: tgt.day, startPeriod: tgt.startPeriod, endPeriod: tgt.endPeriod });
  };

  const commitMove = async (ev: GridEvent, intent: MoveIntent) => {
    const a = ev.assignment;
    if (!a) return;
    const roomName = model.roomById.get(intent.roomId)?.display_name ?? "?";
    try {
      const res = await move.mutateAsync({ assignmentId: a.id, body: { room_ids: [intent.roomId], day: intent.day, start_period: intent.startPeriod, end_period: intent.endPeriod, week: a.week } });
      if (res.ok) {
        const msg = t("grid.moved", { label: ev.label, room: roomName, range: `${dayName(intent.day, locale, "short")} ${periodRangeLabel(intent.startPeriod, intent.endPeriod)}` });
        setAnnounce(msg);
        toast.success(msg, {
          description: res.soft_score !== null && res.soft_score !== undefined ? `Soft ${res.soft_score}` : undefined,
          action: { label: t("common.undo"), onClick: () => void move.mutateAsync({ assignmentId: a.id, body: { room_ids: a.room_ids, day: a.day, start_period: a.start_period, end_period: a.end_period, week: a.week } }) },
          duration: 8000,
        });
        setMoveFor(null);
      } else {
        toast.error(t("grid.moveFailed", { reason: res.conflicts.map((c) => c.message).join("; ") }));
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "error";
      toast.error(t("grid.moveFailed", { reason: detail }));
    }
  };

  const toggleLock = async (ev: GridEvent) => {
    if (!ev.assignment) return;
    const res = await lock.mutateAsync({ assignmentId: ev.assignment.id, locked: !ev.assignment.is_locked });
    toast.success(`${ev.label} · ${res.is_locked ? t("common.locked") : t("common.unlock")}`);
  };

  const openEvent = (ev: GridEvent) => {
    setSelected(ev);
    setSelectedAssignmentId(ev.assignment?.id ?? null);
  };
  const onKeyAction = (ev: GridEvent, key: string) => {
    if (key === "l") void toggleLock(ev);
    if (key === "m" && ev.assignment && !ev.locked) setMoveFor(ev);
  };

  const announcements = {
    onDragStart: ({ active }: { active: { id: string | number } }) => {
      const ev = model.events.find((x) => x.id === String(active.id));
      return ev ? (locale === "tr" ? `${ev.label} alındı. Bırakmak için Boşluk.` : `${ev.label} picked up. Press Space to drop.`) : "";
    },
    onDragOver: ({ active }: { active: { id: string | number } }) => {
      const ev = model.events.find((x) => x.id === String(active.id));
      if (!ev || !target) return "";
      const room = model.roomById.get(target.roomId)?.display_name ?? "";
      return locale === "tr" ? `${ev.label} ${room}, ${dayName(target.day, "tr")} P${target.startPeriod} üzerinde. ${target.ok ? "Uygun" : "Çakışma"}.` : `${ev.label} over ${room}, ${dayName(target.day, "en")} P${target.startPeriod}. ${target.ok ? "Free" : "Conflict"}.`;
    },
    onDragEnd: () => announce,
    onDragCancel: () => (locale === "tr" ? "Taşıma iptal edildi." : "Move cancelled."),
  };

  const issues = model.conflicts + model.warnings;

  return (
    <div className={cn("flex min-h-0 flex-col rounded-xl border bg-card", className)} data-testid="timetable">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" aria-label={t("grid.prevWeek")} onClick={() => changeWeek(week - 1)} data-testid="week-prev"><ChevronLeft /></Button>
          <div className="min-w-[110px] text-center text-sm">
            <span className="font-mono font-semibold" data-testid="week-label">W{week}</span>
            {weekInfo ? <span className="block text-[11px] text-muted-foreground">{formatDate(weekInfo.start_date, locale)}{weekInfo.kind !== "LECTURE" ? ` · ${weekInfo.kind}` : ""}</span> : null}
          </div>
          <Button variant="outline" size="icon-sm" aria-label={t("grid.nextWeek")} onClick={() => changeWeek(week + 1)} data-testid="week-next"><ChevronRight /></Button>
        </div>
        {zoom === "day" ? (
          <div role="radiogroup" aria-label={t("grid.day")} className="flex rounded-md border p-0.5">
            {[1, 2, 3, 4, 5, 6, 7].map((d) => {
              const empty = !model.events.some((e) => e.day === d);
              return (
                <button key={d} type="button" role="radio" aria-checked={day === d} onClick={() => setDay(d)} data-testid={`day-${d}`} className={cn("rounded-sm px-2 py-0.5 text-xs", day === d ? "bg-primary text-primary-foreground" : empty ? "text-muted-foreground/60" : "text-muted-foreground hover:text-foreground")}>
                  {dayName(d, locale, "short")}
                </button>
              );
            })}
          </div>
        ) : null}
        {!isMobile ? (
          <div role="radiogroup" aria-label="Zoom" className="inline-flex rounded-md border p-0.5 text-xs">
            {(["day", "week"] as const).map((z) => (
              <button key={z} type="button" role="radio" aria-checked={zoom === z} onClick={() => setZoom(z)} data-testid={`zoom-${z}`} className={cn("rounded-sm px-2 py-0.5", zoom === z ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>{t(z === "day" ? "grid.zoomDay" : "grid.zoomWeek")}</button>
            ))}
          </div>
        ) : null}
        <div className="flex gap-1" role="group" aria-label={t("grid.building")}>
          {BUILDINGS.map((b) => (
            <button key={b} type="button" aria-pressed={buildings.includes(b)} onClick={() => setBuildings((s) => (s.includes(b) ? s.filter((x) => x !== b) : [...s, b]))} className={cn("rounded-full border px-2 py-0.5 text-xs", buildings.includes(b) ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{b}</button>
          ))}
          {TAGS.map((tg) => (
            <button key={tg} type="button" aria-pressed={tags.includes(tg)} onClick={() => setTags((s) => (s.includes(tg) ? s.filter((x) => x !== tg) : [...s, tg]))} className={cn("rounded-full border px-2 py-0.5 text-xs", tags.includes(tg) ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{tg}</button>
          ))}
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label={t("grid.search")} placeholder={t("grid.search")} value={query} onChange={(e) => setQuery(e.target.value)} className="h-7 w-36 pl-7 text-xs" />
        </div>
        <div className="ml-auto flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger render={<span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs", issues > 0 ? "border-status-infeasible-border bg-status-infeasible text-status-infeasible-fg" : "border-status-feasible-border bg-status-feasible text-status-feasible-fg")} data-testid="issues-pill"><AlertTriangle className="size-3.5" aria-hidden />{model.conflicts} {t("grid.conflict").toLocaleLowerCase(locale)} · {model.warnings} {t("grid.capacityWarning").toLocaleLowerCase(locale)}</span>} />
            <TooltipContent>{t("grid.roomsShown", { count: filteredRooms.length })}</TooltipContent>
          </Tooltip>
          <Legend />
        </div>
      </div>
      <div className="relative min-h-0 flex-1" style={{ minHeight: 320 }}>
        {grid.isLoading ? (
          <div className="grid h-full grid-cols-[72px_repeat(6,1fr)] gap-0.5 p-2" aria-busy>{Array.from({ length: 7 * 10 }, (_, i) => <Skeleton key={i} className="h-9" />)}</div>
        ) : grid.isError ? (
          <div className="p-6 text-sm text-status-infeasible-fg">{t("common.error")} <Button size="sm" variant="outline" onClick={() => void grid.refetch()}>{t("common.retry")}</Button></div>
        ) : isMobile ? (
          <AgendaView model={model} rooms={filteredRooms} day={day} onOpen={openEvent} onMove={(e) => setMoveFor(e)} readOnly={readOnly} />
        ) : zoom === "week" ? (
          <WeekGrid model={model} rooms={filteredRooms} onPickDay={(d) => { setDay(d); setZoom("day"); }} onOpen={openEvent} selectedId={selected?.id ?? null} />
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={onDragStart} onDragOver={onDragOver} onDragEnd={onDragEnd} onDragCancel={() => { setActiveId(null); setTarget(null); }} accessibility={{ announcements }}>
            <DayGrid model={model} rooms={filteredRooms} day={day} target={target} isDragging={activeId !== null} activeId={activeId} selectedId={selected?.id ?? null} highlightIds={highlightSet} changedIds={changedSet} conflictIds={conflictSet} compact={density === "compact"} readOnly={readOnly} examWeek={examWeek} onOpen={openEvent} onKeyAction={onKeyAction} />
            <DragOverlay dropAnimation={reduce ? null : { duration: 240, easing: "cubic-bezier(0.16, 1, 0.3, 1)" }}>
              {activeEvent ? <EventBody event={activeEvent} roomName={model.roomById.get(activeEvent.roomId)?.display_name ?? ""} className="shadow-elev-2 scale-[1.02]" style={{ width: ROOM_COL_W - 2, height: (activeEvent.endPeriod - activeEvent.startPeriod + 1) * (density === "compact" ? 28 : 40) - 2 }} compact={density === "compact"} /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>
      <p className="sr-only" aria-live="polite">{announce}</p>
      <EventSheet event={selected} model={model} onClose={() => { setSelected(null); setSelectedAssignmentId(null); }} onMove={(e) => { setSelected(null); setMoveFor(e); }} onToggleLock={(e) => void toggleLock(e)} readOnly={readOnly} />
      <MoveDialog event={moveFor} model={model} open={moveFor !== null} onOpenChange={(o) => { if (!o) setMoveFor(null); }} onConfirm={(intent) => { if (moveFor) void commitMove(moveFor, intent); }} pending={move.isPending} />
    </div>
  );
}
