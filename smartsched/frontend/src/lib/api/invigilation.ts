"use client";
/**
 * Invigilator assignment for exam runs (backend app/api/v1/invigilation.py, app/services/invigilation.py,
 * app/solver/invigilation.py). Writes need PLANNER (planning.edit), reads VIEWER.
 *
 * - pool: staff / assistants / instructors with their own rules (unavailability, duty caps, load factor);
 * - plans: one CP-SAT solve of an exam run (202 + poll; QUEUED → RUNNING → OPTIMAL / FEASIBLE / INFEASIBLE / FAILED),
 *   re-run as a child plan that keeps the locked duties, publish (one per exam run), delete (409 when published);
 * - duties: lock / unlock, reassign to a candidate (409 `detail.problems` when a hard rule would break; the new duty
 *   is MANUAL and locked), add one to an under-staffed post (`POST …/duties`, 201 duty + the re-scored plan brief;
 *   409 `{tr, en, reason, reason_text, problems}`), candidates of a post (free, and everyone else with the reason);
 * - progress: every brief carries the queue job's last phase and percentage (`progress {phase, pct}`);
 * - exports: roster CSV, load JSON / CSV.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorProblems, errorText, noRetry, pairOf, type Pair } from "./analytics";
import { buildUrl, HttpError, request } from "./client";

export const POOL_KINDS = ["STAFF", "ASSISTANT", "INSTRUCTOR", "OTHER"] as const;
export type PoolKind = (typeof POOL_KINDS)[number];

export interface Unavailable {
  date?: string;
  day?: number;
  start_period?: number;
  end_period?: number;
  note?: string;
}

export interface PoolMember {
  id: number;
  term_id: number | null;
  instructor_id: number | null;
  full_name: string;
  kind: PoolKind;
  max_duties: number | null;
  max_per_day: number | null;
  load_factor: number;
  unavailable: Unavailable[];
  active: boolean;
  notes: string | null;
  person_key: string;
}

export interface PoolIn {
  full_name?: string;
  instructor_id?: number | null;
  term_id?: number | null;
  kind?: PoolKind;
  max_duties?: number | null;
  max_per_day?: number | null;
  load_factor?: number;
  unavailable?: Unavailable[];
  active?: boolean;
  notes?: string | null;
}

export type OwnExam = "prefer" | "allow" | "forbid";
export type InstructorPool = "exam_instructors" | "all" | "none";
export const WEIGHT_KEYS = ["max_load", "spread", "same_day", "own_exam", "stability"] as const;
export type WeightKey = (typeof WEIGHT_KEYS)[number];

export interface PlanParams {
  students_per_invigilator?: number;
  min_per_room?: number;
  max_per_room?: number | null;
  own_exam?: OwnExam;
  instructor_pool?: InstructorPool;
  max_per_day?: number;
  min_rest?: number;
  time_limit_s?: number;
  seed?: number;
  weights?: Partial<Record<WeightKey, number>>;
}

/** the service defaults (services/invigilation.py DEFAULTS, solver DEFAULT_WEIGHTS), shown in the run form */
export const PLAN_DEFAULTS = {
  students_per_invigilator: 40,
  min_per_room: 1,
  max_per_room: null as number | null,
  own_exam: "prefer" as OwnExam,
  instructor_pool: "exam_instructors" as InstructorPool,
  max_per_day: 3,
  min_rest: 0,
  time_limit_s: 20,
  seed: 0,
  weights: { max_load: 10, spread: 2, same_day: 3, own_exam: 5, stability: 4 } as Record<WeightKey, number>,
};

export type PlanStatus = "QUEUED" | "RUNNING" | "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "FAILED" | "ERROR";
export const PLAN_ACTIVE: ReadonlySet<string> = new Set(["QUEUED", "RUNNING"]);

export interface PlanCounts {
  posts: number | null;
  required: number | null;
  filled: number | null;
  missing: number | null;
  people: number | null;
  eligible_people: number | null;
}

/**
 * The queue job's last reported phase (backend plan_progress): queued 0, loading 10, solving 30 (for the whole solve:
 * CP-SAT reports nothing while it runs), persisting 90, done 100, failed. A plan that has not reported yet reads
 * `queued` / `running` without a number.
 */
export const PROGRESS_PHASES = ["queued", "loading", "solving", "persisting", "done", "failed", "running"] as const;
export type ProgressPhase = (typeof PROGRESS_PHASES)[number];
export interface PlanProgress {
  phase: ProgressPhase | (string & {});
  pct: number | null;
}

export interface PlanBrief {
  id: number;
  term_id: number;
  exam_run_id: number;
  parent_plan_id: number | null;
  status: PlanStatus;
  label: string | null;
  hard_score: number | null;
  soft_score: number | null;
  is_active: boolean;
  params: PlanParams & Record<string, unknown>;
  error: string | null;
  created_at: string | null;
  finished_at: string | null;
  counts: PlanCounts;
  headline: Pair | null;
  /** round-1 R1-M-11: nothing to staff (0 room-sessions or 0 required duties); never "En iyi", never published */
  empty?: boolean;
  empty_reason?: Pair | null;
  /** round-1 T-R1-42: how the pool was built (the rule, the exam list's people and how many matched an instructor) */
  pool?: PoolMatch | null;
  /** absent on a backend older than alembic 0033 */
  progress?: PlanProgress | null;
}

/** `stats.pool` of a finished plan: the exam list's people against the Instructor rows (backend match_exam_people) */
export interface PoolMatch {
  instructor_pool: InstructorPool;
  /** distinct people named on the run's exams */
  exam_people: number;
  /** of them, found as exactly one Instructor row */
  matched: number;
  /** fit more than one row (a masked list: two people with the initials "A. A.") */
  ambiguous: number;
  /** not on the instructor list */
  unmatched: number;
  instructors: number;
  /** people in the plan's pool (instructors found + the Pool tab's rows) */
  size: number;
}

export interface Duty {
  id: number;
  post_key: string;
  date: string;
  start_period: number;
  end_period: number;
  time: string;
  room_id: number;
  exam_request_ids: number[];
  person_key: string;
  person_name: string;
  instructor_id: number | null;
  staff_id: number | null;
  is_locked: boolean;
  origin: string;
}

export interface Post {
  key: string;
  date: string;
  start_period: number;
  end_period: number;
  time: string;
  room_id: number;
  room: string;
  building: string | null;
  exam_ids: number[];
  seated: number;
  required: number;
  exams: { id: number; label: string; instructor_text: string | null }[];
  assigned: Duty[];
  missing: number;
}

export interface PersonLoad {
  person_key: string;
  name: string;
  duties: number;
  periods: number;
  own_exam: number;
  days: number;
}

export interface Suggestion {
  code: string;
  count?: number;
  text: Pair;
  [k: string]: unknown;
}

export interface Diagnosis {
  code: string;
  severity: "error" | "warning" | "info";
  text: Pair;
  message?: string;
  post_keys?: string[];
  exam_ids?: number[];
  exams?: string[];
  person_keys?: string[];
  dates?: string[];
  params?: Record<string, unknown>;
  suggestions?: Suggestion[];
  /** a shortage whose posts are all staffed now (filled by hand after the solve) */
  resolved?: boolean;
}

export interface PlanDetail extends PlanBrief {
  posts: Post[];
  people: PersonLoad[];
  diagnosis: Diagnosis[];
  objective_breakdown: Partial<Record<WeightKey, number>> & Record<string, number>;
  stats: Record<string, unknown> & { progress?: number; phase?: string; max_periods?: number; fair_share_periods?: number; wall_s?: number };
}

export interface Candidates {
  post_key: string;
  free: { person_key: string; name: string; kind: string }[];
  unavailable: { person_key: string; name: string; kind: string; reason: string; reason_text: Pair }[];
}

/** the refusal reasons of `POST …/duties` and reassign (backend REASON_TEXT, `post_full`); `reason_text` is the server's */
export const DUTY_REASONS = ["on_post", "post_full", "on_duty", "rest", "day_cap", "total_cap", "teaching", "unavailable", "booking", "own_exam", "own_exam_elsewhere", "no_capacity"] as const;

/** `POST …/duties` 201: the new duty (MANUAL, locked) plus the re-scored plan brief */
export type AddDutyOut = Duty & { plan: PlanBrief };

export interface PlanLoad {
  plan_id: number;
  dates: string[];
  rows: { person_key: string; name: string; duties: number; periods: number; max_per_day: number; cells: { date: string; duties: number; periods: number }[] }[];
  per_date: { date: string; duties: number; people: number }[];
}

const P = "/invigilation";

export const invigilationApi = {
  pool: (termId?: number | null) => request<PoolMember[]>(`${P}/pool`, { query: { term_id: termId ?? undefined }, silent: true }),
  createMember: (body: PoolIn) => request<PoolMember>(`${P}/pool`, { method: "POST", body, silent: true }),
  updateMember: (id: number, body: PoolIn) => request<PoolMember>(`${P}/pool/${id}`, { method: "PUT", body, silent: true }),
  deleteMember: (id: number) => request<void>(`${P}/pool/${id}`, { method: "DELETE", silent: true }),
  plans: (q: { exam_run_id?: number; term_id?: number }) => request<PlanBrief[]>(`${P}/plans`, { query: q, silent: true }),
  plan: (id: number, person?: string | null) => request<PlanDetail>(`${P}/plans/${id}`, { query: { person: person ?? undefined }, silent: true }),
  create: (body: { exam_run_id: number; label?: string; params: PlanParams }) => request<{ plan_id: number; status: PlanStatus }>(`${P}/plans`, { method: "POST", body, silent: true }),
  rerun: (id: number, body: { label?: string; params: PlanParams }) => request<{ plan_id: number; parent_plan_id: number; status: PlanStatus }>(`${P}/plans/${id}/rerun`, { method: "POST", body, silent: true }),
  activate: (id: number) => request<PlanBrief>(`${P}/plans/${id}/activate`, { method: "POST", silent: true }),
  remove: (id: number) => request<void>(`${P}/plans/${id}`, { method: "DELETE", silent: true }),
  lock: (id: number, dutyId: number, locked: boolean) => request<Duty>(`${P}/plans/${id}/duties/${dutyId}/lock`, { method: "POST", query: { locked }, silent: true }),
  reassign: (id: number, dutyId: number, body: { person_key: string; reason?: string }) => request<Duty>(`${P}/plans/${id}/duties/${dutyId}`, { method: "PUT", body, silent: true }),
  addDuty: (id: number, body: { post_key: string; person_key: string; reason?: string }) => request<AddDutyOut>(`${P}/plans/${id}/duties`, { method: "POST", body, silent: true }),
  candidates: (id: number, postKey: string) => request<Candidates>(`${P}/plans/${id}/candidates`, { query: { post_key: postKey }, silent: true }),
  load: (id: number) => request<PlanLoad>(`${P}/plans/${id}/load`, { silent: true }),
};

export const invigilationCsv = {
  roster: (id: number) => buildUrl(`${P}/plans/${id}/export`),
  load: (id: number) => buildUrl(`${P}/plans/${id}/load`, { format: "csv" }),
};

export const ik = {
  all: ["invigilation"] as const,
  pool: (termId: number | null) => ["invigilation", "pool", termId] as const,
  plans: (examRunId: number | null) => ["invigilation", "plans", examRunId] as const,
  plan: (id: number, person: string | null) => ["invigilation", "plan", id, person] as const,
  candidates: (id: number, postKey: string) => ["invigilation", "candidates", id, postKey] as const,
  load: (id: number) => ["invigilation", "load", id] as const,
};

/**
 * Poll interval while a plan is QUEUED / RUNNING: 1 s, growing ×1.5 per answer up to 8 s (a default run takes
 * about 76 s on the real Final, so the backoff keeps it to ~15 requests); false once the plan has finished.
 */
export function pollDelay(status: string | undefined, polls: number): number | false {
  if (!status || !PLAN_ACTIVE.has(status)) return false;
  return Math.min(8000, Math.round(1000 * 1.5 ** Math.max(0, polls)));
}

export function usePool(termId: number | null) {
  return useQuery({ queryKey: ik.pool(termId), queryFn: () => invigilationApi.pool(termId), retry: noRetry, staleTime: 30_000 });
}

export function usePlans(examRunId: number | null) {
  return useQuery({
    queryKey: ik.plans(examRunId),
    queryFn: () => invigilationApi.plans({ exam_run_id: examRunId ?? undefined }),
    enabled: examRunId !== null,
    retry: noRetry,
    refetchInterval: (q) => (q.state.data?.some((p) => PLAN_ACTIVE.has(p.status)) ? 4000 : false),
  });
}

/** every plan (newest first), to open the exam run someone last planned */
export function useAllPlans() {
  return useQuery({ queryKey: ["invigilation", "plans", "all"] as const, queryFn: () => invigilationApi.plans({}), retry: noRetry, staleTime: 30_000 });
}

export function usePlan(id: number | null, person: string | null = null) {
  return useQuery({
    queryKey: ik.plan(id ?? 0, person),
    queryFn: () => invigilationApi.plan(id ?? 0, person),
    enabled: id !== null,
    retry: noRetry,
    refetchInterval: (q) => pollDelay(q.state.data?.status, q.state.dataUpdateCount),
  });
}

export function useCandidates(id: number | null, postKey: string | null) {
  return useQuery({
    queryKey: ik.candidates(id ?? 0, postKey ?? ""),
    queryFn: () => invigilationApi.candidates(id ?? 0, postKey ?? ""),
    enabled: id !== null && !!postKey,
    retry: noRetry,
    staleTime: 0,
  });
}

export function usePlanLoad(id: number | null, enabled = true) {
  return useQuery({ queryKey: ik.load(id ?? 0), queryFn: () => invigilationApi.load(id ?? 0), enabled: enabled && id !== null, retry: noRetry });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ik.all });
}

export function useSaveMember() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (v: { id?: number; body: PoolIn }) => (v.id ? invigilationApi.updateMember(v.id, v.body) : invigilationApi.createMember(v.body)), onSuccess: inv });
}
export function useDeleteMember() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: invigilationApi.deleteMember, onSuccess: inv });
}
export function useCreatePlan() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: invigilationApi.create, onSuccess: inv });
}
export function useRerunPlan() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (v: { id: number; label?: string; params: PlanParams }) => invigilationApi.rerun(v.id, { label: v.label, params: v.params }), onSuccess: inv });
}
export function useActivatePlan() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: invigilationApi.activate, onSuccess: inv });
}
export function useDeletePlan() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: invigilationApi.remove, onSuccess: inv });
}
export function useLockDuty() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (v: { id: number; dutyId: number; locked: boolean }) => invigilationApi.lock(v.id, v.dutyId, v.locked), onSuccess: inv });
}
export function useReassignDuty() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (v: { id: number; dutyId: number; personKey: string; reason?: string }) => invigilationApi.reassign(v.id, v.dutyId, { person_key: v.personKey, reason: v.reason }), onSuccess: inv });
}

/**
 * Fill an under-staffed post by hand. The response's brief replaces the cached one at once (lists and the open
 * detail, with the duty placed on its post), then the detail is re-read for the diagnoses (`resolved`) and the
 * candidates of every post (one person fewer is free at that time).
 */
export function useAddDuty() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; postKey: string; personKey: string; reason?: string }) => invigilationApi.addDuty(v.id, { post_key: v.postKey, person_key: v.personKey, reason: v.reason }),
    onSuccess: (out, v) => {
      qc.setQueriesData<PlanDetail>({ queryKey: ["invigilation", "plan", v.id] }, (d) => (d ? withAddedDuty(d, out) : d));
      qc.setQueriesData<PlanBrief[]>({ queryKey: ["invigilation", "plans"] }, (list) => (Array.isArray(list) ? withBrief(list, out.plan) : list));
      return qc.invalidateQueries({ queryKey: ik.all });
    },
    // a refusal may mean the plan changed under us (post_full: someone filled it): re-read it
    onError: (_e, v) => qc.invalidateQueries({ queryKey: ["invigilation", "plan", v.id] }),
  });
}

/** a plan list with one brief replaced (same id); other plans untouched */
export function withBrief<T extends PlanBrief>(list: readonly T[], brief: PlanBrief): T[] {
  return list.map((p) => (p.id === brief.id ? { ...p, ...brief } : p));
}

/** the detail after `POST …/duties`: the new brief's fields, and the duty on its post (missing one fewer) */
export function withAddedDuty(d: PlanDetail, out: AddDutyOut): PlanDetail {
  if (d.id !== out.plan.id) return d;
  const { plan, ...duty } = out;
  const posts = d.posts.map((p) =>
    p.key === duty.post_key && !p.assigned.some((x) => x.id === duty.id) ? { ...p, assigned: [...p.assigned, duty], missing: Math.max(0, p.missing - 1) } : p,
  );
  return { ...d, ...plan, posts };
}

/** a refusal of `POST …/duties` / reassign: the sentence, the reason code and the server's reason text, the problems */
export function dutyRefusal(e: unknown, lang: "tr" | "en"): { text: string; reason: string | null; reasonText: string | null; problems: string[] } {
  const body = e instanceof HttpError ? detailOf(e.detail) : null;
  const rt = body?.reason_text;
  const reasonText = rt && typeof rt === "object" ? pairOf(rt as Pair, lang) || null : typeof rt === "string" ? rt : null;
  return { text: errorText(e, lang), reason: typeof body?.reason === "string" ? body.reason : null, reasonText, problems: errorProblems(e) };
}

function detailOf(raw: unknown): Record<string, unknown> | null {
  const body = raw && typeof raw === "object" && !Array.isArray(raw) && "detail" in (raw as Record<string, unknown>) ? (raw as Record<string, unknown>).detail : raw;
  return body && typeof body === "object" && !Array.isArray(body) ? (body as Record<string, unknown>) : null;
}

/** `INS:174` → 174 (a pool row linked to that instructor carries their rules); staff keys → null */
export function instructorIdOf(personKey: string): number | null {
  const m = /^INS:(\d+)$/.exec(personKey);
  return m ? Number(m[1]) : null;
}

/**
 * Only the parameters that differ from the defaults go to the backend (the stored plan then shows exactly what the
 * planner changed; `weights` only when one weight differs).
 */
export function changedParams(p: typeof PLAN_DEFAULTS): PlanParams {
  const out: PlanParams = {};
  const d = PLAN_DEFAULTS;
  if (p.students_per_invigilator !== d.students_per_invigilator) out.students_per_invigilator = p.students_per_invigilator;
  if (p.min_per_room !== d.min_per_room) out.min_per_room = p.min_per_room;
  if (p.max_per_room !== null && p.max_per_room !== d.max_per_room) out.max_per_room = p.max_per_room;
  if (p.own_exam !== d.own_exam) out.own_exam = p.own_exam;
  if (p.instructor_pool !== d.instructor_pool) out.instructor_pool = p.instructor_pool;
  if (p.max_per_day !== d.max_per_day) out.max_per_day = p.max_per_day;
  if (p.min_rest !== d.min_rest) out.min_rest = p.min_rest;
  if (p.time_limit_s !== d.time_limit_s) out.time_limit_s = p.time_limit_s;
  if (p.seed !== d.seed) out.seed = p.seed;
  const w: Partial<Record<WeightKey, number>> = {};
  for (const k of WEIGHT_KEYS) if (p.weights[k] !== d.weights[k]) w[k] = p.weights[k];
  if (Object.keys(w).length) out.weights = w;
  return out;
}

/** a stored plan's params merged over the defaults (to prefill a re-run) */
export function paramsFrom(stored: PlanParams | null | undefined): typeof PLAN_DEFAULTS {
  const s = stored ?? {};
  return {
    students_per_invigilator: s.students_per_invigilator ?? PLAN_DEFAULTS.students_per_invigilator,
    min_per_room: s.min_per_room ?? PLAN_DEFAULTS.min_per_room,
    max_per_room: s.max_per_room ?? null,
    own_exam: s.own_exam ?? PLAN_DEFAULTS.own_exam,
    instructor_pool: s.instructor_pool ?? PLAN_DEFAULTS.instructor_pool,
    max_per_day: s.max_per_day ?? PLAN_DEFAULTS.max_per_day,
    min_rest: s.min_rest ?? PLAN_DEFAULTS.min_rest,
    time_limit_s: s.time_limit_s ?? PLAN_DEFAULTS.time_limit_s,
    seed: s.seed ?? PLAN_DEFAULTS.seed,
    weights: { ...PLAN_DEFAULTS.weights, ...(s.weights ?? {}) } as Record<WeightKey, number>,
  };
}
