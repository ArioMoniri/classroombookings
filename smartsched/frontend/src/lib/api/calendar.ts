"use client";
/**
 * Calendar v2 API (backend app/api/v1/calendar.py, schemas app/schemas/calendar.py):
 * term-wide calendar index, heat aggregates, free rooms for a slot, scoped/bulk moves with an undo token,
 * per-assignment explanations, saved views, and CRBS bookings (app/api/v1/bookings.py) for quick-create.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

/* ------------------------------------------------------------------ schemas */

export const Text2 = z.object({ tr: z.string(), en: z.string() });
export type Text2 = z.infer<typeof Text2>;

export const Issue = z.object({
  code: z.string(),
  severity: z.enum(["hard", "soft"]),
  text: Text2,
  with_assignment_id: z.number().nullable().optional(),
  with_label: z.string().nullable().optional(),
  room_code: z.string().nullable().optional(),
  weeks: z.array(z.number()).default([]),
});
export type Issue = z.infer<typeof Issue>;

export const IndexRoom = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  building: z.string(),
  capacity: z.number(),
  exam_capacity: z.number(),
  tags: z.array(z.string()).default([]),
  bookable: z.boolean().default(true),
  photo_url: z.string().nullable().optional(),
});
export type IndexRoom = z.infer<typeof IndexRoom>;

export const IndexWeek = z.object({ index: z.number(), start_date: z.string().nullable(), kind: z.string(), label: z.string().nullable() });
export type IndexWeek = z.infer<typeof IndexWeek>;

export const IndexAssignment = z.object({
  id: z.number(),
  mr: z.number().nullable().optional(),
  ex: z.number().nullable().optional(),
  label: z.string(),
  code: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  sec: z.string().nullable().optional(),
  prog: z.string().nullable().optional(),
  prog_id: z.number().nullable().optional(),
  fac: z.number().nullable().optional(),
  slot: z.number().default(8),
  year: z.number().nullable().optional(),
  evening: z.boolean().default(false),
  instr: z.array(z.string()).default([]),
  instr_ids: z.array(z.number()).default([]),
  size: z.number().default(0),
  cap: z.number().nullable().optional(),
  weeks: z.array(z.number()).default([]),
  day: z.number(),
  date: z.string().nullable().optional(),
  sp: z.number(),
  ep: z.number(),
  rooms: z.array(z.number()).default([]),
  locked: z.boolean().default(false),
  origin: z.string().default("SOLVER"),
  reasons: z.array(z.string()).default([]),
  tags: z.array(z.string()).default([]),
  needs_pc: z.boolean().default(false),
});
export type IndexAssignment = z.infer<typeof IndexAssignment>;

export const IndexBlock = z.object({
  id: z.number(),
  room: z.number(),
  day: z.number(),
  sp: z.number(),
  ep: z.number(),
  weeks: z.array(z.number()).default([]),
  label: z.string(),
  source: z.string(),
});
export type IndexBlock = z.infer<typeof IndexBlock>;

export const IndexBooking = z.object({
  id: z.number(),
  room: z.number(),
  date: z.string(),
  week: z.number().nullable(),
  day: z.number(),
  sp: z.number(),
  ep: z.number(),
  title: z.string(),
  owner: z.string().nullable().optional(),
});
export type IndexBooking = z.infer<typeof IndexBooking>;

export const IndexUnplaced = z.object({
  mr: z.number(),
  label: z.string(),
  code: z.string(),
  prog: z.string().nullable().optional(),
  slot: z.number().default(8),
  year: z.number().nullable().optional(),
  size: z.number().default(0),
  day: z.number().nullable().optional(),
  sp: z.number().nullable().optional(),
  ep: z.number().nullable().optional(),
  weeks: z.array(z.number()).default([]),
  room_text: z.string().nullable().optional(),
});
export type IndexUnplaced = z.infer<typeof IndexUnplaced>;

export const CalendarIndex = z.object({
  run: z.object({
    id: z.number(),
    term_id: z.number(),
    kind: z.enum(["COURSE", "EXAM"]),
    status: z.string(),
    label: z.string().nullable().optional(),
    horizon: z.string(),
    weeks: z.array(z.number()).default([]),
    is_active: z.boolean().default(false),
    origin_import: z.boolean().default(false),
  }),
  rooms: z.array(IndexRoom),
  weeks: z.array(IndexWeek),
  periods: z.array(z.object({ index: z.number(), start: z.string(), end: z.string() })),
  faculties: z.array(z.object({ id: z.number(), name: z.string(), slot: z.number() })),
  assignments: z.array(IndexAssignment),
  blocks: z.array(IndexBlock),
  bookings: z.array(IndexBooking).default([]),
  unplaced: z.array(IndexUnplaced).default([]),
  bookings_enabled: z.boolean().default(false),
  today: z.string(),
});
export type CalendarIndex = z.infer<typeof CalendarIndex>;

export const HeatCell = z.object({
  week: z.number().nullable(),
  day: z.number(),
  date: z.string().nullable(),
  in_term: z.boolean(),
  occupied: z.number(),
  blocked: z.number(),
  capacity: z.number(),
  occupancy: z.number(),
  conflicts: z.number(),
  by_building: z.record(z.string(), z.number()).default({}),
});
export type HeatCell = z.infer<typeof HeatCell>;
export const Heat = z.object({
  run_id: z.number(),
  scale: z.enum(["term", "month"]),
  month: z.string().nullable().optional(),
  room_id: z.number().nullable().optional(),
  cells: z.array(HeatCell),
  weekly: z.array(z.object({ week: z.number(), occupancy: z.number(), conflicts: z.number() })).default([]),
});
export type Heat = z.infer<typeof Heat>;

export const FreeRoom = z.object({
  room_id: z.number(),
  code: z.string(),
  building: z.string(),
  capacity: z.number(),
  tags: z.array(z.string()).default([]),
  status: z.enum(["free", "too_small", "busy", "blocked", "not_bookable", "tag_mismatch"]),
  fit: z.number().nullable().optional(),
  reason: Text2.nullable().optional(),
  with_label: z.string().nullable().optional(),
});
export type FreeRoom = z.infer<typeof FreeRoom>;
export const FreeRooms = z.object({
  run_id: z.number(),
  day: z.number(),
  start_period: z.number(),
  end_period: z.number(),
  weeks: z.array(z.number()),
  size: z.number(),
  rooms: z.array(FreeRoom),
});
export type FreeRooms = z.infer<typeof FreeRooms>;

export type MoveScope = "all" | "week" | "from";
export interface MoveItem {
  aid: number;
  day?: number;
  start_period?: number;
  end_period?: number;
  room_ids?: number[];
  scope?: MoveScope;
  week?: number | null;
}

export const Snapshot = z.object({
  id: z.number(),
  day: z.number(),
  start_period: z.number(),
  end_period: z.number(),
  room_ids: z.array(z.number()),
  week: z.number().nullable(),
  weeks: z.array(z.number()),
  is_locked: z.boolean(),
  origin: z.string(),
});
export const UndoToken = z.object({ snapshots: z.array(Snapshot).default([]), delete_ids: z.array(z.number()).default([]) });
export type UndoToken = z.infer<typeof UndoToken>;

export const MovePlanItem = z.object({
  aid: z.number(),
  label: z.string(),
  ok: z.boolean(),
  hard: z.array(Issue).default([]),
  soft: z.array(Issue).default([]),
  day: z.number(),
  start_period: z.number(),
  end_period: z.number(),
  room_ids: z.array(z.number()),
  room_codes: z.array(z.string()),
  weeks: z.array(z.number()),
  moved_ids: z.array(z.number()).default([]),
  split_ids: z.array(z.number()).default([]),
});
export type MovePlanItem = z.infer<typeof MovePlanItem>;
export const BulkMoveOut = z.object({
  ok: z.boolean(),
  applied: z.boolean(),
  dry_run: z.boolean(),
  items: z.array(MovePlanItem),
  ok_count: z.number(),
  conflict_count: z.number(),
  assignments: z.array(IndexAssignment).default([]),
  undo: UndoToken.default({ snapshots: [], delete_ids: [] }),
});
export type BulkMoveOut = z.infer<typeof BulkMoveOut>;

export const ExplainOut = z.object({
  assignment_id: z.number(),
  text: z.string(),
  sections: z.array(z.object({ key: z.string(), title: z.string(), lines: z.array(z.string()) })),
  checks: z.array(z.object({ key: z.string(), state: z.enum(["ok", "fail", "na"]), text: Text2 })).default([]),
  source: z.enum(["model", "template"]).default("template"),
});
export type ExplainOut = z.infer<typeof ExplainOut>;

export const SavedView = z.object({
  id: z.string(),
  surface: z.enum(["classes", "calendar"]),
  name: z.string(),
  state: z.record(z.string(), z.unknown()),
  shared: z.boolean(),
  owner_id: z.number(),
  owner_name: z.string().nullable().optional(),
  mine: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type SavedView = z.infer<typeof SavedView>;

/** `GET /bookings/grid?display=room&room_id=&date=`: the periods a room can be booked in (CRBS parity). */
const BookingGridPeriod = z.object({ id: z.number(), start_period: z.number().optional(), end_period: z.number().optional() }).passthrough();

/* ------------------------------------------------------------------ endpoints */

const silently = { silent: true } as const;

export const calendarApi = {
  index: (runId: number) => request(`/runs/${runId}/calendar-index`, { schema: CalendarIndex }),
  heat: (runId: number, opts: { scale?: "term" | "month"; month?: string; roomId?: number } = {}) =>
    request(`/runs/${runId}/heat`, { query: { scale: opts.scale ?? "term", month: opts.month, room_id: opts.roomId }, schema: Heat }),
  freeRooms: (runId: number, q: { day: number; start_period: number; end_period: number; weeks?: number[]; min_capacity?: number; tags?: string[]; exclude_assignment_id?: number }) =>
    request(`/runs/${runId}/free-rooms`, {
      query: { day: q.day, start_period: q.start_period, end_period: q.end_period, weeks: q.weeks?.join(","), min_capacity: q.min_capacity, tags: q.tags?.join(","), exclude_assignment_id: q.exclude_assignment_id },
      schema: FreeRooms,
    }),
  movePreview: (runId: number, aid: number, body: Omit<MoveItem, "aid">) =>
    request(`/runs/${runId}/assignments/${aid}/move-preview`, { method: "POST", body, schema: BulkMoveOut, ...silently }),
  bulkMove: (runId: number, body: { moves: MoveItem[]; atomic?: boolean; dry_run?: boolean; force?: boolean }) =>
    request(`/runs/${runId}/assignments/bulk-move`, { method: "POST", body, schema: BulkMoveOut, ...silently }),
  restore: (runId: number, undo: UndoToken) =>
    request(`/runs/${runId}/assignments/restore`, { method: "POST", body: undo, schema: z.object({ restored: z.array(z.number()), deleted: z.array(z.number()) }), ...silently }),
  bulkLock: (runId: number, ids: number[], locked: boolean) =>
    request(`/runs/${runId}/assignments/bulk-lock`, { method: "POST", body: { ids, locked }, schema: z.object({ updated: z.array(z.number()), missing: z.array(z.number()) }) }),
  explain: (runId: number, aid: number, lang: "tr" | "en", signal?: AbortSignal) =>
    request(`/runs/${runId}/assignments/${aid}/explain`, { method: "POST", body: { lang, use_model: true }, schema: ExplainOut, signal, ...silently }),
  views: (surface: "classes" | "calendar") => request("/views", { query: { surface }, schema: z.array(SavedView), ...silently }),
  createView: (body: { surface: "classes" | "calendar"; name: string; state: Record<string, unknown>; shared?: boolean }) =>
    request("/views", { method: "POST", body, schema: SavedView }),
  updateView: (id: string, body: { name?: string; state?: Record<string, unknown>; shared?: boolean }) =>
    request(`/views/${id}`, { method: "PUT", body, schema: SavedView }),
  deleteView: (id: string) => request(`/views/${id}`, { method: "DELETE" }),
  /** CRBS bookings: the period ids a room accepts on a date (empty when no booking schedule is configured). */
  bookingPeriods: async (roomId: number, date: string): Promise<{ id: number; start_period: number; end_period: number }[]> => {
    const raw = await request<unknown>("/bookings/grid", { query: { display: "room", room_id: roomId, date }, ...silently });
    const periods = collectPeriods(raw);
    return periods.map((p) => BookingGridPeriod.parse(p)).filter((p): p is { id: number; start_period: number; end_period: number } & typeof p => typeof p.start_period === "number" && typeof p.end_period === "number");
  },
  createBooking: (body: { room_id: number; date: string; period_id: number; notes?: string; term_id?: number }) =>
    request<Record<string, unknown>>("/bookings", { method: "POST", body, ...silently }),
  createRecurring: (body: { room_id: number; date: string; period_id: number; notes?: string; term_id?: number; start?: string; end?: string }) =>
    request<Record<string, unknown>>("/bookings/recurring", { method: "POST", body, ...silently }),
};

/** Find `periods` arrays anywhere in the CRBS grid payload (its exact nesting belongs to the bookings router). */
function collectPeriods(raw: unknown): Record<string, unknown>[] {
  const out = new Map<number, Record<string, unknown>>();
  const walk = (v: unknown, depth: number) => {
    if (depth > 5 || v === null || typeof v !== "object") return;
    if (Array.isArray(v)) {
      v.forEach((x) => walk(x, depth + 1));
      return;
    }
    const rec = v as Record<string, unknown>;
    if (Array.isArray(rec.periods)) {
      for (const p of rec.periods) {
        if (p && typeof p === "object" && typeof (p as Record<string, unknown>).id === "number") out.set((p as { id: number }).id, p as Record<string, unknown>);
      }
    }
    Object.values(rec).forEach((x) => walk(x, depth + 1));
  };
  walk(raw, 0);
  return [...out.values()];
}

/* ------------------------------------------------------------------ hooks */

export const calKeys = {
  index: (runId: number) => ["calendar-index", runId] as const,
  heat: (runId: number, scale: string, month?: string, roomId?: number) => ["calendar-heat", runId, scale, month ?? null, roomId ?? null] as const,
  free: (runId: number, key: string) => ["calendar-free", runId, key] as const,
  views: (surface: string) => ["saved-views", surface] as const,
};

export function useCalendarIndex(runId: number | null) {
  return useQuery({
    queryKey: calKeys.index(runId ?? 0),
    queryFn: () => calendarApi.index(runId ?? 0),
    enabled: runId !== null,
    staleTime: 60_000,
    placeholderData: (prev) => (prev && prev.run.id === runId ? prev : undefined),
  });
}

export function useHeat(runId: number | null, opts: { scale?: "term" | "month"; month?: string; roomId?: number } = {}) {
  return useQuery({
    queryKey: calKeys.heat(runId ?? 0, opts.scale ?? "term", opts.month, opts.roomId),
    queryFn: () => calendarApi.heat(runId ?? 0, opts),
    enabled: runId !== null,
    staleTime: 60_000,
  });
}

export function useFreeRooms(runId: number | null, q: Parameters<typeof calendarApi.freeRooms>[1] | null) {
  const key = q ? JSON.stringify(q) : "";
  return useQuery({
    queryKey: calKeys.free(runId ?? 0, key),
    queryFn: () => calendarApi.freeRooms(runId ?? 0, q as Parameters<typeof calendarApi.freeRooms>[1]),
    enabled: runId !== null && q !== null,
    staleTime: 15_000,
  });
}

export function useSavedViews(surface: "classes" | "calendar") {
  return useQuery({ queryKey: calKeys.views(surface), queryFn: () => calendarApi.views(surface), retry: false, staleTime: 60_000 });
}

export function useSaveView(surface: "classes" | "calendar") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id?: string; name: string; state: Record<string, unknown>; shared?: boolean }) =>
      v.id ? calendarApi.updateView(v.id, { name: v.name, state: v.state, shared: v.shared }) : calendarApi.createView({ surface, name: v.name, state: v.state, shared: v.shared }),
    onSuccess: () => qc.invalidateQueries({ queryKey: calKeys.views(surface) }),
  });
}

export function useDeleteView(surface: "classes" | "calendar") {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: string) => calendarApi.deleteView(id), onSuccess: () => qc.invalidateQueries({ queryKey: calKeys.views(surface) }) });
}

/** Patch the cached index with rows returned by a move / restore (no refetch of the 1–3 MB payload). */
export function patchIndex(index: CalendarIndex, rows: IndexAssignment[], deletedIds: number[] = []): CalendarIndex {
  const gone = new Set(deletedIds);
  const byId = new Map(rows.map((r) => [r.id, r]));
  const kept = index.assignments.filter((a) => !gone.has(a.id)).map((a) => byId.get(a.id) ?? a);
  const known = new Set(kept.map((a) => a.id));
  const added = rows.filter((r) => !known.has(r.id) && !gone.has(r.id));
  return { ...index, assignments: [...kept, ...added] };
}
