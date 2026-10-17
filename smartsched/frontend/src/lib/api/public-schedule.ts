"use client";
/**
 * V2 public read-only day view (`app/api/v1/public_schedule.py`, service `app/services/public_schedule.py`). No sign-in.
 *
 * - `GET /public/schedule`: buildings and their rooms (only when an administrator switched the view on).
 * - `GET /public/schedule/rooms/{code}?date=` and `/public/schedule/buildings/{code}?date=`: one day; `date` defaults
 *   to the booking clock's today, the window is today − 7 … today + 120.
 * - Off, an unknown room or building and a date outside the window all answer the same plain 404; above the
 *   per-address limit 429 with `Retry-After`.
 * - Data minimisation: course codes only, generic block labels, bookings as "Rezerve / Booked" or hidden; no names,
 *   no notes, no ids.
 *
 * Administration (`setup.settings`): `GET/PUT /public-schedule/admin/settings {enabled?, show_bookings?: busy|hidden}`;
 * switching it on records a KVKK sign-off (who, when, legal basis), like calendar sync.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { CalendarSignoff } from "./approval-first";
import { Bilingual } from "./wave1";

const s = { silent: true } as const;

/** days before / after today a public page may show (`PAST_DAYS`, `FUTURE_DAYS`) */
export const WINDOW = { past: 7, future: 120 } as const;
/** kiosk refresh */
export const REFRESH_MS = 60_000;

export const PublicRoom = z.object({ code: z.string(), name: z.string(), building: z.string().nullish(), capacity: z.number().nullish() });
export type PublicRoom = z.infer<typeof PublicRoom>;

export const PublicIndex = z.object({
  buildings: z.array(z.object({ code: z.string(), name: z.string(), rooms: z.array(PublicRoom).default([]) })).default([]),
  show_bookings: z.enum(["busy", "hidden"]).catch("busy"),
});
export type PublicIndex = z.infer<typeof PublicIndex>;

export const PublicItem = z.object({
  kind: z.enum(["class", "reserved", "booked"]).catch("reserved"),
  start_period: z.number(),
  end_period: z.number(),
  start: z.string(),
  end: z.string(),
  label: Bilingual,
});
export type PublicItem = z.infer<typeof PublicItem>;

export const PublicRoomDay = z.object({ date: z.string(), room: PublicRoom, items: z.array(PublicItem).default([]) });
export type PublicRoomDay = z.infer<typeof PublicRoomDay>;

export const PublicBuildingDay = z.object({
  date: z.string(),
  building: z.object({ code: z.string(), name: z.string() }),
  rooms: z.array(PublicRoom.extend({ items: z.array(PublicItem).default([]) })).default([]),
});
export type PublicBuildingDay = z.infer<typeof PublicBuildingDay>;

export const PublicSettings = z.object({
  enabled: z.boolean(),
  signoff: CalendarSignoff.nullish(),
  show_bookings: z.enum(["busy", "hidden"]).catch("busy"),
});
export type PublicSettings = z.infer<typeof PublicSettings>;

/** `public_schedule.LEGAL_BASIS`: the English constant the sign-off stores; shown in the reader's language. */
export const PUBLIC_LEGAL_BASIS = "KVKK Art. 4(2)(ç) data minimisation: the public day view publishes no personal data (course codes, room codes and busy times only)";

export const publicKeys = {
  index: ["public", "index"] as const,
  room: (code: string, date: string | null) => ["public", "room", code, date] as const,
  building: (code: string, date: string | null) => ["public", "building", code, date] as const,
  settings: ["public", "settings"] as const,
};

export const publicApi = {
  index: () => request("/public/schedule", { schema: PublicIndex, ...s }),
  room: (code: string, date: string | null) => request(`/public/schedule/rooms/${encodeURIComponent(code)}`, { query: { date }, schema: PublicRoomDay, ...s }),
  building: (code: string, date: string | null) => request(`/public/schedule/buildings/${encodeURIComponent(code)}`, { query: { date }, schema: PublicBuildingDay, ...s }),
  settings: () => request("/public-schedule/admin/settings", { schema: PublicSettings, ...s }),
  saveSettings: (body: { enabled?: boolean; show_bookings?: "busy" | "hidden" }) => request("/public-schedule/admin/settings", { method: "PUT", body, schema: PublicSettings, ...s }),
};

/** 404 = the view is off, the code is unknown or the date is outside the window (one answer for all three). */
export const isNotFound = (e: unknown) => e instanceof HttpError && e.status === 404;
export const isRateLimited = (e: unknown) => e instanceof HttpError && e.status === 429;

const kiosk = { refetchInterval: REFRESH_MS, refetchIntervalInBackground: true, retry: (n: number, e: unknown) => !isNotFound(e) && !isRateLimited(e) && n < 2, staleTime: 30_000 } as const;

export function usePublicIndex() {
  return useQuery({ queryKey: publicKeys.index, queryFn: publicApi.index, ...kiosk });
}
export function usePublicRoom(code: string, date: string | null) {
  return useQuery({ queryKey: publicKeys.room(code, date), queryFn: () => publicApi.room(code, date), ...kiosk });
}
export function usePublicBuilding(code: string, date: string | null) {
  return useQuery({ queryKey: publicKeys.building(code, date), queryFn: () => publicApi.building(code, date), ...kiosk });
}

export function usePublicSettings(enabled = true) {
  return useQuery({ queryKey: publicKeys.settings, queryFn: publicApi.settings, enabled, retry: false });
}
export function useSavePublicSettings() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: publicApi.saveSettings, onSuccess: (out) => qc.setQueryData(publicKeys.settings, out) });
}

/* ------------------------------------------------------------------------------------- pure helpers */

/** `YYYY-MM-DD` ± n days (UTC arithmetic, so a DST change never shifts the day). */
export function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const t = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1) + n * 86_400_000);
  return t.toISOString().slice(0, 10);
}

/** The dates a public page may show, from the day the backend called today. */
export function publicWindow(today: string): { min: string; max: string } {
  return { min: addDays(today, -WINDOW.past), max: addDays(today, WINDOW.future) };
}

/** The item running at `hhmm` ("09:40") on the shown day, if any. */
export function currentItem<T extends { start: string; end: string }>(items: readonly T[], hhmm: string): T | null {
  return items.find((i) => i.start <= hhmm && hhmm < i.end) ?? null;
}

/** The next item after `hhmm`, if any. */
export function nextItem<T extends { start: string }>(items: readonly T[], hhmm: string): T | null {
  return [...items].sort((a, b) => a.start.localeCompare(b.start)).find((i) => i.start > hhmm) ?? null;
}
