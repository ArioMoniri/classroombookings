"use client";
/**
 * W3-SLOT: the one hook every booking surface reads for the administrator's slot display (slot-display.ts), and the
 * administrator's save. `GET /bookings/slot-display` answers every signed-in user; an older backend (404) or a
 * failure falls back to the defaults, so a surface always draws.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { Grid } from "@/lib/api/crbs";
import { z } from "zod";
import { request } from "@/lib/api/client";
import { applySlotDisplay, DEFAULT_SLOT_DISPLAY, parseSlotDisplay, slotDisplayExtra, type SlotDisplay } from "./slot-display";

export const SLOT_DISPLAY_KEY = ["slot-display"] as const;

const Raw = z.record(z.string(), z.unknown());

async function fetchSlotDisplay(): Promise<SlotDisplay> {
  try {
    return parseSlotDisplay(await request("/bookings/slot-display", { silent: true, schema: Raw }));
  } catch {
    return DEFAULT_SLOT_DISPLAY;
  }
}

export function useSlotDisplay(): { display: SlotDisplay; ready: boolean } {
  const q = useQuery({ queryKey: SLOT_DISPLAY_KEY, queryFn: fetchSlotDisplay, staleTime: 60_000, retry: false });
  return { display: q.data ?? DEFAULT_SLOT_DISPLAY, ready: q.isSuccess };
}

/** ADMIN only (PUT /settings answers 403 otherwise). Every booking surface follows on success. */
export function useSaveSlotDisplay() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sd: SlotDisplay) => request("/settings", { method: "PUT", silent: true, body: { extra: slotDisplayExtra(sd) } }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: SLOT_DISPLAY_KEY });
      await qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

/** A grid as the administrator wants it shown (applySlotDisplay), memoised: same object while inputs are the same. */
export function useShownGrid(grid: Grid | undefined, sd: SlotDisplay, reveal = false): Grid | undefined {
  return useMemo(() => (grid ? applySlotDisplay(grid, sd, reveal) : undefined), [grid, sd, reveal]);
}
