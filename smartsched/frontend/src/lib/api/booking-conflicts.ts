"use client";
/**
 * P2 conflict resolver after publishing (`app/api/v1/booking_conflicts.py`, service `app/services/booking_conflicts.py`).
 * Every route needs `planning.edit`; the `override` action needs `planning.admin` (the backend refuses it per item).
 *
 * - `GET /bookings/conflicts/summary`: open conflicts per published run (the banner on /bookings).
 * - `GET /bookings/conflicts/{run}/plan`: conflicts grouped by series with ranked options; 409 `plan_stale` once
 *   another run of the term and kind is published.
 * - `POST …/apply {items, dry_run}`: all or nothing; 409 `invalid_items` with `problems[]` changes nothing.
 * - `POST …/auto`: the top option of every conflict whose score clears the threshold, as a dry-run payload, plus the
 *   conflicts left (`unresolved`, with the reason).
 * - `POST …/detect`: scan the published run again after manual timetable edits.
 *
 * Errors are `{detail: {code, message, message_en, message_tr, …}}`: read them with `wave1Error` / `errorText`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";
import { Bilingual, wave1Error } from "./wave1";

const s = { silent: true } as const;

export const ACTIONS = ["move_room", "move_period", "move_day", "cancel", "override"] as const;
export type ResolveAction = (typeof ACTIONS)[number];
export const SCOPES = ["one", "future", "all"] as const;
export type ResolveScope = (typeof SCOPES)[number];

export const SummaryRun = z.object({
  run_id: z.number(),
  term_id: z.number(),
  kind: z.string().nullish(),
  label: z.string().nullish(),
  open: z.number(),
  series: z.number().default(0),
  message_tr: z.string().default(""),
  message_en: z.string().default(""),
});
export type SummaryRun = z.infer<typeof SummaryRun>;
export const ConflictSummary = z.object({ runs: z.array(SummaryRun).default([]) });
export type ConflictSummary = z.infer<typeof ConflictSummary>;

export const ConflictOption = z
  .object({
    id: z.string(),
    kind: z.enum(ACTIONS).catch("cancel"),
    room_id: z.number().nullish(),
    room: z.string().nullish(),
    capacity: z.number().nullish(),
    building: z.string().nullish(),
    start_period: z.number().nullish(),
    end_period: z.number().nullish(),
    dates: z.array(z.string()).default([]),
    score: z.number().nullish(),
    reason: Bilingual.nullish(),
    default_reason: z.string().nullish(),
    admin_only: z.boolean().optional(),
    link: z.string().nullish(),
  })
  .passthrough();
export type ConflictOption = z.infer<typeof ConflictOption>;

export const Held = z.object({
  assignment_id: z.number().nullish(),
  label: z.string().nullish(),
  start_period: z.number().nullish(),
  end_period: z.number().nullish(),
});

export const ConflictLine = z.object({
  conflict_id: z.number(),
  booking_id: z.number(),
  status: z.string(),
  date: z.string(),
  start_period: z.number(),
  end_period: z.number(),
  time: z.string().nullish(),
  room_id: z.number().nullish(),
  room: z.string().nullish(),
  user_id: z.number().nullish(),
  user: z.string().nullish(),
  notes: z.string().nullish(),
  headcount: z.number().nullish(),
  held: Held.nullish(),
});
export type ConflictLine = z.infer<typeof ConflictLine>;

export const ConflictGroup = z.object({
  key: z.string(),
  series_id: z.number().nullish(),
  kind: z.enum(["series", "booking"]).catch("booking"),
  requested: z.boolean().default(false),
  room_id: z.number(),
  room: z.string(),
  default_scope: z.enum(SCOPES).catch("one"),
  conflicts: z.array(ConflictLine),
  options: z.array(ConflictOption).default([]),
  no_room_reason: Bilingual.nullish(),
});
export type ConflictGroup = z.infer<typeof ConflictGroup>;

export const ConflictPlan = z.object({
  run_id: z.number(),
  term_id: z.number(),
  open: z.number(),
  groups: z.array(ConflictGroup).default([]),
  banner: Bilingual.nullish(),
});
export type ConflictPlan = z.infer<typeof ConflictPlan>;

export interface ApplyItem {
  conflict_id: number;
  action: ResolveAction;
  option_id?: string | null;
  scope: ResolveScope;
  reason?: string | null;
}

export const AutoItem = z.object({ conflict_id: z.number(), action: z.enum(ACTIONS), option_id: z.string().nullish(), scope: z.enum(SCOPES).catch("one") });
export const AutoPlan = z.object({
  run_id: z.number(),
  dry_run: z.boolean().default(true),
  items: z.array(AutoItem).default([]),
  unresolved: z.array(z.object({ conflict_id: z.number(), group: z.string().nullish(), reason: Bilingual.nullish() })).default([]),
});
export type AutoPlan = z.infer<typeof AutoPlan>;

export const ApplyResult = z.object({
  run_id: z.number(),
  resolved: z.array(z.number()).default([]),
  moved: z.array(z.number()).default([]),
  cancelled: z.array(z.number()).default([]),
  kept: z.array(z.number()).default([]),
  notified: z.number().default(0),
  unnotified: z.number().default(0),
  already: z.array(z.number()).default([]),
  dry_run: z.boolean().default(false),
});
export type ApplyResult = z.infer<typeof ApplyResult>;

export const Problem = z.object({ conflict_id: z.number().nullish(), code: z.string(), message_tr: z.string(), message_en: z.string() });
export type Problem = z.infer<typeof Problem>;

/** The `problems[]` of a 409 `invalid_items` (empty for any other error). */
export function applyProblems(err: unknown): Problem[] {
  const e = wave1Error(err);
  if (e.code !== "invalid_items") return [];
  const parsed = z.array(Problem).safeParse(e.data.problems);
  return parsed.success ? parsed.data : [];
}

export const conflictKeys = {
  summary: ["conflicts", "summary"] as const,
  plan: (run: number) => ["conflicts", "plan", run] as const,
};

export const conflictsApi = {
  summary: () => request("/bookings/conflicts/summary", { schema: ConflictSummary, ...s }),
  plan: (run: number) => request(`/bookings/conflicts/${run}/plan`, { schema: ConflictPlan, ...s }),
  auto: (run: number) => request(`/bookings/conflicts/${run}/auto`, { method: "POST", schema: AutoPlan, ...s }),
  apply: (run: number, items: ApplyItem[], dryRun: boolean) => request(`/bookings/conflicts/${run}/apply`, { method: "POST", body: { items, dry_run: dryRun }, schema: ApplyResult, ...s }),
  detect: (run: number) => request<{ run_id: number; new: number; open: number; cleared: number; superseded: number }>(`/bookings/conflicts/${run}/detect`, { method: "POST", ...s }),
};

/** The banner's data; only fetched for planners (`enabled`), a 403 is read as "nothing to show". */
export function useConflictSummary(enabled: boolean) {
  return useQuery({ queryKey: conflictKeys.summary, queryFn: conflictsApi.summary, enabled, staleTime: 60_000, retry: false });
}

export function useConflictPlan(run: number | null) {
  return useQuery({ queryKey: conflictKeys.plan(run ?? 0), queryFn: () => conflictsApi.plan(run!), enabled: run != null && run > 0, retry: false });
}

export function useApplyConflicts(run: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ items, dryRun }: { items: ApplyItem[]; dryRun: boolean }) => conflictsApi.apply(run, items, dryRun),
    onSuccess: (res) => {
      if (res.dry_run) return;
      void qc.invalidateQueries({ queryKey: ["conflicts"] });
      void qc.invalidateQueries({ queryKey: ["crbs", "grid"] });
    },
  });
}

export function useDetectConflicts(run: number) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => conflictsApi.detect(run), onSuccess: () => void qc.invalidateQueries({ queryKey: ["conflicts"] }) });
}
