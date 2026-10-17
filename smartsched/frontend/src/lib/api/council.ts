/**
 * Ingestion Council API (`/api/v1/council`, backend app/api/v1/council.py + app/schemas/council.py):
 * upload any files, follow the council per file and step, review low-confidence items, commit into a term.
 */
import { z } from "zod";
import { API_PREFIX, request } from "./client";

export const CouncilStep = z.object({
  id: z.number(),
  file_index: z.number().nullable(),
  agent: z.string(),
  status: z.enum(["RUNNING", "DONE", "SKIPPED", "FAILED"]),
  attempt: z.number(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  duration_ms: z.number().nullable(),
  model: z.string().nullable(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  cost_usd: z.number(),
  message: z.string().nullable(),
});
export type CouncilStep = z.infer<typeof CouncilStep>;

export const CouncilFile = z.object({
  index: z.number(),
  filename: z.string(),
  size: z.number(),
  status: z.string(),
  format: z.string().nullable().optional(),
  /** structured (read on the server) | ai (needs the model) */
  route_kind: z.string().nullable().optional(),
  /** the e-mail this file was attached to (its index in the job) */
  parent: z.number().nullable().optional(),
  language: z.string().nullable().optional(),
  route: z.string().nullable().optional(),
  kinds: z.array(z.string()).default([]),
  counts: z.record(z.string(), z.number()).default({}),
  rule_texts: z.number().default(0),
  message: z.string().nullable().optional(),
  steps: z.array(CouncilStep).default([]),
});
export type CouncilFile = z.infer<typeof CouncilFile>;

export const TermGroup = z.object({
  key: z.string(),
  code: z.string(),
  name: z.string(),
  kind: z.string(),
  year: z.number().nullable(),
  files: z.array(z.number()),
  week_count: z.number(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  confidence: z.number(),
  evidence: z.array(z.string()).default([]),
});
export type TermGroup = z.infer<typeof TermGroup>;

export const CouncilPlan = z.object({
  groups: z.array(TermGroup),
  unassigned_files: z.array(z.number()).default([]),
  global_files: z.array(z.number()).default([]),
  period_grid: z.object({ source: z.string(), periods: z.array(z.object({ index: z.number(), start: z.string(), end: z.string() })), coverage: z.number().nullable() }),
});
export type CouncilPlan = z.infer<typeof CouncilPlan>;

export const JOB_STATUSES = ["QUEUED", "RUNNING", "REVIEW", "READY", "COMMITTED", "FAILED"] as const;
export const CouncilJob = z.object({
  id: z.number(),
  status: z.enum(JOB_STATUSES),
  mode: z.string(),
  ai_mode: z.enum(["llm", "heuristic"]),
  lang: z.string(),
  year_hint: z.number().nullable(),
  progress: z.number(),
  phase: z.string().nullable(),
  files: z.array(CouncilFile),
  cross_steps: z.array(CouncilStep),
  plan: CouncilPlan.nullable(),
  summary: z.record(z.string(), z.unknown()),
  usage: z.record(z.string(), z.unknown()),
  commits: z.array(z.record(z.string(), z.unknown())),
  error: z.string().nullable(),
  created_at: z.string(),
  finished_at: z.string().nullable(),
});
export type CouncilJob = z.infer<typeof CouncilJob>;

/** Every kind app/council/review.py emits (ITEM_KINDS; a backend contract test reads this list). A kind the
 * frontend does not know yet still parses (`kind` is any string) and is shown under a generic label (T-R1-21). */
export const REVIEW_KINDS = ["classification", "mapping", "merge", "issue", "rule", "rule_text", "plan", "file", "ai_rows", "person_merge"] as const;
export type ReviewKind = (typeof REVIEW_KINDS)[number];
export const isReviewKind = (k: string): k is ReviewKind => (REVIEW_KINDS as readonly string[]).includes(k);
export const ReviewDecision = z.object({ action: z.enum(["accept", "reject", "edit"]), value: z.record(z.string(), z.unknown()).nullable().optional() }).passthrough();
export const ReviewItem = z
  .object({
    id: z.string(),
    kind: z.string(),
    title: z.string(),
    blocking: z.boolean(),
    decision: ReviewDecision.nullable(),
    file_index: z.number().nullable().optional(),
    confidence: z.number().nullable().optional(),
    current: z.record(z.string(), z.unknown()).optional(),
    alternatives: z.array(z.array(z.union([z.string(), z.number(), z.null()]))).optional(),
    samples: z.array(z.string()).optional(),
    options: z.array(z.string()).optional(),
    severity: z.string().optional(),
  })
  .passthrough();
export type ReviewItem = z.infer<typeof ReviewItem>;

export const ReviewOut = z.object({
  job_id: z.number(),
  status: z.string(),
  blocking: z.number(),
  items: z.array(ReviewItem),
  plan: CouncilPlan.nullable(),
  threshold: z.number(),
  saved: z.number().nullable().optional(),
  errors: z.array(z.string()).default([]),
  rerun_files: z.array(z.number()).default([]),
  /** a mapping / classification change re-reads files on the job queue: RUNNING until it finished */
  rerun_queued: z.boolean().default(false),
  /** false for planning.view-only readers: no samples, texts or names, counts only */
  content: z.boolean().default(true),
});
export type ReviewOut = z.infer<typeof ReviewOut>;

/** `result.baseline_run` of a commit (app/council/baseline.py `as_baseline_run`): the schedule-map entries of the
 * committed files written to the term's one "Baseline: imported schedule" run (`mode: auto`), to a run chosen at
 * commit (`mode: run`), or not written (`mode: skip`, `skipped`); the other counters (`linked_by_start`,
 * `clipped_outside_term`, `entries_unplaceable`, `exam_entries_skipped`, ...) come along. In a dry run `run_id` is
 * null while the run would be new (`run_created`). */
export const BaselineRunResult = z
  .object({
    run_id: z.number().nullable(),
    run_created: z.boolean(),
    mode: z.enum(["auto", "skip", "run"]).default("auto"),
    skipped: z.boolean().default(false),
    entries: z.number().default(0),
    created: z.number().default(0),
    updated: z.number().default(0),
    unchanged: z.number().default(0),
    linked: z.number().default(0),
    unlinked: z.number().default(0),
  })
  .catchall(z.union([z.number(), z.boolean(), z.string(), z.null()]));
export type BaselineRunResult = z.infer<typeof BaselineRunResult>;
/** `ScheduleRun.label` / `params.source` of that run */
export const BASELINE_LABEL = "Baseline: imported schedule";
export const BASELINE_SOURCE = "COUNCIL_BASELINE";
/** the term's baseline import run (a schedule map written by an intake commit), not a solver run */
export function isBaselineRun(r: { params: { source?: string } }): boolean {
  return r.params.source === BASELINE_SOURCE;
}

export const CommitOut = z
  .object({
    baseline_run: BaselineRunResult.nullish(),
    term_id: z.number(),
    term_code: z.string(),
    term_created: z.boolean(),
    files: z.array(z.number()),
    fast_path: z.array(z.record(z.string(), z.unknown())),
    general: z.record(z.string(), z.number()),
    constraints_created: z.array(z.number()),
    constraints_rejected: z.array(z.unknown()),
    /** every constraint the commit wrote (importer preference rules + accepted proposals; T-R1-24) */
    constraints_total: z.number().nullish(),
    /** a commit has no undo (T-R1-24) */
    reversible: z.boolean().nullish(),
    /** per entity, the same counts as the dry run */
    changes: z.record(z.string(), z.object({ create: z.number().default(0), update: z.number().default(0), unchanged: z.number().default(0), conflict: z.number().default(0) }).passthrough()).nullish(),
  })
  .passthrough();
export type CommitOut = z.infer<typeof CommitOut>;

export interface DecisionIn {
  id: string;
  action: "accept" | "reject" | "edit";
  value?: Record<string, unknown> | null;
}
export interface CommitIn {
  group?: number;
  term_id?: number;
  term?: { code?: string; name?: string; kind?: string; week_count?: number; start_date?: string };
  files?: number[];
  include_rules?: boolean;
  allow_pending?: boolean;
  /** run the writer in a rolled-back transaction and answer the diff (POST commit {dry_run: true}) */
  dry_run?: boolean;
  /** a planner's edit vs a changed file value: keep the edit or take the file */
  on_conflict?: "keep" | "take";
  /** where the schedule maps go: the term's baseline run (auto, default), nowhere (skip) or another COURSE run */
  baseline?: BaselineTarget;
}
export type BaselineTarget = { mode: "auto" } | { mode: "skip" } | { mode: "run"; run_id: number };

/** One cross-file review row (GET /council/jobs/{id}/rows, P19-A2). */
export const CouncilRow = z
  .object({
    id: z.string(),
    file_index: z.number(),
    record_index: z.number(),
    entity: z.string().nullable(),
    method: z.enum(["direct", "ai"]),
    review_required: z.boolean().default(false),
    state: z.string(),
    confidence: z.number(),
    low_confidence: z.boolean().default(false),
    values: z.record(z.string(), z.unknown()).default({}),
    issues: z.array(z.unknown()).default([]),
    provenance: z.record(z.string(), z.unknown()).default({}),
  })
  .passthrough();
export type CouncilRow = z.infer<typeof CouncilRow>;
export const CouncilRows = z.object({
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  items: z.array(CouncilRow),
  counts: z.object({ state: z.record(z.string(), z.number()).default({}), method: z.record(z.string(), z.number()).default({}), total: z.number().default(0) }).passthrough(),
  bulk_max: z.number().default(50),
});
export type CouncilRows = z.infer<typeof CouncilRows>;
export interface RowDecisionIn {
  row_id: string;
  action: "accept" | "reject" | "edit";
  value?: Record<string, unknown> | null;
}
/** Commit dry run: per-entity counts and the row diffs (app/council/dryrun.py summarize). */
export const CommitDryRun = z
  .object({
    on_conflict: z.string(),
    counts: z.record(z.string(), z.object({ create: z.number(), update: z.number(), unchanged: z.number(), conflict: z.number() })),
    rows: z.array(z.record(z.string(), z.unknown())).default([]),
    rows_total: z.number().default(0),
    conflicts_total: z.number().default(0),
    /** the commit's term, files and the schedule map's baseline run, as the real commit would answer them */
    result: z
      .object({ term_code: z.string().nullish(), term_created: z.boolean().nullish(), baseline_run: BaselineRunResult.nullish() })
      .passthrough()
      .default({}),
  })
  .passthrough();
export type CommitDryRun = z.infer<typeof CommitDryRun>;

/** One remembered intake decision (GET /council/memory, app/council/memory_admin.py). */
export const MEMORY_KINDS = ["intake_mapping", "intake_lexicon", "intake_kind", "intake_term", "intake_merge", "intake_rule"] as const;
export const IntakeMemoryItem = z
  .object({
    id: z.number(),
    signature: z.string(),
    kind: z.string(),
    group: z.string(),
    attribute: z.string(),
    value: z.string().nullable(),
    action: z.string().nullable().optional(),
    created_at: z.string(),
    created_by: z.object({ id: z.number().nullable(), name: z.string().nullable() }).nullable(),
    job_id: z.number(),
    job_exists: z.boolean().default(true),
    term_id: z.number().nullable(),
    /** the row the next matching upload is offered (the latest per kind, signature and attribute) */
    effective: z.boolean().default(true),
    description: z.object({ tr: z.string(), en: z.string() }),
    context: z.record(z.string(), z.unknown()).default({}),
  })
  .passthrough();
export type IntakeMemoryItem = z.infer<typeof IntakeMemoryItem>;
export const IntakeMemoryGroup = z
  .object({
    signature: z.string(),
    group: z.string(),
    kinds: z.array(z.string()),
    jobs: z.array(z.number()),
    count: z.number(),
    last_at: z.string(),
    label: z.object({ tr: z.string(), en: z.string() }),
    ids: z.array(z.number()),
  })
  .passthrough();
export type IntakeMemoryGroup = z.infer<typeof IntakeMemoryGroup>;
export const IntakeMemoryList = z.object({
  items: z.array(IntakeMemoryItem),
  groups: z.array(IntakeMemoryGroup),
  total: z.number(),
  /** false for planning.view-only readers: no headers, merge names or rule texts */
  content: z.boolean().default(true),
  truncated: z.boolean().default(false),
});
export type IntakeMemoryList = z.infer<typeof IntakeMemoryList>;
/** A forget is a learning reset of scope `intake`: undo with POST /learning/resets/{id}/undo for 30 days. */
export const MemoryForgetOut = z.object({ id: z.number(), forgotten: z.number(), ids: z.array(z.number()), undo_until: z.string(), undoable: z.boolean() }).passthrough();
export type MemoryForgetOut = z.infer<typeof MemoryForgetOut>;

export const councilApi = {
  create: (files: File[], opts: { mode?: "auto" | "general"; lang?: string; yearHint?: number; ai?: boolean } = {}) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    fd.append("mode", opts.mode ?? "auto");
    fd.append("lang", opts.lang ?? "en");
    if (opts.yearHint) fd.append("year_hint", String(opts.yearHint));
    if (opts.ai === false) fd.append("ai", "false");
    return request("/council/jobs", { method: "POST", formData: fd, schema: CouncilJob });
  },
  /** `lang`: the reader's language; the council's messages come back in Turkish for "tr" (T-R1-23) */
  list: (limit = 5) => request("/council/jobs", { query: { limit }, schema: z.array(CouncilJobBrief), silent: true }),
  get: (id: number, lang?: string) => request(`/council/jobs/${id}`, { query: lang ? { lang } : undefined, schema: CouncilJob, silent: true }),
  review: (id: number, lang?: string) => request(`/council/jobs/${id}/review`, { query: lang ? { lang } : undefined, schema: ReviewOut }),
  decide: (id: number, decisions: DecisionIn[], lang?: string) =>
    request(`/council/jobs/${id}/review`, { method: "POST", query: lang ? { lang } : undefined, body: { decisions }, schema: ReviewOut }),
  commit: (id: number, body: CommitIn) => request(`/council/jobs/${id}/commit`, { method: "POST", body: { ...body, dry_run: false }, schema: CommitOut }),
  dryRun: (id: number, body: CommitIn) => request(`/council/jobs/${id}/commit`, { method: "POST", body: { ...body, dry_run: true }, schema: CommitDryRun }),
  rows: (id: number, q: { state?: string; method?: "direct" | "ai"; file?: number; q?: string; offset?: number; limit?: number } = {}) =>
    request(`/council/jobs/${id}/rows`, { query: q, schema: CouncilRows }),
  decideRows: (id: number, decisions: RowDecisionIn[], confirm = false) =>
    request(`/council/jobs/${id}/rows/decisions`, { method: "POST", body: { decisions, confirm }, schema: z.record(z.string(), z.unknown()) }),
  eventsUrl: (id: number, lang?: string) => `${API_PREFIX}/council/jobs/${id}/events${lang ? `?lang=${encodeURIComponent(lang)}` : ""}`,
  memory: (q: { signature?: string; kind?: string; job_id?: number } = {}) => request("/council/memory", { query: q, schema: IntakeMemoryList }),
  forget: (id: number) => request(`/council/memory/${id}`, { method: "DELETE", schema: MemoryForgetOut }),
  forgetSignature: (signature: string) => request("/council/memory", { method: "DELETE", query: { signature }, schema: MemoryForgetOut }),
};

/** One line of GET /council/jobs (newest first): the recent jobs a reload or a new tab reopens (T-R1-26). */
export const CouncilJobBrief = z.object({ id: z.number(), status: z.enum(JOB_STATUSES), files: z.number(), ai_mode: z.string(), created_at: z.string() }).passthrough();
export type CouncilJobBrief = z.infer<typeof CouncilJobBrief>;

export const ACTIVE_JOB = new Set<CouncilJob["status"]>(["QUEUED", "RUNNING"]);

/** Council agents in pipeline order (per file, then across files). */
export const FILE_AGENTS = ["intake", "structure", "extract", "rules"] as const;
export const CROSS_AGENTS = ["reconcile", "planner", "critic"] as const;
