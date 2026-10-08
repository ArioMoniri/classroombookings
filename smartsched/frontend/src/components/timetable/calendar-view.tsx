"use client";
/**
 * Calendar v2 (docs/design/v2/calendar.md): six lenses over one client-side index.
 * Chrome is glass (capsules, sidebar, inspector, scrubber, popovers); content is opaque.
 */
import "./calendar.css";
import { motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { ClassInspector, SelectionSummary } from "@/components/classes/class-inspector";
import { useCalendarIndex } from "@/lib/api/calendar";
import { api } from "@/lib/api/endpoints";
import { useMe } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { AgendaLens } from "./agenda-lens";
import { BoardStrip } from "./board-strip";
import { CalendarSidebar } from "./calendar-sidebar";
import { CapsuleToolbar } from "./capsule-toolbar";
import { DayTimeline } from "./day-timeline";
import { MonthHeat, TermHeat } from "./heat-lenses";
import { MobileCalendar } from "./mobile-calendar";
import { MoveDialog, MovePopover, type PendingMove, type ScopeValue } from "./move-dialog";
import { QuickCreate, type CreateRequest } from "./quick-create";
import { ShortcutsSheet } from "./shortcuts-sheet";
import { TimeGrid, type CreateIntent, type GridColumn, type MoveIntent, type TimeGridHandle } from "./time-grid";
import { checkMove, spanText } from "./model/check";
import { compareRuns } from "./model/compare";
import { dateOf, minutesNow, rangeTitle, todayIso, weekDayOf, weekTypeKey } from "./model/dates";
import { EMPTY_FILTERS, activeFilterCount, eventPasses, queryMatchesRoom, roomPasses, type CalendarFilters } from "./model/filters";
import { BAND_H, MINUTE_PX_STEPS, ROOM_COL, ROOM_HEADER_H, STRIP_SLOT_STEPS, clampZoom, periodAtMinute, rowHeightFor, type Density } from "./model/geometry";
import { computeHeat, weeklyMean, type HeatMetric } from "./model/heat";
import { blocksOf, bookingsOf, eventsOf, roomCap, termLongBlocks, type CalEvent, type CalendarModel } from "./model/index-model";
import { useUndoStore } from "./model/undo-store";
import { lensDirection, lensForKey, parseViewState, serializeViewState, weekInRun, type Lens, type Subject, type ViewState } from "./model/view-state";
import { useCalendarActions } from "./use-calendar-actions";
import { useCalendarData } from "./use-calendar-data";
import { WeekScrubber } from "./week-scrubber";

const ALLDAY_H = 22;

function useMedia(query: string): boolean {
  const [m, setM] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return m;
}

/** Fill the viewport below the element's top edge (the shell owns the page chrome). */
function useFillHeight(ref: React.RefObject<HTMLElement | null>, enabled: boolean): number | undefined {
  const [h, setH] = useState<number | undefined>(undefined);
  useLayoutEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;
    const measure = () => setH(Math.max(420, window.innerHeight - el.getBoundingClientRect().top - 12));
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [ref, enabled]);
  return h;
}

function useNow(): { minutes: number; iso: string } {
  const [now, setNow] = useState(() => ({ minutes: minutesNow(), iso: todayIso() }));
  useEffect(() => {
    // updates every 60 s with no animation (calendar.md §7.4)
    const id = setInterval(() => setNow({ minutes: minutesNow(), iso: todayIso() }), 60_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function subjectKeep(s: Subject | null): ((e: CalEvent) => boolean) | null {
  if (!s) return null;
  if (s.kind === "room") return (e) => e.room === Number(s.id);
  if (s.kind === "instructor") return (e) => e.a.instr_ids.includes(Number(s.id));
  if (s.kind === "cohort") return (e) => e.cohort === s.id;
  return (e) => String(e.a.mr) === s.id || String(e.a.id) === s.id;
}

export interface CalendarViewProps {
  /** run-view embeds the calendar for one run without URL sync or sidebar */
  embedded?: boolean;
  runId?: number;
  initialWeek?: number;
  className?: string;
}

export function CalendarView({ embedded = false, runId: fixedRun, initialWeek, className }: CalendarViewProps) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const router = useRouter();
  const me = useMe();
  const isAdmin = me.data?.role === "ADMIN";
  const readOnly = me.data?.role === "VIEWER";
  const mobile = useMedia("(max-width: 767px)");
  const wide = useMedia("(min-width: 1600px)");
  const desktop = useMedia("(min-width: 1280px)");
  const rootRef = useRef<HTMLDivElement>(null);
  const fill = useFillHeight(rootRef, !embedded);
  const now = useNow();

  // ------------------------------------------------------------------ view state ↔ URL
  const search = useSearchParams();
  const [vs, setVs] = useState<ViewState>(() => {
    const params = !embedded ? new URLSearchParams(search.toString()) : new URLSearchParams();
    const s = parseViewState(params, { run: fixedRun ?? null, week: initialWeek ?? null });
    return params.has("day") ? s : { ...s, day: 0 };
  });
  const update = useCallback((patch: Partial<ViewState>) => setVs((s) => ({ ...s, ...patch })), []);

  const data = useCalendarData(fixedRun ?? vs.run);
  const model = data.model;
  const runId = data.runId;
  const setUndoRun = useUndoStore((s) => s.setRun);
  const canUndo = useUndoStore((s) => s.past.length > 0);
  const canRedo = useUndoStore((s) => s.future.length > 0);
  useEffect(() => setUndoRun(runId), [runId, setUndoRun]);

  const [filters, setFilters] = useState<CalendarFilters>(EMPTY_FILTERS);
  const [selection, setSelection] = useState<Set<number>>(() => new Set(vs.sel ? [vs.sel] : []));
  const [anchorAid, setAnchorAid] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(vs.sel !== null);
  // null = automatic: docked on ≥ 1600 px, closed (overlay when opened) below (calendar.md §5.2)
  const [sidebarPref, setSidebarPref] = useState<boolean | null>(embedded ? false : null);
  const sidebarOpen = sidebarPref ?? wide;
  const setSidebarOpen = useCallback((v: boolean | ((o: boolean) => boolean)) => setSidebarPref((p) => (typeof v === "function" ? v(p ?? wide) : v)), [wide]);
  const [pending, setPending] = useState<PendingMove | null>(null);
  const [moveFor, setMoveFor] = useState<CalEvent | null>(null);
  const [createReq, setCreateReq] = useState<CreateRequest | null>(null);
  const [shortcuts, setShortcuts] = useState(false);
  const [ghosts, setGhosts] = useState(true);
  const [metric, setMetric] = useState<HeatMetric>("occupancy");
  const [brush, setBrush] = useState<[number, number] | null>(null);
  const [condensed, setCondensed] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [explainSignal, setExplainSignal] = useState(0);
  const [zoomBadge, setZoomBadge] = useState<number | null>(null);
  const gridRef = useRef<TimeGridHandle>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const opts = useMemo(() => ({ isAdmin, announce: setAnnounce }), [isAdmin]);
  const actions = useCalendarActions(runId, opts);

  // ------------------------------------------------------------------ week / day defaults (usability M1)
  const allWeeks = useMemo(() => model?.weeks ?? [], [model]);
  const runWeeks = model?.index.run.horizon === "WEEK" ? model.index.run.weeks : [];
  const todayPos = model ? weekDayOf(model.index.weeks, now.iso) : null;
  const week = vs.week ?? weekInRun(runWeeks, allWeeks, todayPos?.week ?? null);
  const mask = week >= 1 && week <= 31 ? 1 << (week - 1) : 0;
  const day = vs.day || (todayPos && todayPos.week === week ? todayPos.day : 1);
  const urlState = useMemo(() => ({ ...vs, week: model ? week : vs.week, day }), [vs, model, week, day]);
  useEffect(() => {
    if (embedded) return;
    const p = serializeViewState(urlState, new URLSearchParams(window.location.search));
    const url = `${window.location.pathname}?${p.toString()}`;
    if (url !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(window.history.state, "", url);
  }, [urlState, embedded]);
  const weekInfo = model?.index.weeks.find((w) => w.index === week);
  const dates = useMemo(() => [1, 2, 3, 4, 5, 6, 7].map((d) => (model ? dateOf(model.index.weeks, week, d) : null)), [model, week]);
  const isTodayWeek = todayPos?.week === week;

  // ------------------------------------------------------------------ compare
  const compareIdx = useCalendarIndex(vs.compare);
  const compare = useMemo(() => (model && compareIdx.data ? compareRuns(model.index.assignments, compareIdx.data.assignments, model.weeks) : null), [model, compareIdx.data]);

  // ------------------------------------------------------------------ filtered view
  const rooms = useMemo(() => {
    if (!model) return [];
    const byQuery = filters.query.trim() ? model.rooms.filter((r) => queryMatchesRoom(filters.query, r)) : [];
    const list = (byQuery.length ? byQuery : model.rooms).filter((r) => roomPasses(filters, r) && (r.bookable || model.byRoomDay.has(`${r.id}:${day}`)));
    return list;
  }, [model, filters, day]);
  const roomSet = useMemo(() => new Set(rooms.map((r) => r.id)), [rooms]);
  const roomQuery = useMemo(() => !!model && filters.query.trim() !== "" && model.rooms.some((r) => queryMatchesRoom(filters.query, r)), [model, filters.query]);
  const keep = useCallback((e: CalEvent) => eventPasses(roomQuery ? { ...filters, query: "" } : filters, e), [filters, roomQuery]);
  const weekEvents = useMemo(() => (model ? eventsOf(model, week, undefined, (e) => keep(e)) : []), [model, week, keep]);
  const heat = useMemo(
    () => (model ? computeHeat(model, { rooms: roomSet.size !== model.rooms.length ? roomSet : undefined, keep: activeFilterCount(filters) ? keep : undefined, changed: compare ? (e, w) => compare.movedWeeks.get(e.a.id)?.has(w) ?? false : undefined }) : new Map()),
    [model, roomSet, keep, filters, compare],
  );
  const unplacedByDay = useMemo(() => {
    const m = new Map<string, number>();
    for (const u of model?.unplaced ?? []) if (u.day) for (const w of u.weeks.length ? u.weeks : allWeeks) m.set(`${w}:${u.day}`, (m.get(`${w}:${u.day}`) ?? 0) + 1);
    return m;
  }, [model, allWeeks]);
  const counts = useMemo(() => {
    const slots = new Map<number, number>();
    const buildings = new Map<string, number>();
    const seen = new Set<number>();
    let conflicts = 0;
    let warnings = 0;
    let locked = 0;
    for (const e of model ? eventsOf(model, week) : []) {
      if (seen.has(e.a.id)) continue;
      seen.add(e.a.id);
      slots.set(e.a.slot, (slots.get(e.a.slot) ?? 0) + 1);
      if (e.conflict) conflicts++;
      if (e.warning) warnings++;
      if (e.a.locked) locked++;
    }
    return { slots, buildings, conflicts, warnings, locked };
  }, [model, week]);

  // ------------------------------------------------------------------ selection
  const selectedEvents = useMemo(() => (model ? [...selection].map((aid) => model.eventByAid.get(aid)?.[0]).filter((x): x is CalEvent => !!x) : []), [model, selection]);
  const onSelect = useCallback(
    (aid: number | null, mode: "replace" | "toggle" | "range") => {
      if (aid === null) {
        setSelection(new Set());
        return;
      }
      setSelection((s) => {
        if (mode === "toggle") {
          const next = new Set(s);
          if (next.has(aid)) next.delete(aid);
          else next.add(aid);
          return next;
        }
        if (mode === "range" && anchorAid !== null) {
          const order = weekEvents.filter((e) => e.day === day || vs.lens !== "board").sort((a, b) => a.room - b.room || a.sp - b.sp);
          const i = order.findIndex((e) => e.a.id === anchorAid);
          const j = order.findIndex((e) => e.a.id === aid);
          if (i >= 0 && j >= 0) return new Set(order.slice(Math.min(i, j), Math.max(i, j) + 1).map((e) => e.a.id));
        }
        return new Set([aid]);
      });
      if (mode !== "range") setAnchorAid(aid);
      setInspectorOpen(true);
      update({ sel: aid });
    },
    [anchorAid, weekEvents, day, vs.lens, update],
  );
  const onSelectMany = useCallback((aids: number[], additive: boolean) => {
    setSelection((s) => (additive ? new Set([...s, ...aids]) : new Set(aids)));
    if (aids.length) setInspectorOpen(true);
  }, []);
  const onOpen = useCallback(() => setInspectorOpen(true), []);

  // ------------------------------------------------------------------ move / resize / create flows
  const commit = useCallback(
    async (ev: CalEvent, target: { room: number; day: number; sp: number; ep: number }, scope: ScopeValue, extra: PendingMove["extra"] = []) => {
      const roomName = model?.roomById.get(target.room)?.name ?? "";
      const items = [
        { aid: ev.a.id, day: target.day, start_period: target.sp, end_period: target.ep, room_ids: ev.a.rooms.length > 1 && target.room === ev.room ? ev.a.rooms : [target.room], scope: scope.scope, week: scope.scope === "all" ? null : scope.week },
        ...extra.map((x) => ({ aid: x.ev.a.id, day: x.target.day, start_period: x.target.sp, end_period: x.target.ep, room_ids: [x.target.room], scope: "all" as const })),
      ];
      const res = await actions.move(items, ev.a.label, roomName);
      return res.applied;
    },
    [model, actions],
  );

  const onMove = useCallback(
    (m: MoveIntent) => {
      if (!model) return;
      if (!m.check.ok) {
        const reason = m.check.hard[0]?.text[lang] ?? "";
        setAnnounce(t("calendar.move.cannot", { reason }));
        toast.error(t("calendar.move.cannot", { reason }), {
          description: isAdmin ? undefined : t("calendar.move.forceAdmin"),
          action: isAdmin ? { label: t("calendar.move.force"), onClick: () => void (async () => {
            const roomName = model.roomById.get(m.target.room)?.name ?? "";
            await actions.move([{ aid: m.ev.a.id, day: m.target.day, start_period: m.target.sp, end_period: m.target.ep, room_ids: [m.target.room], scope: "all" }], m.ev.a.label, roomName, true);
          })() } : undefined,
        });
        return;
      }
      const bad = m.extra.filter((x) => !checkMove(model, x.ev, { ...x.target, mask: x.ev.mask }, new Set([m.ev.a.id, ...m.extra.map((y) => y.ev.a.id)])).ok);
      if (m.skipPopover && !bad.length) {
        void commit(m.ev, m.target, { scope: "all", week }, m.extra);
        return;
      }
      setPending({ ev: m.ev, target: m.target, extra: m.extra, anchor: m.anchor, soft: m.check.soft });
    },
    [model, lang, t, isAdmin, actions, commit, week],
  );

  const onResize = useCallback(
    (ev: CalEvent, sp: number, ep: number) => {
      if (!model) return;
      const c = checkMove(model, ev, { room: ev.room, day: ev.day, sp, ep });
      if (!c.ok) {
        toast.error(t("calendar.move.cannot", { reason: c.hard[0]?.text[lang] ?? "" }));
        return;
      }
      void commit(ev, { room: ev.room, day: ev.day, sp, ep }, { scope: "all", week });
    },
    [model, t, lang, commit, week],
  );

  const onCreate = useCallback(
    (c: CreateIntent) => {
      if (readOnly) return;
      const room = c.column.room ?? (vs.subject?.kind === "room" ? Number(vs.subject.id) : null);
      if (room === null) return;
      setCreateReq({ column: c.column, room, sp: c.sp, ep: c.ep, anchor: c.anchor, defaultTab: vs.lens === "day" ? "booking" : "request" });
    },
    [readOnly, vs.subject, vs.lens],
  );

  // ------------------------------------------------------------------ navigation
  const setWeek = useCallback((w: number) => {
    const first = allWeeks[0] ?? 1;
    const last = allWeeks[allWeeks.length - 1] ?? 14;
    update({ week: Math.min(last, Math.max(first, w)) });
  }, [allWeeks, update]);
  const [month, setMonth] = useState<string | null>(null);
  const monthValue = month ?? (dates[0] ?? now.iso).slice(0, 7);
  const step = useCallback(
    (dir: 1 | -1) => {
      if (vs.lens === "month") {
        const [y, m] = monthValue.split("-").map(Number);
        const d = new Date(Date.UTC(y, m - 1 + dir, 1));
        setMonth(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
        return;
      }
      if ((vs.lens === "board" && vs.board === "day") || vs.lens === "day") {
        const nd = day + dir;
        if (nd < 1) update({ week: Math.max(allWeeks[0] ?? 1, week - 1), day: 7 });
        else if (nd > 7) update({ week: Math.min(allWeeks[allWeeks.length - 1] ?? 14, week + 1), day: 1 });
        else update({ day: nd });
        return;
      }
      setWeek(week + dir);
    },
    [vs.lens, vs.board, day, week, allWeeks, update, setWeek, monthValue],
  );
  const goToday = useCallback(() => {
    if (todayPos && model?.weeks.includes(todayPos.week)) update({ week: todayPos.week, day: todayPos.day });
    else toast(t("calendar.heat.outOfTerm"));
    setMonth(null);
  }, [todayPos, model, update, t]);
  const setLens = useCallback((l: Lens) => {
    update({ lens: l });
    if (l === "week" && !vs.subject && selectedEvents[0]) update({ lens: l, subject: { kind: "room", id: String(selectedEvents[0].room) } });
  }, [update, vs.subject, selectedEvents]);
  // travel direction of the last lens / week change ("storing information from previous renders")
  const [travel, setTravel] = useState({ lens: vs.lens, week, lensDir: 0, weekDir: 0 });
  if (travel.lens !== vs.lens || travel.week !== week) {
    setTravel({ lens: vs.lens, week, lensDir: travel.lens !== vs.lens ? lensDirection(travel.lens, vs.lens) : travel.lensDir, weekDir: travel.week !== week ? (week > travel.week ? 1 : -1) : 0 });
  }
  const weekDir = travel.weekDir;

  const zoomBy = useCallback((delta: number) => {
    const z = clampZoom(vs.zoom + delta);
    if (z === vs.zoom) return;
    update({ zoom: z });
    setZoomBadge(z);
  }, [vs.zoom, update]);
  useEffect(() => {
    if (zoomBadge === null) return;
    const h = setTimeout(() => setZoomBadge(null), 1000);
    return () => clearTimeout(h);
  }, [zoomBadge]);

  // ------------------------------------------------------------------ keyboard map (calendar.md §12)
  useEffect(() => {
    if (embedded) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      if (document.querySelector("[role=dialog][data-open], [data-slot=dialog-content], [data-slot=sheet-content]")) return;
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        void (e.shiftKey ? actions.redo() : actions.undo());
        return;
      }
      if (meta && e.key.toLowerCase() === "y") {
        e.preventDefault();
        void actions.redo();
        return;
      }
      if (meta && e.altKey && e.code === "KeyS") {
        e.preventDefault();
        setSidebarOpen((v) => !v);
        return;
      }
      if (meta && e.key.toLowerCase() === "a") {
        e.preventDefault();
        const ids = [...new Set((vs.lens === "board" && vs.board === "day" ? weekEvents.filter((x) => x.day === day && roomSet.has(x.room)) : weekEvents).map((x) => x.a.id))].slice(0, 500);
        setSelection(new Set(ids));
        setAnnounce(t("calendar.selected", { n: ids.length }));
        return;
      }
      if (meta || e.altKey) return;
      if (e.key === "Escape") {
        if (selection.size) setSelection(new Set());
        else setInspectorOpen(false);
        return;
      }
      if (e.key === "?") return void setShortcuts(true);
      if (e.code === "BracketRight" || e.code === "BracketLeft") {
        e.preventDefault();
        const dir = e.code === "BracketRight" ? 1 : -1;
        if (e.shiftKey) setWeek(week + 4 * dir);
        else step(dir as 1 | -1);
        return;
      }
      if (e.shiftKey && (e.key === "B" || e.key === "b")) return void update({ lens: "board", board: vs.board === "day" ? "strip" : "day" });
      if (e.shiftKey) return;
      const k = e.key;
      const lens = lensForKey(k);
      if (lens) return void setLens(lens);
      switch (k.toLocaleLowerCase("tr-TR")) {
        case "t":
          return goToday();
        case "j":
          return step(1);
        case "k":
          return step(-1);
        case "+":
        case "=":
          return zoomBy(1);
        case "-":
          return zoomBy(-1);
        case "0":
          return void update({ zoom: 3 });
        case "i":
          return setInspectorOpen((v) => !v);
        case "c":
          return setGhosts((v) => !v);
        case "e":
          setInspectorOpen(true);
          return setExplainSignal((x) => x + 1);
        case "l":
          if (selectedEvents.length && !readOnly) {
            const lockAll = !selectedEvents.every((x) => x.a.locked);
            void actions.lock(selectedEvents.map((x) => x.a.id), lockAll, selectedEvents[0].a.label);
          }
          return;
        case "m":
          if (selectedEvents[0] && !readOnly) setMoveFor(selectedEvents[0]);
          return;
        case "/":
          e.preventDefault();
          setSidebarOpen(true);
          requestAnimationFrame(() => searchRef.current?.focus());
          return;
        case "s":
          (document.querySelector("[data-testid=subject-picker]") as HTMLElement | null)?.click();
          return;
        default:
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [embedded, actions, vs.lens, vs.board, weekEvents, day, roomSet, selection.size, t, setWeek, week, step, update, setLens, goToday, zoomBy, selectedEvents, readOnly]);

  // ------------------------------------------------------------------ lens content
  const chipLine2 = useCallback(
    (e: CalEvent) => {
      const room = model?.roomById.get(e.room);
      const cap = model ? roomCap(model, room) : 0;
      if (vs.lens === "week" && vs.subject?.kind !== "room") return `${room?.name ?? ""} · ${e.a.size}/${cap}`;
      return e.a.size ? `${e.a.size}/${cap}${model?.exam ? ` ${lang === "tr" ? "sınav" : "exam"}` : ""}` : `—/${cap}`;
    },
    [model, vs.lens, vs.subject, lang],
  );
  const ariaFor = useCallback(
    (e: CalEvent) => {
      const room = model?.roomById.get(e.room);
      const parts = [e.a.label, e.a.prog && e.a.year ? `${e.a.prog} ${e.a.year}${lang === "tr" ? ". sınıf" : ""}` : e.a.prog, room?.name, `${dayName(e.day, locale)} ${spanText(e.sp, e.ep)}`, e.a.size ? `${e.a.size} ${lang === "tr" ? "öğrenci" : "students"}` : null, room ? `${roomCap(model as CalendarModel, room)} ${lang === "tr" ? "koltuk" : "seats"}` : null, e.a.locked ? t("calendar.state.locked").toLocaleLowerCase(locale) : null, e.conflict ? `${t("calendar.state.conflict").toLocaleLowerCase(locale)}: ${e.a.reasons[0] ?? ""}` : null, selection.has(e.a.id) ? t("calendar.state.selected") : null];
      return parts.filter(Boolean).join(", ");
    },
    [model, lang, locale, t, selection],
  );

  const gridColumnsBoard = useMemo<GridColumn[]>(() => rooms.map((r) => ({ key: `r${r.id}`, room: r.id, day, label: r.name, sub: model?.exam ? t("calendar.examCap", { n: r.exam_capacity }) : String(r.capacity), ariaLabel: t("calendar.roomAria", { room: r.name, cap: model?.exam ? r.exam_capacity : r.capacity }), building: r.building, tag: r.tags.includes("TIP") ? "TIP" : r.tags.includes("PC") ? "PC" : undefined })), [rooms, day, model, t]);
  const boardIndex = useMemo(() => new Map(rooms.map((r, i) => [r.id, i])), [rooms]);

  const subjectFilter = subjectKeep(vs.subject);
  const weekLensEvents = useMemo(() => {
    if (!subjectFilter) return [];
    const seen = new Set<number>();
    return weekEvents.filter((e) => {
      if (!subjectFilter(e)) return false;
      if (vs.subject?.kind === "room") return true;
      if (seen.has(e.a.id)) return false;
      seen.add(e.a.id);
      return true;
    });
  }, [weekEvents, subjectFilter, vs.subject]);
  const weekDays = useMemo(() => [1, 2, 3, 4, 5, 6, 7].filter((d) => d <= 5 || weekLensEvents.some((e) => e.day === d)), [weekLensEvents]);
  const subjectRoom = vs.subject?.kind === "room" ? Number(vs.subject.id) : null;
  const gridColumnsWeek = useMemo<GridColumn[]>(() => weekDays.map((d) => ({ key: `d${d}`, room: subjectRoom, day: d, label: `${dayName(d, locale, "short")} ${dates[d - 1]?.slice(8) ?? ""}`, ariaLabel: `${dayName(d, locale)} ${dates[d - 1] ?? ""}`, today: dates[d - 1] === now.iso })), [weekDays, subjectRoom, locale, dates, now.iso]);
  const dayIndex = useMemo(() => new Map(weekDays.map((d, i) => [d, i])), [weekDays]);

  const termLong = useMemo(() => (model ? termLongBlocks(model, day).filter((b) => roomSet.has(b.room)) : []), [model, day, roomSet]);
  const boardHeader = useMemo(() => {
    if (!model) return null;
    const bands: { b: string; start: number; count: number }[] = [];
    rooms.forEach((r, i) => {
      const last = bands[bands.length - 1];
      if (last && last.b === r.building) last.count++;
      else bands.push({ b: r.building, start: i, count: 1 });
    });
    const colW = ROOM_COL[vs.density];
    const summary = new Map<string, { label: string; rooms: string[]; sp: number; ep: number }>();
    for (const b of termLong) {
      const k = `${b.label}:${b.sp}:${b.ep}`;
      const x = summary.get(k) ?? { label: b.label, rooms: [], sp: b.sp, ep: b.ep };
      x.rooms.push(model.roomById.get(b.room)?.name ?? "");
      summary.set(k, x);
    }
    return (
      <>
        {bands.map((band) => (
          <div key={`${band.b}${band.start}`} className="absolute top-0 flex h-6 items-center px-2 text-[11px] font-semibold text-label-2" style={{ left: 56 + band.start * colW, width: band.count * colW, boxShadow: "inset 1px 0 0 var(--cal-line-strong)" }}>
            <span className="sticky left-16 truncate">{t("calendar.buildingBand", { b: band.b, n: band.count })}</span>
          </div>
        ))}
        <div className="absolute flex items-center gap-3 overflow-hidden px-2 text-[11px] text-label-2" style={{ top: BAND_H, left: 56, height: ALLDAY_H, right: 0 }}>
          <span className="sticky left-14 shrink-0 font-semibold">{t("calendar.allDay")}</span>
          {[...summary.values()].slice(0, 3).map((s) => (
            <span key={`${s.label}${s.sp}`} className="truncate">
              {s.label} · {s.rooms.length > 2 ? `${s.rooms[0]}–${s.rooms[s.rooms.length - 1]}` : s.rooms.join(", ")} · P{s.sp}–P{s.ep} · {t("calendar.termLong")}
            </span>
          ))}
          {summary.size > 3 ? <span className="shrink-0">+{summary.size - 3}</span> : null}
          {weekInfo && weekTypeKey(weekInfo.kind) === "holiday" ? <span className="font-semibold">{t("calendar.weekType.holiday")}</span> : null}
        </div>
      </>
    );
  }, [model, rooms, vs.density, termLong, t, weekInfo]);

  const pendingList = pending && model
    ? [{ ev: pending.ev, col: vs.lens === "week" ? (dayIndex.get(pending.target.day) ?? -1) : (boardIndex.get(pending.target.room) ?? -1), sp: pending.target.sp, ep: pending.target.ep }].filter((x) => x.col >= 0)
    : [];

  const subjectTitle = useMemo(() => {
    if (!model || !vs.subject) return null;
    const s = vs.subject;
    if (s.kind === "room") {
      const r = model.roomById.get(Number(s.id));
      return r ? t("calendar.subject.roomHeader", { room: r.name, cap: model.exam ? r.exam_capacity : r.capacity }) + (r.tags.length ? ` · ${r.tags.join(" ")}` : "") : null;
    }
    const evs = model.events.filter(subjectKeep(s) ?? (() => false));
    const ids = new Set(evs.map((e) => e.a.id));
    if (s.kind === "instructor") {
      const e = evs[0];
      const i = e ? e.a.instr_ids.indexOf(Number(s.id)) : -1;
      return e ? t("calendar.subject.instructorHeader", { name: e.a.instr[i] ?? "", n: ids.size }) : null;
    }
    if (s.kind === "cohort") {
      const e = evs[0];
      return e ? t("calendar.subject.cohortHeader", { name: t("calendar.subject.cohortLabel", { program: e.a.prog ?? "", year: e.a.year ?? "" }), n: ids.size }) : null;
    }
    return evs[0]?.a.label ?? null;
  }, [model, vs.subject, t]);

  const renderLens = () => {
    if (!model) return null;
    const rowH = rowHeightFor(vs.zoom);
    const ghostList = compare && ghosts ? (compare.ghosts.get(week) ?? []) : [];
    if (vs.lens === "board" && vs.board === "strip")
      return <BoardStrip model={model} rooms={rooms} events={weekEvents.filter((e) => roomSet.has(e.room))} blocks={blocksOf(model, week).filter((b) => roomSet.has(b.room))} slotW={STRIP_SLOT_STEPS[vs.zoom - 1]} rowH={vs.density === "compact" ? 24 : 32} heat={heat} week={week} dates={dates} selection={selection} onSelect={onSelect} onOpen={onOpen} onPickDay={(d) => update({ board: "day", day: d })} onPickRoom={(id) => update({ lens: "week", subject: { kind: "room", id: String(id) } })} todayDay={isTodayWeek ? (todayPos?.day ?? null) : null} ariaFor={ariaFor} />;
    if (vs.lens === "board") {
      const evs = weekEvents.filter((e) => e.day === day && roomSet.has(e.room));
      return (
        <TimeGrid
          ref={gridRef}
          model={model}
          mask={mask}
          columns={gridColumnsBoard}
          colW={ROOM_COL[vs.density]}
          rowH={rowH}
          events={evs}
          colOf={(e) => boardIndex.get(e.room) ?? -1}
          blocks={blocksOf(model, week, day).filter((b) => roomSet.has(b.room))}
          blockCol={(b) => boardIndex.get(b.room) ?? -1}
          bookings={bookingsOf(model, week, day).filter((b) => roomSet.has(b.room))}
          bookingCol={(b) => boardIndex.get(b.room) ?? -1}
          ghosts={ghostList.filter((g) => g.day === day)}
          ghostCol={(g) => boardIndex.get(g.room) ?? -1}
          movedAids={compare?.movedAids}
          selection={selection}
          onSelect={onSelect}
          onSelectMany={onSelectMany}
          onOpen={onOpen}
          onMove={onMove}
          onCreate={onCreate}
          onResize={onResize}
          onZoom={(d) => zoomBy(d)}
          onAnnounce={setAnnounce}
          readOnly={readOnly}
          nowMin={isTodayWeek && todayPos?.day === day ? now.minutes : null}
          nowCols={isTodayWeek && todayPos?.day === day ? rooms.map((_, i) => i) : []}
          gridLabel={t("calendar.gridLabel", { day: dayName(day, locale), week })}
          header={boardHeader}
          headerH={BAND_H + ALLDAY_H + ROOM_HEADER_H}
          pending={pendingList}
          focusAid={vs.sel}
          line2={chipLine2}
          ariaFor={ariaFor}
          emptyHint={evs.length === 0 && activeFilterCount(filters) > 0 ? <FilteredEmpty onClear={() => setFilters(EMPTY_FILTERS)} /> : null}
        />
      );
    }
    if (vs.lens === "week") {
      if (!vs.subject) return <EmptyState className="px-6" title={t("calendar.subject.placeholder")} description={t("calendar.empty.pickSubject")} size="sm" />;
      const room = subjectRoom;
      const blocks = room !== null ? blocksOf(model, week).filter((b) => b.room === room) : [];
      const bks = room !== null ? bookingsOf(model, week).filter((b) => b.room === room) : [];
      return (
        <TimeGrid
          ref={gridRef}
          model={model}
          mask={mask}
          columns={gridColumnsWeek}
          colW={Math.max(ROOM_COL[vs.density], 132)}
          rowH={rowH}
          events={weekLensEvents}
          colOf={(e) => dayIndex.get(e.day) ?? -1}
          blocks={blocks}
          blockCol={(b) => dayIndex.get(b.day) ?? -1}
          bookings={bks}
          bookingCol={(b) => dayIndex.get(b.day) ?? -1}
          ghosts={ghostList.filter((g) => (room === null ? false : g.room === room))}
          ghostCol={(g) => dayIndex.get(g.day) ?? -1}
          movedAids={compare?.movedAids}
          selection={selection}
          onSelect={onSelect}
          onSelectMany={onSelectMany}
          onOpen={onOpen}
          onMove={onMove}
          onCreate={onCreate}
          onResize={onResize}
          onZoom={(d) => zoomBy(d)}
          onAnnounce={setAnnounce}
          readOnly={readOnly}
          nowMin={isTodayWeek ? now.minutes : null}
          nowCols={isTodayWeek && todayPos ? [dayIndex.get(todayPos.day) ?? -1].filter((x) => x >= 0) : []}
          gridLabel={t("calendar.weekGridLabel", { subject: subjectTitle ?? "", week })}
          headerH={ROOM_HEADER_H}
          pending={pendingList}
          focusAid={vs.sel}
          line2={chipLine2}
          ariaFor={ariaFor}
          emptyHint={weekLensEvents.length === 0 ? <div className="absolute top-24 left-20 max-w-sm"><EmptyState size="sm" title={t("calendar.empty.subject", { subject: subjectTitle ?? "" })} description={t("calendar.empty.subjectHint")} /></div> : null}
        />
      );
    }
    if (vs.lens === "day") {
      const evs = weekEvents.filter((e) => e.day === day && roomSet.has(e.room));
      const cur = todayPos?.day === day ? (periodAtMinute(now.minutes) ?? 0) : 0;
      const busyNow = new Set(evs.filter((e) => e.sp <= cur && cur <= e.ep).map((e) => e.room));
      const list = filters.freeNow ? [...rooms].sort((a, b) => Number(busyNow.has(a.id)) - Number(busyNow.has(b.id))) : rooms;
      return <DayTimeline model={model} rooms={list} day={day} mask={mask} pxPerMin={MINUTE_PX_STEPS[vs.zoom - 1]} events={evs} blocks={blocksOf(model, week, day).filter((b) => roomSet.has(b.room))} bookings={bookingsOf(model, week, day).filter((b) => roomSet.has(b.room))} nowMin={now.minutes} isToday={isTodayWeek && todayPos?.day === day} selection={selection} readOnly={readOnly} onSelect={onSelect} onOpen={onOpen} onMove={onMove} onCreate={onCreate} onAnnounce={setAnnounce} ariaFor={ariaFor} label={t("calendar.timelineLabel", { day: dayName(day, locale) })} />;
    }
    if (vs.lens === "month") return <MonthHeat model={model} heat={heat} metric={metric} onMetric={setMetric} unplacedByDay={unplacedByDay} todayIso={now.iso} onPick={(w, d) => update({ lens: "board", board: "day", week: w, day: d })} compareOn={!!compare} month={monthValue} onMonth={setMonth} />;
    if (vs.lens === "term") return <TermHeat model={model} heat={heat} metric={metric} onMetric={setMetric} unplacedByDay={unplacedByDay} todayIso={now.iso} onPick={(w, d) => update({ lens: "board", board: "day", week: w, day: d })} compareOn={!!compare} brush={brush} onBrush={setBrush} currentWeek={week} />;
    const evs = subjectFilter ? weekEvents.filter(subjectFilter) : weekEvents.filter((e) => roomSet.has(e.room));
    return <AgendaLens model={model} events={evs} days={[1, 2, 3, 4, 5, 6, 7]} dates={dates} todayIso={now.iso} nowMin={now.minutes} selection={selection} onOpen={onOpen} onSelect={onSelect} emptyLabel={t("calendar.empty.filtered")} />;
  };


  // ------------------------------------------------------------------ states
  if (data.noRun) {
    return (
      <div ref={rootRef} className={cn("cal-canvas flex items-start p-8", className)} style={{ height: embedded ? undefined : fill }}>
        <EmptyState title={t("calendar.empty.noRun")} actions={<><Button onClick={() => router.push("/generate")}>{t("calendar.empty.generate")}</Button><Button variant="outline" onClick={() => router.push("/import")}>{t("calendar.empty.import")}</Button></>} />
      </div>
    );
  }
  if (mobile && !embedded && model) {
    return <MobileCalendar model={model} week={week} day={day} dates={dates} onDay={(d) => update({ day: d })} onWeek={setWeek} heat={heat} now={now} selection={selection} onSelect={onSelect} subject={vs.subject} onSubject={(s) => update({ subject: s })} runId={runId} termId={data.term?.id ?? null} actions={actions} readOnly={readOnly} lens={vs.lens} onLens={setLens} />;
  }

  const showScrubber = model && vs.lens !== "month" && vs.lens !== "term";
  const rangeStart = dates[0];
  const rangeEnd = dates[6];
  const title = vs.lens === "month"
    ? new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${monthValue}-01T00:00:00Z`))
    : vs.lens === "term"
      ? (data.term?.name ?? "")
      : rangeStart && rangeEnd
        ? rangeTitle(rangeStart, rangeEnd, locale)
        : t("calendar.nav.weekTitle", { n: week, type: "" });
  const weekType = t(`calendar.weekType.${weekTypeKey(weekInfo?.kind ?? "LECTURE")}`);
  const dayLens = (vs.lens === "board" && vs.board === "day") || vs.lens === "day";
  const outside = runWeeks.length > 0 && !runWeeks.includes(week);
  const selected = selectedEvents.length === 1 ? selectedEvents[0] : null;
  const inspectorVisible = inspectorOpen && selectedEvents.length > 0 && !embedded;
  const docked = wide;

  return (
    <div ref={rootRef} className={cn("relative flex min-h-0 gap-2", className)} style={{ height: embedded ? undefined : fill }} data-testid="calendar">
      {sidebarOpen && model && runId !== null && !embedded ? (
        <CalendarSidebar
          ref={searchRef}
          className={cn("w-[272px] shrink-0", !wide && "absolute inset-y-0 left-0 z-40 shadow-[var(--ambient-3)]")}
          model={model}
          term={data.term}
          runs={data.runs}
          runId={runId}
          onRun={(id) => {
            update({ run: id, sel: null });
            setSelection(new Set());
          }}
          week={week}
          day={day}
          onPickDate={(w, d) => update({ week: w, day: d, ...(vs.lens === "month" || vs.lens === "term" ? { lens: "board" as Lens, board: "day" as const } : {}) })}
          heat={heat}
          todayIso={now.iso}
          filters={filters}
          onFilters={setFilters}
          counts={counts}
          compare={vs.compare}
          onCompare={(id) => update({ compare: id })}
          ghosts={ghosts}
          onGhosts={setGhosts}
        />
      ) : null}

      <section className="cal-canvas relative flex min-w-0 flex-1 flex-col overflow-hidden" aria-label={t("calendar.lens.label")} onScrollCapture={(e) => {
        const top = (e.target as HTMLElement).scrollTop ?? 0;
        const next = top > 24;
        if (next !== condensed) setCondensed(next);
      }}>
        <div className="px-3 pt-3">
          {model ? (
            <CapsuleToolbar
              model={model}
              lens={vs.lens}
              onLens={setLens}
              board={vs.board}
              onBoard={(b) => update({ board: b })}
              weekLabel={t("calendar.nav.weekTitle", { n: week, type: "" }).replace(/ · $/, "")}
              weeks={model.index.weeks}
              week={week}
              onWeek={setWeek}
              onPrev={() => step(-1)}
              onNext={() => step(1)}
              onToday={goToday}
              onToggleSidebar={() => setSidebarOpen((v) => !v)}
              subject={vs.subject}
              onSubject={(s) => update({ subject: s, ...(s && vs.lens !== "agenda" ? { lens: "week" as Lens } : {}) })}
              conflicts={counts.conflicts}
              warnings={counts.warnings}
              onIssues={() => setFilters((f) => ({ ...f, status: f.status.includes("conflict") ? [] : ["conflict"] }))}
              canUndo={canUndo}
              canRedo={canRedo}
              onUndo={() => void actions.undo()}
              onRedo={() => void actions.redo()}
              density={vs.density}
              onDensity={(d: Density) => update({ density: d })}
              runs={data.runs}
              compare={vs.compare}
              onCompare={(id) => update({ compare: id })}
              onExport={() => runId !== null && window.open(api.runs.exportUrl(runId, "xlsx"), "_blank")}
              onShortcuts={() => setShortcuts(true)}
              onSearch={() => {
                setSidebarOpen(true);
                requestAnimationFrame(() => searchRef.current?.focus());
              }}
              condensed={condensed}
              readOnly={readOnly}
            />
          ) : null}
        </div>
        <div className="flex flex-wrap items-end gap-x-3 gap-y-1 px-4 pt-2 pb-2">
          <h1 className="type-title-2 capitalize" data-testid="calendar-title">{title}</h1>
          {vs.lens !== "month" && vs.lens !== "term" ? (
            <p className="pb-0.5 text-[13px] text-label-2">
              {t("calendar.nav.weekTitle", { n: week, type: weekType })}
              {vs.lens === "week" && subjectTitle ? ` · ${subjectTitle}` : ""}
            </p>
          ) : null}
          {compare && vs.compare ? (
            <p className="pb-0.5 text-[12px] text-label-2" role="status">
              {t("calendar.compare.summary", { run: vs.compare, m: n(compare.moved), a: n(compare.onlyA), r: n(compare.onlyB) })}
              <Button size="xs" variant="ghost" onClick={() => update({ compare: null })}>{t("calendar.compare.close")}</Button>
            </p>
          ) : null}
          {dayLens && model ? (
            <div className="ml-auto">
              <SegmentedGlass size="sm" aria-label={t("calendar.lens.day")} options={[1, 2, 3, 4, 5, 6, 7].map((d) => ({ value: String(d), label: `${dayName(d, locale, "short")} ${dates[d - 1]?.slice(8) ?? ""}` }))} value={String(day)} onValueChange={(v) => update({ day: Number(v) })} />
            </div>
          ) : null}
          {vs.lens === "day" ? (
            <label className="flex items-center gap-1.5 pb-0.5 text-[12px]"><input type="checkbox" checked={filters.freeNow} onChange={(e) => setFilters((f) => ({ ...f, freeNow: e.target.checked }))} className="accent-(--accent)" />{t("calendar.freeNow")}</label>
          ) : null}
        </div>
        {outside && model ? (
          <div className="mx-4 mb-2 flex items-center gap-2 rounded-xl bg-fill-3 px-3 py-2 text-[13px]" role="status">
            {t("calendar.empty.outsideRun", { weeks: runWeeks.join(", ") })}
            <Button size="xs" variant="secondary" onClick={() => setWeek(runWeeks[0])}>{t("calendar.empty.goToRunWeek", { n: runWeeks[0] })}</Button>
          </div>
        ) : null}
        <div className="relative min-h-0 flex-1">
          {data.loading && !model ? (
            <p className="flex h-full items-start gap-2 px-6 py-6 text-[13px] text-label-2" role="status"><span className="size-3 animate-spin rounded-full border-2 border-label-4 border-t-label-2" aria-hidden />{t("calendar.loading")}</p>
          ) : data.error && !model ? (
            <div className="px-6 py-6"><p className="mb-2 text-[13px]">{t("calendar.error")}</p><Button size="sm" variant="secondary" onClick={data.refetch}>{t("calendar.retry")}</Button></div>
          ) : model ? (
            <motion.div
              key={`${vs.lens}-${vs.board}`}
              className="absolute inset-0"
              initial={reduce ? false : { x: 8 * travel.lensDir }}
              animate={{ x: 0 }}
              transition={springs.smooth}
            >
              <motion.div key={`w${week}-${day}`} className="absolute inset-0" initial={reduce || weekDir === 0 ? false : { x: 12 * weekDir }} animate={{ x: 0 }} transition={springs.smooth}>
                {renderLens()}
              </motion.div>
              {/* veil on top fades out instead of fading the lens (keeps the glass headers' blur, backdrop-root rule) */}
              {!reduce ? (
                <motion.div key={`veil-${vs.lens}-${week}-${day}`} aria-hidden className="cal-canvas pointer-events-none absolute inset-0 z-30" initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={{ duration: 0.18 }} />
              ) : null}
            </motion.div>
          ) : null}
          {zoomBadge !== null ? <span role="status" className="glass-thick absolute top-3 right-3 z-40 rounded-full px-3 py-1 text-[12px] font-medium">{t("calendar.zoom", { n: zoomBadge })}</span> : null}
        </div>
        {showScrubber && model ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-4 z-30 flex justify-center">
            <WeekScrubberLazy model={model} week={week} heat={heat} onWeek={setWeek} onToday={goToday} todayWeek={todayPos?.week ?? null} runWeeks={runWeeks} />
          </div>
        ) : null}
      </section>

      {inspectorVisible && model ? (
        <div className={cn("flex min-h-0 w-[360px] shrink-0 flex-col", !docked && "absolute inset-y-0 right-0 z-40")}>
          {selected ? (
            <ClassInspector
              surface="calendar"
              className="h-full"
              termId={model.index.run.term_id}
              runId={runId}
              kind={model.exam ? "exams" : "meetings"}
              assignment={selected.a}
              roomName={(id) => model.roomById.get(id)?.name ?? `#${id}`}
              roomCap={(ids) => ids.reduce((s, id) => s + roomCap(model, model.roomById.get(id)), 0)}
              allWeeks={model.weeks.filter((w) => w <= 16)}
              readOnly={readOnly}
              onClose={() => {
                setInspectorOpen(false);
                setSelection(new Set());
                update({ sel: null });
              }}
              onMove={() => setMoveFor(selected)}
              onLock={(locked) => void actions.lock([selected.a.id], locked, selected.a.label)}
              explainSignal={explainSignal}
            />
          ) : (
            <SelectionSummary
              className="h-fit"
              count={selectedEvents.length}
              students={selectedEvents.reduce((s, e) => s + e.a.size, 0)}
              buildings={new Set(selectedEvents.map((e) => model.roomById.get(e.room)?.building)).size}
              onLock={readOnly ? undefined : () => void actions.lock(selectedEvents.map((e) => e.a.id), true, selectedEvents[0].a.label)}
              onUnlock={readOnly ? undefined : () => void actions.lock(selectedEvents.map((e) => e.a.id), false, selectedEvents[0].a.label)}
              onClear={() => setSelection(new Set())}
            />
          )}
        </div>
      ) : null}

      {model ? (
        <>
          <MovePopover
            model={model}
            pending={pending}
            week={week}
            onCancel={() => setPending(null)}
            onSave={(scope) => {
              const p = pending;
              setPending(null);
              if (p) void commit(p.ev, p.target, scope, p.extra);
            }}
          />
          <MoveDialog model={model} ev={moveFor} week={week} open={moveFor !== null} onOpenChange={(o) => !o && setMoveFor(null)} onConfirm={(target, scope) => (moveFor ? commit(moveFor, target, scope) : Promise.resolve(false))} />
          <QuickCreate model={model} req={createReq} week={week} onClose={() => setCreateReq(null)} onMoveHere={async (aid, target) => {
            const ev = model.eventByAid.get(aid)?.[0];
            if (!ev) return false;
            const c = checkMove(model, ev, target);
            if (!c.ok) {
              toast.error(t("calendar.move.cannot", { reason: c.hard[0]?.text[lang] ?? "" }));
              return false;
            }
            return commit(ev, target, { scope: "all", week });
          }} />
        </>
      ) : null}
      <ShortcutsSheet open={shortcuts} onOpenChange={setShortcuts} />
      <p className="sr-only" aria-live="polite" data-testid="calendar-live">{announce}</p>
    </div>
  );
}

function FilteredEmpty({ onClear }: { onClear: () => void }) {
  const { t } = useI18n();
  return (
    <div className="absolute top-32 left-20 z-10 max-w-sm">
      <EmptyState size="sm" title={t("calendar.empty.filtered")} actions={<Button size="sm" variant="secondary" onClick={onClear}>{t("calendar.empty.clearFilters")}</Button>} />
    </div>
  );
}

function WeekScrubberLazy({ model, week, heat, onWeek, onToday, todayWeek, runWeeks }: { model: CalendarModel; week: number; heat: ReturnType<typeof computeHeat>; onWeek: (w: number) => void; onToday: () => void; todayWeek: number | null; runWeeks: readonly number[] }) {
  const weeks = model.index.weeks.filter((w) => w.start_date || w.index <= 16);
  return <WeekScrubber weeks={weeks} week={week} occupancy={(w) => weeklyMean(heat, w)} onWeek={onWeek} onToday={onToday} todayWeek={todayWeek} runWeeks={runWeeks} />;
}
