/**
 * Zod schemas for the Generator Studio API (backend `app/schemas/studio.py`, routers
 * `app/api/v1/studio.py` + `app/api/v1/presets.py`). Field names mirror the backend 1:1; defaults keep
 * the client tolerant of optional fields the backend omits.
 */
import { z } from "zod";
import { utcIso } from "./adapters";
import { ProposedConstraint } from "./schemas";

/** `{tr, en}` text pairs the backend sends for every planner-facing sentence. */
export const Text2 = z.object({ tr: z.string().default(""), en: z.string().default("") });
export type Text2 = z.infer<typeof Text2>;

export const StudioKind = z.enum(["COURSE", "EXAM"]);
export type StudioKind = z.infer<typeof StudioKind>;
export const StudioStep = z.enum(["scope", "classes", "rules", "check", "run"]);
export type StudioStep = z.infer<typeof StudioStep>;
export const STUDIO_STEPS: readonly StudioStep[] = StudioStep.options;

const isoDate = z.preprocess((v) => utcIso(v) ?? v, z.string());

/* ------------------------------------------------------------------------------- draft */

export const Pin = z.object({
  event_id: z.number(),
  room_ids: z.array(z.number()).default([]),
  day: z.number().nullable().optional(),
  start_period: z.number().nullable().optional(),
  // draft-only overrides written by pre-check fixes (backend app/schemas/studio.py Pin): kept so a later
  // PUT of the pins does not silently drop them
  unlock: z.boolean().nullable().optional(),
  required_tags: z.array(z.string()).nullable().optional(),
  size: z.number().nullable().optional(),
  max_rooms: z.number().nullable().optional(),
});
export type Pin = z.infer<typeof Pin>;

export const RuleOverride = z.object({
  hardness: z.enum(["hard", "soft"]).nullable().optional(),
  weight: z.number().nullable().optional(),
});
export type RuleOverride = z.infer<typeof RuleOverride>;

export const DraftParams = z
  .object({
    time_limit_s: z.number().optional(),
    seed: z.number().optional(),
    workers: z.number().optional(),
    weights: z.record(z.string(), z.number()).optional(),
    stability: z.boolean().optional(),
    label: z.string().optional(),
    parent_run_id: z.number().nullable().optional(),
  })
  .catchall(z.unknown());
export type DraftParams = z.infer<typeof DraftParams>;

export const HorizonParams = z
  .object({ weeks: z.array(z.number()).optional(), start_week: z.number().optional(), week: z.number().optional() })
  .catchall(z.unknown());
export type HorizonParams = z.infer<typeof HorizonParams>;

/** `DraftOut` (GET/PUT /terms/{id}/studio). */
export const Draft = z.object({
  draft_id: z.number(),
  term_id: z.number(),
  user_id: z.number().optional(),
  kind: StudioKind,
  version: z.number(),
  etag: z.string().optional(),
  scope: z.object({
    horizon: z.enum(["WEEK", "MONTH", "TERM"]),
    horizon_params: HorizonParams.default({}),
    weeks: z.array(z.number()).default([]),
    holiday_weeks: z.array(z.number()).default([]),
  }),
  excluded_event_ids: z.array(z.number()).default([]),
  pins: z.array(Pin).default([]),
  disabled_builtin_kinds: z.array(z.string()).default([]),
  disabled_rule_ids: z.array(z.number()).default([]),
  rule_overrides: z.record(z.string(), RuleOverride).default({}),
  rule_ids: z.array(z.number()).default([]),
  preset_id: z.number().nullable().optional(),
  last_step: StudioStep.nullable().optional(),
  params: DraftParams.default({}),
  updated_at: isoDate.optional(),
});
export type Draft = z.infer<typeof Draft>;

/** `DraftIn`: partial update, `version` required for optimistic concurrency. */
export interface DraftPatch {
  horizon?: "WEEK" | "MONTH" | "TERM";
  horizon_params?: HorizonParams;
  excluded_event_ids?: number[];
  pins?: Pin[];
  disabled_builtin_kinds?: string[];
  disabled_rule_ids?: number[];
  rule_overrides?: Record<string, RuleOverride>;
  preset_id?: number | null;
  last_step?: StudioStep;
  params?: DraftParams;
}

/** 409 body of PUT /terms/{id}/studio: `{detail: {message, current: DraftOut}}`. */
export const DraftConflict = z.object({ detail: z.object({ message: z.string(), current: Draft }) });

/* -------------------------------------------------------------------------- class list */

export const ChangedField = z.object({ field: z.string(), imported: z.unknown().optional(), current: z.unknown().optional() });
export type ChangedField = z.infer<typeof ChangedField>;

export const ClassRow = z.object({
  id: z.number(),
  kind: StudioKind.default("COURSE"),
  section_id: z.number().nullable().optional(),
  course_code: z.string().nullable().default(null),
  course_name: z.string().nullable().default(null),
  section_label: z.string().nullable().default(null),
  program_id: z.number().nullable().default(null),
  program_name: z.string().nullable().default(null),
  faculty_id: z.number().nullable().default(null),
  faculty_name: z.string().nullable().default(null),
  is_evening: z.boolean().default(false),
  class_year: z.number().nullable().default(null),
  class_years: z.array(z.number()).default([]),
  day: z.number().nullable().default(null),
  days: z.array(z.number()).default([]),
  start_period: z.number().nullable().default(null),
  end_period: z.number().nullable().default(null),
  time_label: z.string().nullable().default(null),
  date: z.string().nullable().optional(),
  weeks: z.array(z.number()).default([]),
  enrolment: z.number().nullable().default(null),
  mode: z.string().nullable().default(null),
  needs_room: z.boolean().default(true),
  flexible_day: z.boolean().default(false),
  requested_room_ids: z.array(z.number()).default([]),
  requested_room_codes: z.array(z.string()).default([]),
  requested_building: z.string().nullable().default(null),
  requested_tags: z.array(z.string()).default([]),
  definitive_room_ids: z.array(z.number()).default([]),
  definitive_room_codes: z.array(z.string()).default([]),
  requested_room_count: z.number().nullable().optional(),
  status: z.string(),
  locked: z.boolean().default(false),
  instructors: z.array(z.string()).default([]),
  included: z.boolean().default(true),
  schedulable: z.boolean().default(true),
  pinned: z.boolean().default(false),
  changed_fields: z.array(ChangedField).default([]),
  rule_ids: z.array(z.number()).default([]),
});
export type ClassRow = z.infer<typeof ClassRow>;

export const ClassPage = z.object({
  items: z.array(ClassRow),
  total: z.number(),
  limit: z.number().default(2000),
  offset: z.number().default(0),
  counts: z.record(z.string(), z.number()).default({}),
});
export type ClassPage = z.infer<typeof ClassPage>;

export const ClassMode = z.enum(["F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"]);
export type ClassMode = z.infer<typeof ClassMode>;

/** `MeetingPatch` (PUT /studio/meetings/bulk). Enrolment and mode land on the section. */
export interface MeetingPatch {
  enrolment?: number | null;
  mode?: ClassMode;
  day?: number | null;
  days?: number[];
  flexible_day?: boolean;
  start_period?: number | null;
  end_period?: number | null;
  weeks?: number[];
  requested_room_ids?: number[];
  requested_building?: string | null;
  requested_tags?: string[];
  definitive_room_ids?: number[];
  needs_room?: boolean;
  locked?: boolean;
}

export const BulkEditResult = z.object({
  results: z.array(z.object({ id: z.number(), ok: z.boolean(), errors: z.array(z.string()).default([]), changed: z.array(z.string()).default([]), warnings: z.array(z.string()).default([]) })),
  updated: z.number(),
  failed: z.number(),
  rows: z.array(ClassRow).default([]),
});
export type BulkEditResult = z.infer<typeof BulkEditResult>;

/* ---------------------------------------------------------------------------- pre-check */

export const FixAction = z.object({ type: z.string(), payload: z.record(z.string(), z.unknown()).default({}) });
export const Fix = z.object({ option: z.string(), label: Text2, action: FixAction, admin_only: z.boolean().default(false) });
export type Fix = z.infer<typeof Fix>;

export const PrecheckCategory = z.enum(["impossible", "clash", "no_match", "info"]);
export type PrecheckCategory = z.infer<typeof PrecheckCategory>;

export const PrecheckItem = z.object({
  id: z.string(),
  category: PrecheckCategory,
  severity: z.enum(["error", "warning", "info"]),
  /** cause bucket: capacity | room_tags | locked_ineligible | pigeonhole | instructor_clash | rule_no_match … */
  group: z.string().default("other"),
  title: Text2,
  message: Text2,
  detail: z.string().default(""),
  event_ids: z.array(z.number()).default([]),
  classes: z.array(z.record(z.string(), z.unknown())).default([]),
  constraint_kinds: z.array(z.string()).default([]),
  constraint_ids: z.array(z.number()).default([]),
  fixes: z.array(Fix).default([]),
});
export type PrecheckItem = z.infer<typeof PrecheckItem>;

export const Readiness = z.enum(["ready", "needs_look", "blocked"]);
export type Readiness = z.infer<typeof Readiness>;

export const Estimate = z.object({ low: z.number(), high: z.number(), words: Text2.optional() });
export type Estimate = z.infer<typeof Estimate>;

export const PrecheckGroup = z.object({
  group: z.string(),
  title: Text2.optional(),
  severity: z.enum(["error", "warning", "info"]),
  count: z.number(),
});
export type PrecheckGroup = z.infer<typeof PrecheckGroup>;

export const Precheck = z.object({
  draft_id: z.number(),
  version: z.number(),
  readiness: Readiness,
  counts: z.record(z.string(), z.number()).default({}),
  /** "> 20 issues: grouped by cause" (the full Bahar answer is ~650 KB: render groups, expand lazily) */
  groups: z.array(PrecheckGroup).default([]),
  items: z.array(PrecheckItem).default([]),
  estimate_s: Estimate,
  summary: Text2,
  duration_s: z.number().default(0),
});
export type Precheck = z.infer<typeof Precheck>;

export const FixResult = z.object({ applied: z.record(z.string(), z.unknown()), draft: Draft, precheck: Precheck });
export type FixResult = z.infer<typeof FixResult>;

/* -------------------------------------------------------------------------------- rules */

export const RuleSource = z.enum(["FILE", "ADMIN", "AI", "UPLOAD", "BUILTIN"]);
export type RuleSource = z.infer<typeof RuleSource>;

export const SourceRef = z.record(z.string(), z.unknown());
export type SourceRef = z.infer<typeof SourceRef>;

export const StudioRule = z.object({
  id: z.number(),
  kind: z.string(),
  params: z.record(z.string(), z.unknown()).default({}),
  hardness: z.enum(["hard", "soft"]),
  weight: z.number(),
  source: z.string().default("ADMIN"),
  source_ref: SourceRef.nullable().optional(),
  nl_text: z.string().nullable().default(null),
  enabled: z.boolean().default(true),
  in_play: z.boolean().default(true),
  override: RuleOverride.nullable().optional(),
  title: Text2,
  affected_count: z.number().nullable().optional(),
});
export type StudioRule = z.infer<typeof StudioRule>;

export const BuiltinRule = z.object({ kind: z.string(), title: Text2, enabled: z.boolean().default(true), disableable: z.boolean().default(false) });
export type BuiltinRule = z.infer<typeof BuiltinRule>;

export const RulesOut = z.object({
  rules: z.array(StudioRule),
  builtins: z.array(BuiltinRule).default([]),
  counts: z.record(z.string(), z.number()).default({}),
});
export type RulesOut = z.infer<typeof RulesOut>;

export const Preview = z.object({
  affected_count: z.number(),
  total: z.number(),
  percent: z.number(),
  targeted: z.boolean(),
  sample: z.array(z.record(z.string(), z.unknown())).default([]),
  issues: z.array(z.string()).default([]),
  notes: z.array(z.string()).default([]),
});
export type Preview = z.infer<typeof Preview>;

export const CopyItem = z.object({
  source_id: z.number(),
  kind: z.string(),
  hardness: z.string(),
  weight: z.number(),
  nl_text: z.string().nullable().optional(),
  params: z.record(z.string(), z.unknown()).default({}),
  affected_count: z.number().default(0),
  reasons: z.array(z.string()).default([]),
  created_id: z.number().nullable().optional(),
});
export type CopyItem = z.infer<typeof CopyItem>;

export const CopyResult = z.object({
  will_match: z.array(CopyItem),
  needs_review: z.array(CopyItem),
  cannot_match: z.array(CopyItem),
  created: z.array(z.number()).default([]),
  dry_run: z.boolean(),
});
export type CopyResult = z.infer<typeof CopyResult>;

/** `ProposedSectionEdit` (app/schemas/ai.py), the upload/NL data edits ("set students to 60"). */
export const ProposedSectionEdit = z.object({
  op: z.enum(["include", "exclude", "set_field"]),
  section_ids: z.array(z.number()).default([]),
  changes: z.record(z.string(), z.unknown()).default({}),
  nl_text: z.string().default(""),
  rationale: z.string().default(""),
  confidence: z.number().default(0),
  status: z.enum(["ok", "needs_review", "rejected"]).default("ok"),
  issues: z.array(z.string()).default([]),
  entities: z.array(z.record(z.string(), z.unknown())).default([]),
  labels: z.array(z.string()).default([]),
  source: z.string().default("AI"),
  source_ref: SourceRef.nullable().optional(),
});
export type ProposedSectionEdit = z.infer<typeof ProposedSectionEdit>;

export const Unparsed = z.object({ text: z.string().default(""), reason: z.string().default(""), source_ref: SourceRef.nullable().optional() });
export type Unparsed = z.infer<typeof Unparsed>;

/** `POST /terms/{id}/preferences/upload` (IngestOut) and NL elicit (ElicitOut), studio view. */
export const Extraction = z.object({
  proposals: z.array(ProposedConstraint).default([]),
  section_edits: z.array(ProposedSectionEdit).default([]),
  unparsed: z.array(Unparsed).default([]),
  assistant_message: z.string().default(""),
  filename: z.string().optional(),
  file_kind: z.string().optional(),
  warnings: z.array(z.string()).default([]),
  detected_columns: z.record(z.string(), z.string()).default({}),
});
export type Extraction = z.infer<typeof Extraction>;

export const AcceptOut = z.object({
  created: z.array(z.number()),
  rejected: z.array(z.record(z.string(), z.unknown())).default([]),
  section_edits_applied: z.array(z.unknown()).default([]),
});
export type AcceptOut = z.infer<typeof AcceptOut>;

/* ---------------------------------------------------------------- no-AI column mapping */

export const MappingRole = z.enum(["course", "section", "program", "year", "enrolment", "day", "time", "room", "building", "mode", "note"]);
export type MappingRole = z.infer<typeof MappingRole>;
export const MAPPING_ROLES: readonly MappingRole[] = MappingRole.options;

export const RoomRule = z.enum(["prefer", "pin", "forbid"]);
export type RoomRule = z.infer<typeof RoomRule>;

export interface MappingSpec {
  columns: Partial<Record<MappingRole, number>>;
  room_rule: RoomRule;
  hardness: "hard" | "soft";
  weight: number;
  header_row?: number | null;
  sheet?: string | null;
}

export const MappingColumns = z.object({
  mode: z.literal("columns"),
  filename: z.string(),
  sheets: z.array(z.string()).default([]),
  sheet: z.string().nullable().optional(),
  header_row: z.number().nullable().optional(),
  row_count: z.number().default(0),
  columns: z.array(z.object({ index: z.number(), header: z.string().default(""), samples: z.array(z.string()).default([]) })),
  suggested_mapping: z.object({
    columns: z.record(z.string(), z.number()).default({}),
    room_rule: RoomRule.default("prefer"),
    hardness: z.enum(["hard", "soft"]).default("soft"),
    weight: z.number().default(5),
  }),
  roles: z.record(z.string(), Text2).default({}),
});
export type MappingColumns = z.infer<typeof MappingColumns>;

export const MappingProposals = z.object({
  mode: z.literal("proposals"),
  filename: z.string(),
  proposals: z.array(ProposedConstraint).default([]),
  section_edits: z.array(ProposedSectionEdit).default([]),
  unparsed: z.array(Unparsed).default([]),
  counts: z.record(z.string(), z.number()).default({}),
});
export type MappingProposals = z.infer<typeof MappingProposals>;

export const MappingResult = z.discriminatedUnion("mode", [MappingColumns, MappingProposals]);
export type MappingResult = z.infer<typeof MappingResult>;

/* ------------------------------------------------------------------------------ presets */

export const Preset = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable().optional(),
  kind: z.string().default("COURSE"),
  rules: z.array(z.record(z.string(), z.unknown())).default([]),
  scope: z.record(z.string(), z.unknown()).default({}),
  filters: z.record(z.string(), z.unknown()).default({}),
  disabled_builtin_kinds: z.array(z.string()).default([]),
  created_by: z.number().nullable().optional(),
  author: z.string().nullable().optional(),
  created_at: isoDate,
  updated_at: isoDate.optional(),
});
export type Preset = z.infer<typeof Preset>;

export const PresetApply = z.object({
  add: z.array(z.record(z.string(), z.unknown())).default([]),
  change: z.array(z.record(z.string(), z.unknown())).default([]),
  turn_off: z.array(z.record(z.string(), z.unknown())).default([]),
  unresolved: z.array(z.record(z.string(), z.unknown())).default([]),
  scope: z.record(z.string(), z.unknown()).nullable().optional(),
  excluded_count: z.number().default(0),
  dry_run: z.boolean(),
  created: z.array(z.number()).default([]),
  draft: Draft.nullable().optional(),
});
export type PresetApply = z.infer<typeof PresetApply>;

/* ------------------------------------------------------------------ generate / summary */

export const GenerateOut = z.object({
  run_id: z.number(),
  status: z.string(),
  draft_id: z.number(),
  draft_version: z.number(),
  events: z.number().default(0),
  excluded: z.number().default(0),
  prompt_text: z.string().default(""),
});
export type GenerateOut = z.infer<typeof GenerateOut>;

export const StudioSummary = z.object({
  draft_id: z.number(),
  version: z.number(),
  kind: z.string().optional(),
  counts: z.object({
    classes_total: z.number().default(0),
    classes_need_room: z.number().default(0),
    classes_in: z.number().default(0),
    classes_out: z.number().default(0),
    classes_without_time: z.number().default(0),
    events: z.number().default(0),
    rooms: z.number().default(0),
    weeks: z.number().default(0),
    pinned: z.number().default(0),
    rules_must: z.number().default(0),
    rules_try: z.number().default(0),
    builtins_off: z.number().default(0),
  }),
  weeks: z.array(z.number()).default([]),
  holiday_weeks: z.array(z.number()).default([]),
  readiness: z.string().default("unknown"),
  estimate_s: Estimate,
  sentence: Text2,
  human_summary: Text2,
  warnings: z.array(z.object({ code: z.string(), count: z.number().default(0), message: Text2 })).default([]),
  last_good_run: z
    .object({ id: z.number(), status: z.string(), soft_score: z.number().nullable().optional(), hard_score: z.number().nullable().optional(), finished_at: isoDate.nullable().optional() })
    .nullable()
    .optional(),
  disabled_builtin_kinds: z.array(z.string()).default([]),
});
export type StudioSummary = z.infer<typeof StudioSummary>;

/* -------------------------------------------------------------------------------- meta */

export const TemplateField = z
  .object({
    name: z.string(),
    type: z.string(),
    param: z.string(),
    required: z.boolean().default(false),
    min: z.number().optional(),
    max: z.number().optional(),
    default: z.unknown().optional(),
    advanced: z.boolean().optional(),
    ordered: z.boolean().optional(),
    min_items: z.number().optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown());
export type TemplateField = z.infer<typeof TemplateField>;

export const RuleTemplate = z.object({
  id: z.string(),
  topic: z.string(),
  kind: z.string(),
  title: Text2,
  sentence: Text2,
  fields: z.array(TemplateField),
  default_hardness: z.enum(["hard", "soft"]),
  default_weight: z.number(),
  allowed_hardness: z.array(z.enum(["hard", "soft"])).default(["hard", "soft"]),
  note: Text2.optional(),
  params_schema: z.unknown().optional(),
  catalog_title: Text2.nullable().optional(),
});
export type RuleTemplate = z.infer<typeof RuleTemplate>;

export const StudioMeta = z.object({
  weight_scale: z.object({
    low: z.number(),
    normal: z.number(),
    high: z.number(),
    default: z.number().optional(),
    labels: z.record(z.string(), Text2).optional(),
    custom_range: z.array(z.number()).default([1, 10]),
  }),
  templates: z.array(RuleTemplate),
  builtins: z.array(z.object({ kind: z.string(), title: Text2, disableable: z.boolean().default(false), admin_only: z.boolean().default(true) })).default([]),
  sources: z.record(z.string(), Text2).default({}),
  hardness: z.record(z.string(), z.object({ label: Text2, help: Text2 })).default({}),
  periods: z.array(z.object({ index: z.number(), start: z.string(), end: z.string(), label: z.string().optional() })).default([]),
  mapping_roles: z.record(z.string(), Text2).default({}),
  catalog: z
    .array(
      z
        .object({
          kind: z.string(),
          title: z.record(z.string(), z.string()).default({}),
          description: z.record(z.string(), z.string()).default({}),
          allowed_hardness: z.array(z.string()).default(["hard", "soft"]),
          default_hardness: z.string().default("soft"),
        })
        .catchall(z.unknown()),
    )
    .default([]),
});
export type StudioMeta = z.infer<typeof StudioMeta>;
