/**
 * Zod schemas for the SmartSched API (/api/v1). Mirrors docs/ARCHITECTURE.md
 * "Domain model" and "API surface". Every response is parsed at the boundary.
 */
import { z } from "zod";

export const Role = z.enum(["ADMIN", "PLANNER", "VIEWER"]);
export type Role = z.infer<typeof Role>;

export const User = z.object({
  id: z.number(),
  email: z.string(),
  full_name: z.string().nullable().optional(),
  role: Role,
  is_active: z.boolean().default(true),
  created_at: z.string().nullable().optional(),
});
export type User = z.infer<typeof User>;

export const LoginResponse = z.object({
  access_token: z.string(),
  token_type: z.string().default("bearer"),
  user: User,
});
export type LoginResponse = z.infer<typeof LoginResponse>;

export const TermKind = z.enum(["REGULAR", "FINAL", "BUT", "SUMMER"]);
export type TermKind = z.infer<typeof TermKind>;

export const Term = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  kind: TermKind,
  start_date: z.string(),
  end_date: z.string(),
  week_count: z.number(),
  is_active: z.boolean(),
});
export type Term = z.infer<typeof Term>;

export const WeekKind = z.enum(["LECTURE", "EXAM", "HOLIDAY", "MAKEUP"]);
export const Week = z.object({
  id: z.number(),
  term_id: z.number(),
  index: z.number(),
  start_date: z.string(),
  kind: WeekKind,
  label: z.string(),
});
export type Week = z.infer<typeof Week>;

export const RoomTag = z.enum(["TIP", "PC", "LAB", "AMPHI"]);
export type RoomTag = z.infer<typeof RoomTag>;

export const Building = z.object({ id: z.number(), code: z.string(), name: z.string() });
export type Building = z.infer<typeof Building>;

export const Room = z.object({
  id: z.number(),
  building_id: z.number(),
  building_code: z.string(),
  code: z.string(),
  display_name: z.string(),
  floor: z.number().nullable(),
  capacity: z.number(),
  exam_capacity: z.number(),
  tags: z.array(RoomTag),
  is_bookable: z.boolean(),
  notes: z.string().nullable().optional(),
  photo_url: z.string().nullable().optional(),
  legacy_crbs_room_id: z.number().nullable().optional(),
  /** 0..1 share of lecture periods occupied this week (optional, server-computed) */
  utilisation: z.number().nullable().optional(),
});
export type Room = z.infer<typeof Room>;

export const Program = z.object({
  id: z.number(),
  faculty_id: z.number(),
  faculty_name: z.string(),
  name: z.string(),
  is_evening: z.boolean(),
});
export type Program = z.infer<typeof Program>;

export const Mode = z.enum(["F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"]);
export type Mode = z.infer<typeof Mode>;

export const RequestStatus = z.enum(["NEW", "PARSED", "NEEDS_REVIEW", "LOCKED"]);
export type RequestStatus = z.infer<typeof RequestStatus>;

export const ParseWarning = z.object({
  row: z.number(),
  field: z.string(),
  value: z.string().nullable(),
  message: z.string(),
  severity: z.enum(["error", "warning", "info"]),
});
export type ParseWarning = z.infer<typeof ParseWarning>;

export const MeetingRequest = z.object({
  id: z.number(),
  section_id: z.number(),
  course_code: z.string(),
  course_name: z.string(),
  section_label: z.string(),
  program_id: z.number(),
  program_name: z.string(),
  class_year: z.number().nullable(),
  enrolment: z.number().nullable(),
  instructor: z.string().nullable(),
  mode: Mode,
  day: z.number().nullable(),
  start_period: z.number().nullable(),
  end_period: z.number().nullable(),
  start_time: z.string().nullable(),
  end_time: z.string().nullable(),
  weeks: z.array(z.number()),
  requested_room_text: z.string().nullable(),
  requested_room_ids: z.array(z.number()),
  requested_building: z.string().nullable(),
  requested_tags: z.array(RoomTag),
  requested_capacity: z.number().nullable(),
  flexible_day: z.boolean(),
  definitive_room_text: z.string().nullable(),
  definitive_room_ids: z.array(z.number()),
  notes: z.string().nullable().optional(),
  status: RequestStatus,
  parse_warnings: z.array(ParseWarning),
});
export type MeetingRequest = z.infer<typeof MeetingRequest>;

export const MeetingRequestUpdate = MeetingRequest.pick({
  day: true,
  start_period: true,
  end_period: true,
  enrolment: true,
  requested_room_ids: true,
  requested_building: true,
  requested_tags: true,
  requested_capacity: true,
  flexible_day: true,
  definitive_room_ids: true,
  status: true,
  notes: true,
}).partial();
export type MeetingRequestUpdate = z.infer<typeof MeetingRequestUpdate>;

export const ExamRequest = z.object({
  id: z.number(),
  term_id: z.number(),
  course_code: z.string(),
  course_name: z.string(),
  program_id: z.number(),
  program_name: z.string(),
  class_year: z.number().nullable(),
  enrolment: z.number().nullable(),
  instructor_text: z.string().nullable(),
  date: z.string().nullable(),
  start_time: z.string().nullable(),
  end_time: z.string().nullable(),
  start_period: z.number().nullable(),
  end_period: z.number().nullable(),
  requested_venue_text: z.string().nullable(),
  requested_room_count: z.number().nullable(),
  requested_min_capacity: z.number().nullable(),
  requested_tags: z.array(RoomTag),
  invigilators_requested: z.number().nullable(),
  on_campus_written: z.boolean(),
  no_exam: z.boolean(),
  definitive_room_text: z.string().nullable(),
  definitive_room_ids: z.array(z.number()),
  merge_key: z.string().nullable(),
  status: RequestStatus,
  parse_warnings: z.array(ParseWarning),
});
export type ExamRequest = z.infer<typeof ExamRequest>;

export const ExamRequestUpdate = ExamRequest.pick({
  date: true,
  start_period: true,
  end_period: true,
  enrolment: true,
  requested_room_count: true,
  requested_min_capacity: true,
  requested_tags: true,
  definitive_room_ids: true,
  status: true,
}).partial();
export type ExamRequestUpdate = z.infer<typeof ExamRequestUpdate>;

export const Paginated = <T extends z.ZodTypeAny>(item: T) =>
  z.object({ items: z.array(item), total: z.number(), page: z.number().default(1), page_size: z.number().default(50) });

export const ImportKind = z.enum(["planning-list", "exam-list", "weekly-grid", "crbs"]);
export type ImportKind = z.infer<typeof ImportKind>;

export const ImportJob = z.object({
  id: z.number(),
  kind: ImportKind,
  filename: z.string(),
  status: z.enum(["QUEUED", "RUNNING", "DONE", "FAILED"]),
  summary: z.object({
    rows: z.number(),
    created: z.number(),
    updated: z.number(),
    skipped: z.number(),
    warnings: z.array(ParseWarning),
  }),
  created_at: z.string(),
});
export type ImportJob = z.infer<typeof ImportJob>;

export const Hardness = z.enum(["hard", "soft"]);
export const ConstraintSource = z.enum(["FILE", "ADMIN", "AI", "UPLOAD", "BUILTIN"]);
export const Constraint = z.object({
  id: z.number(),
  term_id: z.number(),
  run_id: z.number().nullable(),
  kind: z.string(),
  params: z.record(z.string(), z.unknown()),
  hardness: Hardness,
  weight: z.number(),
  source: ConstraintSource,
  nl_text: z.string().nullable(),
  enabled: z.boolean(),
});
export type Constraint = z.infer<typeof Constraint>;

export const RunKind = z.enum(["COURSE", "EXAM"]);
export type RunKind = z.infer<typeof RunKind>;
export const Horizon = z.enum(["WEEK", "MONTH", "TERM"]);
export type Horizon = z.infer<typeof Horizon>;
/** TIMEOUT / ERROR are persisted verbatim from the solver result (SolverResult.status). */
export const RunStatus = z.enum(["QUEUED", "RUNNING", "FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "INFEASIBLE", "TIMEOUT", "ERROR", "FAILED", "CANCELLED"]);
export type RunStatus = z.infer<typeof RunStatus>;

export const Diagnosis = z.object({
  id: z.string(),
  /** position in run.diagnosis (the `{idx}` of the apply route) */
  index: z.number().optional(),
  event_ids: z.array(z.number()),
  event_labels: z.array(z.string()),
  constraint_kinds: z.array(z.string()),
  message: z.string(),
  /** Backend `GET /runs/{id}` structures the solver's suggestion strings; only `applicable` ones can be
   * applied with `POST /runs/{id}/diagnoses/{index}/apply {option_index}`. */
  suggestions: z.array(
    z.object({
      id: z.string(),
      index: z.number().optional(),
      text: z.string(),
      action: z.enum(["release_room", "move", "split", "relax", "unlock", "add_constraint", "manual"]),
      applicable: z.boolean().default(true),
      params: z.record(z.string(), z.unknown()).default({}),
    }),
  ),
  severity: z.enum(["critical", "high", "medium", "low"]),
  /** solver/bridge diagnosis code (``unplaced``, ``input_conflict`` ...) */
  code: z.string().default(""),
  /** planner-facing text (backend templates); preferred over ``message`` when present */
  text: z.object({ tr: z.string(), en: z.string() }).optional(),
});
export type Diagnosis = z.infer<typeof Diagnosis>;

export const RunParams = z.object({
  time_limit_s: z.number().default(60),
  seed: z.number().default(0),
  workers: z.number().default(8),
  stability: z.boolean().default(true),
  weights: z.record(z.string(), z.number()).default({}),
});
export type RunParams = z.infer<typeof RunParams>;

export const ScheduleRun = z.object({
  id: z.number(),
  term_id: z.number(),
  term_code: z.string(),
  kind: RunKind,
  horizon: Horizon,
  horizon_params: z.object({ weeks: z.array(z.number()).default([]), dates: z.array(z.string()).default([]) }),
  status: RunStatus,
  progress: z.number().min(0).max(100).default(0),
  params: RunParams,
  objective_value: z.number().nullable(),
  soft_score: z.number().nullable(),
  hard_score: z.number().nullable(),
  stats: z.record(z.string(), z.union([z.number(), z.string()])).default({}),
  objective_breakdown: z.record(z.string(), z.number()).default({}),
  diagnosis: z.array(Diagnosis).default([]),
  parent_run_id: z.number().nullable(),
  prompt_text: z.string().nullable(),
  created_at: z.string(),
  finished_at: z.string().nullable(),
});
export type ScheduleRun = z.infer<typeof ScheduleRun>;

export const RunCreate = z.object({
  term_id: z.number(),
  kind: RunKind,
  horizon: Horizon,
  horizon_params: z.object({ weeks: z.array(z.number()).optional(), dates: z.array(z.string()).optional() }).optional(),
  params: RunParams.partial().optional(),
  prompt: z.string().optional(),
  parent_run_id: z.number().nullable().optional(),
});
export type RunCreate = z.infer<typeof RunCreate>;

export const RunCreated = z.object({ run_id: z.number() });

/** `POST /runs/{id}/diagnoses/{idx}/apply` */
export const DiagnosisApplyResult = z.object({
  run_id: z.number(),
  child_run_id: z.number().nullable(),
  action: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).default({}),
  constraint_id: z.number().nullable().optional(),
});
export type DiagnosisApplyResult = z.infer<typeof DiagnosisApplyResult>;

export const AssignmentOrigin = z.enum(["SOLVER", "AI_EDIT", "MANUAL", "IMPORT"]);
export const Assignment = z.object({
  id: z.number(),
  run_id: z.number(),
  meeting_request_id: z.number().nullable(),
  exam_request_id: z.number().nullable(),
  label: z.string(),
  course_code: z.string(),
  course_name: z.string().nullable().optional(),
  section_label: z.string().nullable(),
  program_name: z.string().nullable(),
  instructor: z.string().nullable(),
  size: z.number(),
  /** seats of the assigned room(s): lecture capacity (course runs) / exam capacity (exam runs) */
  capacity: z.number().nullable().optional(),
  /** weeks the assignment occupies its room(s) */
  weeks: z.array(z.number()).default([]),
  week: z.number().nullable(),
  day: z.number(),
  date: z.string().nullable(),
  start_period: z.number(),
  end_period: z.number(),
  room_ids: z.array(z.number()),
  is_locked: z.boolean(),
  origin: AssignmentOrigin,
  conflict: z.boolean().default(false),
  conflict_reason: z.string().nullable().optional(),
});
export type Assignment = z.infer<typeof Assignment>;

export const Block = z.object({
  id: z.number(),
  room_id: z.number(),
  day: z.number(),
  start_period: z.number(),
  end_period: z.number(),
  weeks: z.array(z.number()),
  label: z.string(),
  source: z.enum(["GRID_IMPORT", "ADMIN", "CRBS"]),
});
export type Block = z.infer<typeof Block>;

export const GridPeriod = z.object({ index: z.number(), start: z.string(), end: z.string() });

export const GridResponse = z.object({
  run_id: z.number(),
  week: z.number(),
  week_start: z.string(),
  weeks: z.array(Week),
  periods: z.array(GridPeriod),
  rooms: z.array(Room),
  assignments: z.array(Assignment),
  blocks: z.array(Block),
});
export type GridResponse = z.infer<typeof GridResponse>;

export const MoveRequest = z.object({
  room_ids: z.array(z.number()),
  day: z.number(),
  start_period: z.number(),
  end_period: z.number(),
  week: z.number().nullable().optional(),
});
export type MoveRequest = z.infer<typeof MoveRequest>;

export const MoveConflict = z.object({
  kind: z.string(),
  message: z.string(),
  with_assignment_id: z.number().nullable().optional(),
  with_label: z.string().nullable().optional(),
});
export const MoveResponse = z.object({
  ok: z.boolean(),
  assignment: Assignment.nullable(),
  conflicts: z.array(MoveConflict).default([]),
  hard_score: z.number().nullable().optional(),
  soft_score: z.number().nullable().optional(),
});
export type MoveResponse = z.infer<typeof MoveResponse>;

export const ChatMove = z.object({
  assignment_id: z.number(),
  label: z.string(),
  from: z.object({ room: z.string(), day: z.number(), start_period: z.number(), end_period: z.number() }),
  to: z.object({ room: z.string(), day: z.number(), start_period: z.number(), end_period: z.number() }),
});
export const ChatConstraintDiff = z.object({
  op: z.enum(["add", "remove", "update"]),
  kind: z.string(),
  hardness: Hardness,
  weight: z.number(),
  nl_text: z.string(),
});
export const ChatProposal = z.object({
  id: z.string(),
  summary: z.string(),
  moves: z.array(ChatMove),
  constraints: z.array(ChatConstraintDiff),
  /** swaps / locks / re-solve flags and model warnings, as short human-readable lines */
  notes: z.array(z.string()).default([]),
  applied: z.boolean().default(false),
  child_run_id: z.number().nullable().optional(),
});
export type ChatProposal = z.infer<typeof ChatProposal>;

export const ChatMessage = z.object({
  id: z.number(),
  run_id: z.number(),
  role: z.enum(["user", "assistant", "system"]),
  content: z.string(),
  proposal: ChatProposal.nullable().optional(),
  created_at: z.string(),
});
export type ChatMessage = z.infer<typeof ChatMessage>;

export const ChatResponse = z.object({ messages: z.array(ChatMessage) });

export const Settings = z.object({
  anthropic_api_key_masked: z.string().nullable(),
  anthropic_model: z.string(),
  available_models: z.array(z.string()).default([]),
  solver_default_time_limit: z.number(),
  solver_default_workers: z.number(),
  solver_default_seed: z.number(),
  default_weights: z.record(z.string(), z.number()),
});
export type Settings = z.infer<typeof Settings>;

export const SettingsUpdate = z.object({
  anthropic_api_key: z.string().optional(),
  anthropic_model: z.string().optional(),
  solver_default_time_limit: z.number().optional(),
  solver_default_workers: z.number().optional(),
  solver_default_seed: z.number().optional(),
  default_weights: z.record(z.string(), z.number()).optional(),
});
export type SettingsUpdate = z.infer<typeof SettingsUpdate>;

export const TestAiResponse = z.object({ ok: z.boolean(), model: z.string().nullable(), latency_ms: z.number().nullable(), error: z.string().nullable() });
export type TestAiResponse = z.infer<typeof TestAiResponse>;

export const DashboardSummary = z.object({
  term: Term,
  current_week: z.number(),
  rooms_total: z.number(),
  rooms_bookable: z.number(),
  sections_total: z.number(),
  requests_total: z.number(),
  requests_needs_review: z.number(),
  utilisation: z.number(),
  utilisation_by_building: z.array(z.object({ building: z.string(), utilisation: z.number(), rooms: z.number() })),
  peak_hours: z.array(z.object({ day: z.number(), period: z.number(), occupancy: z.number() })),
  /** real building × day / building × period matrices (backend `GET /dashboard`); optional for the composed fallback */
  utilisation_building_day: z.array(z.object({ building: z.string(), day: z.number(), utilisation: z.number() })).default([]),
  utilisation_building_period: z.array(z.object({ building: z.string(), period: z.number(), utilisation: z.number() })).default([]),
  utilisation_week: z.number().optional(),
  requests_pending: z.number().optional(),
  active_run_id: z.number().nullable().optional(),
  utilisation_run_id: z.number().nullable().optional(),
  conflicts: z.number(),
  last_runs: z.array(ScheduleRun),
});
export type DashboardSummary = z.infer<typeof DashboardSummary>;

export const ApiError = z.object({
  detail: z.union([z.string(), z.array(z.object({ msg: z.string(), loc: z.array(z.union([z.string(), z.number()])).optional() }))]),
  error_id: z.string().optional(),
});
export type ApiError = z.infer<typeof ApiError>;

/* ------------------------------------------------------------------ AI layer (app/schemas/ai.py) */

export const AiUsage = z.object({
  model: z.string().nullable().optional(),
  input_tokens: z.number().default(0),
  output_tokens: z.number().default(0),
  estimated_cost_usd: z.number().default(0),
});

/** `ProposedConstraint`: one typed rule the model extracted (ids resolved server-side, never by the model). */
export const ProposedConstraint = z.object({
  kind: z.string(),
  params: z.record(z.string(), z.unknown()).default({}),
  hardness: Hardness.default("soft"),
  weight: z.number().default(1),
  nl_text: z.string().default(""),
  rationale: z.string().default(""),
  confidence: z.number().default(0),
  title: z.string().nullable().optional(),
  status: z.enum(["ok", "needs_review", "rejected"]).default("ok"),
  issues: z.array(z.string()).default([]),
  entities: z.array(z.record(z.string(), z.unknown())).default([]),
  source: z.string().default("AI"),
  source_ref: z.record(z.string(), z.unknown()).nullable().optional(),
});
export type ProposedConstraint = z.infer<typeof ProposedConstraint>;

/** `POST /terms/{id}/elicit` (and `/preferences/upload`, which adds file metadata). */
export const ElicitResult = z.object({
  proposals: z.array(ProposedConstraint),
  section_edits: z.array(z.record(z.string(), z.unknown())).default([]),
  unparsed: z.array(z.record(z.string(), z.unknown())).default([]),
  assistant_message: z.string().default(""),
  usage: AiUsage.optional(),
  filename: z.string().optional(),
  warnings: z.array(z.string()).default([]),
});
export type ElicitResult = z.infer<typeof ElicitResult>;

export const AcceptResult = z.object({
  created: z.array(z.number()),
  rejected: z.array(z.record(z.string(), z.unknown())).default([]),
  section_edits_applied: z.array(z.unknown()).default([]),
});
export type AcceptResult = z.infer<typeof AcceptResult>;

export const ExplainResult = z.object({
  text: z.string(),
  sections: z.array(z.record(z.string(), z.unknown())).default([]),
  source: z.enum(["model", "template"]).default("template"),
});
export type ExplainResult = z.infer<typeof ExplainResult>;

export const AiCatalog = z.object({
  kinds: z.array(
    z.object({
      kind: z.string(),
      title: z.record(z.string(), z.string()),
      description: z.record(z.string(), z.string()),
      allowed_hardness: z.array(z.string()),
      default_hardness: z.string(),
      implicit: z.boolean().default(false),
    }),
  ),
});
export type AiCatalog = z.infer<typeof AiCatalog>;

export const ChatApplyResult = z.object({
  child_run_id: z.number().nullable(),
  messages: z.array(ChatMessage),
  status: z.string().nullable().optional(),
  rejected: z.array(z.record(z.string(), z.unknown())).default([]),
});
export type ChatApplyResult = z.infer<typeof ChatApplyResult>;
