/**
 * Normalises payloads from the FastAPI backend (smartsched/backend/app/api/v1) into the
 * frontend schemas in ./schemas.ts. Every adapter is idempotent: it accepts both the backend
 * shape and its own already-normalised output.
 */
import { PERIODS } from "@/lib/time";

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : v === null || v === undefined ? null : String(v));
const num = (v: unknown, fallback: number | null = null): number | null => (typeof v === "number" && Number.isFinite(v) ? v : typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)) ? Number(v) : fallback);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const nums = (v: unknown): number[] => arr(v).map((x) => num(x)).filter((x): x is number => x !== null);
const strs = (v: unknown): string[] => arr(v).map(str).filter((x): x is string => x !== null);

/** FastAPI serialises naive UTC datetimes ("2026-10-08T07:30:12.5"); without a zone JS would read them
 * as local time (3 h off in Türkiye). Append "Z" to date-times that carry no offset. */
export function utcIso(v: unknown): string | null {
  const s = str(v);
  if (!s) return null;
  return /T\d{2}:\d{2}/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s) ? `${s}Z` : s;
}

/** "HH:MM:SS" → "HH:MM" */
export function clock(v: unknown): string | null {
  const s = str(v);
  if (!s) return null;
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? `${m[1].padStart(2, "0")}:${m[2]}` : s;
}

/** Accepts an array, or a Page {items, total, limit, offset}. */
export function listOf(v: unknown): unknown[] {
  if (Array.isArray(v)) return v;
  if (isRec(v) && Array.isArray(v.items)) return v.items;
  return [];
}

/** Backend Page {items,total,limit,offset} → {items,total,page,page_size}. */
export function page(v: unknown): unknown {
  if (!isRec(v)) return v;
  if ("page" in v) return v;
  const limit = num(v.limit, 50) ?? 50;
  const offset = num(v.offset, 0) ?? 0;
  return { items: arr(v.items), total: num(v.total, arr(v.items).length), page: Math.floor(offset / Math.max(1, limit)) + 1, page_size: limit };
}

const ROOM_TAGS = new Set(["TIP", "PC", "LAB", "AMPHI"]);
export function room(v: unknown): unknown {
  if (!isRec(v)) return v;
  const code = str(v.code) ?? "";
  const floorRaw = v.floor;
  const floor = typeof floorRaw === "string" ? (/^z/i.test(floorRaw) ? 0 : num(floorRaw)) : num(floorRaw);
  return {
    ...v,
    building_code: str(v.building_code) ?? (code[0]?.toLocaleUpperCase("tr-TR") ?? "?"),
    building_id: num(v.building_id, 0),
    display_name: str(v.display_name) ?? code,
    floor,
    capacity: num(v.capacity, 0),
    exam_capacity: num(v.exam_capacity, 0) ?? 0,
    tags: strs(v.tags).map((t) => t.toLocaleUpperCase("tr-TR")).filter((t) => ROOM_TAGS.has(t)),
    is_bookable: v.is_bookable !== false,
  };
}

export function program(v: unknown): unknown {
  if (!isRec(v)) return v;
  return { ...v, faculty_id: num(v.faculty_id, 8), faculty_name: str(v.faculty_name) ?? "", is_evening: v.is_evening === true };
}

export function term(v: unknown): unknown {
  if (!isRec(v)) return v;
  return { ...v, start_date: str(v.start_date) ?? "", end_date: str(v.end_date) ?? "", week_count: num(v.week_count, 14) };
}

export function week(v: unknown): unknown {
  if (!isRec(v)) return v;
  return { ...v, start_date: str(v.start_date) ?? "", label: str(v.label) ?? `W${num(v.index, 0)}` };
}

export function meeting(v: unknown): unknown {
  if (!isRec(v)) return v;
  const instructors = strs(v.instructors);
  return {
    ...v,
    course_code: str(v.course_code) ?? "?",
    course_name: str(v.course_name) ?? "",
    section_label: str(v.section_label) ?? "1",
    program_id: num(v.program_id, 0),
    program_name: str(v.program_name) ?? "",
    class_year: num(v.class_year),
    enrolment: num(v.enrolment),
    instructor: str(v.instructor) ?? (instructors.length ? instructors.join(" / ") : null),
    mode: str(v.mode) ?? "F2F",
    start_time: clock(v.start_time),
    end_time: clock(v.end_time),
    weeks: nums(v.weeks),
    requested_room_ids: nums(v.requested_room_ids),
    requested_tags: strs(v.requested_tags).filter((t) => ROOM_TAGS.has(t)),
    definitive_room_ids: nums(v.definitive_room_ids),
    flexible_day: v.flexible_day === true,
    parse_warnings: arr(v.parse_warnings).map(warning),
  };
}

export function exam(v: unknown): unknown {
  if (!isRec(v)) return v;
  return {
    ...v,
    course_name: str(v.course_name) ?? "",
    program_id: num(v.program_id, 0),
    program_name: str(v.program_name) ?? "",
    class_year: num(v.class_year),
    start_time: clock(v.start_time),
    end_time: clock(v.end_time),
    requested_tags: strs(v.requested_tags).filter((t) => ROOM_TAGS.has(t)),
    definitive_room_ids: nums(v.definitive_room_ids),
    on_campus_written: v.on_campus_written === true,
    no_exam: v.no_exam === true,
    parse_warnings: arr(v.parse_warnings).map(warning),
  };
}

export function warning(v: unknown): unknown {
  if (!isRec(v)) return { row: 0, field: "", value: null, message: String(v), severity: "info" };
  const sev = str(v.severity) ?? "warning";
  return { row: num(v.row, 0), field: str(v.field) ?? str(v.column) ?? "", value: str(v.value) ?? str(v.raw), message: str(v.message) ?? str(v.code) ?? "", severity: sev === "error" || sev === "info" ? sev : "warning" };
}

export function importJob(v: unknown): unknown {
  if (!isRec(v)) return v;
  const summary = isRec(v.summary) ? v.summary : {};
  return {
    ...v,
    filename: str(v.filename) ?? "",
    status: str(v.status) ?? "DONE",
    summary: { rows: num(summary.rows, 0), created: num(summary.created, 0), updated: num(summary.updated, 0), skipped: num(summary.skipped, 0), warnings: arr(summary.warnings).map(warning) },
    created_at: utcIso(v.created_at) ?? new Date().toISOString(),
  };
}

const FIX_ACTIONS = new Set(["release_room", "move", "split", "relax", "unlock", "add_constraint", "manual"]);
/** solver severities (error / warning / info) → UI severities */
const SEVERITY: Record<string, string> = { critical: "critical", high: "high", medium: "medium", low: "low", error: "high", warning: "medium", info: "low" };

export function diagnosis(v: unknown, i: number): unknown {
  if (!isRec(v)) return { id: String(i), index: i, event_ids: [], event_labels: [], constraint_kinds: [], message: String(v), suggestions: [], severity: "high" };
  const index = num(v.index, i) ?? i;
  return {
    id: str(v.id) ?? String(index),
    index,
    event_ids: nums(v.event_ids),
    event_labels: strs(v.event_labels),
    constraint_kinds: strs(v.constraint_kinds),
    message: str(v.message) ?? "",
    suggestions: arr(v.suggestions).map((s, j) => {
      if (!isRec(s)) return { id: `s${j}`, index: j, text: String(s), action: "manual", applicable: false, params: {} };
      const action = str(s.action) ?? "manual";
      return {
        id: str(s.id) ?? `s${j}`,
        index: num(s.index, j) ?? j,
        text: str(s.text) ?? "",
        action: FIX_ACTIONS.has(action) ? action : "manual",
        applicable: s.applicable !== false && action !== "manual",
        params: isRec(s.params) ? s.params : {},
      };
    }),
    severity: SEVERITY[str(v.severity) ?? "high"] ?? "high",
    code: str(v.code) ?? "",
    // planner-facing TR / EN text rendered by the backend from code + params (no ids, day names, clock times)
    text: isRec(v.text) ? { tr: str(v.text.tr) ?? "", en: str(v.text.en) ?? "" } : undefined,
  };
}

/** `"s3"` / `"3"` → 3 (suggestion ids from {@link diagnosis}). */
export function optionIndex(id: string): number {
  const m = /(\d+)$/.exec(id);
  return m ? Number(m[1]) : 0;
}

const ACTIVE = new Set(["QUEUED", "RUNNING"]);
export function run(v: unknown): unknown {
  if (!isRec(v)) return v;
  const stats = isRec(v.stats) ? v.stats : {};
  const params = isRec(v.params) ? v.params : {};
  const hp = isRec(v.horizon_params) ? v.horizon_params : {};
  const status = str(v.status) ?? "QUEUED";
  const breakdown = isRec(v.objective_breakdown) ? v.objective_breakdown : isRec(stats.objective_breakdown) ? stats.objective_breakdown : {};
  const flatStats: Record<string, number | string> = {};
  for (const [k, val] of Object.entries(stats)) if (typeof val === "number" || typeof val === "string") flatStats[k] = val;
  return {
    ...v,
    horizon_params: { weeks: nums(hp.weeks), dates: strs(hp.dates) },
    progress: num(v.progress, num(stats.progress, ACTIVE.has(status) ? 0 : 100)),
    params: { time_limit_s: num(params.time_limit_s, 60), seed: num(params.seed, 0), workers: num(params.workers, 8), stability: params.stability !== false, weights: isRec(params.weights) ? params.weights : {} },
    objective_value: num(v.objective_value),
    soft_score: num(v.soft_score),
    hard_score: num(v.hard_score),
    stats: flatStats,
    objective_breakdown: Object.fromEntries(Object.entries(breakdown).map(([k, val]) => [k, num(val, 0)])),
    diagnosis: arr(v.diagnosis).map(diagnosis),
    parent_run_id: num(v.parent_run_id),
    prompt_text: str(v.prompt_text),
    created_at: utcIso(v.created_at) ?? new Date().toISOString(),
    finished_at: utcIso(v.finished_at),
  };
}

export function assignment(v: unknown): unknown {
  if (!isRec(v)) return v;
  const codes = strs(v.course_codes);
  const label = str(v.label) ?? str(v.display_label) ?? codes.join(" / ") ?? "?";
  const reasons = strs(v.conflict_reasons);
  const instructors = strs(v.instructors);
  return {
    ...v,
    label,
    course_code: str(v.course_code) ?? codes[0] ?? label.split(" §")[0],
    course_name: str(v.course_name),
    section_label: str(v.section_label),
    program_name: str(v.program_name),
    instructor: str(v.instructor) ?? (instructors.length ? instructors.join(" / ") : null),
    size: num(v.size, num(v.enrolment, 0)),
    capacity: num(v.capacity),
    weeks: Array.isArray(v.week_set) ? nums(v.week_set) : nums(v.weeks),
    week: num(v.week),
    day: num(v.day, 1),
    date: str(v.date),
    room_ids: nums(v.room_ids),
    is_locked: v.is_locked === true || v.locked === true,
    origin: str(v.origin) ?? "SOLVER",
    conflict: v.conflict === true || v.is_conflict === true,
    conflict_reason: str(v.conflict_reason) ?? (reasons.length ? reasons.join("; ") : null),
  };
}

/** Backend grid = day × room × 18 cells; frontend grid = rooms + assignment spans + blocks. */
export function grid(v: unknown): unknown {
  if (!isRec(v)) return v;
  if (Array.isArray(v.rooms) && Array.isArray(v.assignments)) {
    return { ...v, rooms: arr(v.rooms).map(room), assignments: arr(v.assignments).map(assignment), weeks: arr(v.weeks).map(week), blocks: arr(v.blocks) };
  }
  const runId = num(v.run_id, 0) ?? 0;
  const roomsById = new Map<number, Rec>();
  const assignments = new Map<string, Rec>();
  const blocks = new Map<string, Rec>();
  for (const d of arr(v.days)) {
    if (!isRec(d)) continue;
    const day = num(d.day, 1) ?? 1;
    for (const r of arr(d.rooms)) {
      if (!isRec(r)) continue;
      const roomId = num(r.room_id, 0) ?? 0;
      if (!roomsById.has(roomId)) roomsById.set(roomId, room({ id: roomId, code: r.code, display_name: r.display_name, capacity: r.capacity, exam_capacity: r.exam_capacity, tags: r.tags, is_bookable: r.is_bookable !== false, floor: r.floor ?? null, building_id: r.building_id ?? 0 }) as Rec);
      for (const c of arr(r.cells)) {
        if (!isRec(c) || c.head !== true) continue;
        const key = `${c.kind}:${num(c.id, 0)}:${roomId}:${day}`;
        if (c.kind === "block") {
          const source = str(c.source);
          blocks.set(key, { id: num(c.id, 0), room_id: roomId, day, start_period: num(c.start_period, 1), end_period: num(c.end_period, 1), weeks: nums(c.weeks), label: str(c.label) ?? "BLOCK", source: source === "ADMIN" || source === "CRBS" ? source : "GRID_IMPORT" });
        } else {
          const id = num(c.id, 0) ?? 0;
          const existing = assignments.get(`a:${id}`);
          if (existing) {
            (existing.room_ids as number[]).push(roomId);
            continue;
          }
          // enriched backend cells carry course/programme/size/conflict data (services/grid.py)
          assignments.set(`a:${id}`, assignment({ ...c, id, run_id: runId, meeting_request_id: num(c.meeting_request_id), exam_request_id: num(c.exam_request_id), label: c.label, week: c.week !== undefined ? c.week : num(v.week), day, start_period: c.start_period, end_period: c.end_period, room_ids: [roomId], is_locked: c.locked === true, origin: c.origin, tags: c.tags }) as Rec);
        }
      }
    }
  }
  return {
    run_id: runId,
    week: num(v.week, 1),
    week_start: str(v.week_start) ?? "",
    weeks: arr(v.weeks).map(week),
    periods: Array.isArray(v.periods) && v.periods.length ? v.periods : PERIODS,
    rooms: [...roomsById.values()],
    assignments: [...assignments.values()],
    blocks: [...blocks.values()],
  };
}

export function moveResponse(v: unknown): unknown {
  if (!isRec(v)) return v;
  return {
    ok: v.ok === true,
    assignment: isRec(v.assignment) ? assignment(v.assignment) : null,
    conflicts: arr(v.conflicts).map((c) => (isRec(c) ? { kind: str(c.kind) ?? str(c.type) ?? "conflict", message: str(c.message) ?? str(c.detail) ?? JSON.stringify(c), with_assignment_id: num(c.with_assignment_id ?? c.assignment_id), with_label: str(c.with_label ?? c.label) } : { kind: "conflict", message: String(c) })),
    hard_score: num(v.hard_score),
    soft_score: num(v.soft_score),
  };
}

function parseWeights(v: unknown): Record<string, number> {
  let obj: unknown = v;
  if (typeof v === "string") {
    try {
      obj = JSON.parse(v);
    } catch {
      obj = {};
    }
  }
  return isRec(obj) ? Object.fromEntries(Object.entries(obj).map(([k, val]) => [k, num(val, 0) ?? 0])) : {};
}

/** Opus is the backend default (settings_service / config); listed first. */
export const DEFAULT_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"];
export function settings(v: unknown): unknown {
  if (!isRec(v)) return v;
  if ("anthropic_api_key_masked" in v) return { ...v, available_models: strs(v.available_models).length ? v.available_models : DEFAULT_MODELS };
  const key = v.anthropic_api_key;
  const masked = isRec(key) ? (key.set ? str(key.masked) : null) : str(key);
  const model = str(v.anthropic_model) ?? DEFAULT_MODELS[0];
  return {
    anthropic_api_key_masked: masked,
    anthropic_model: model,
    available_models: strs(v.available_models).length ? strs(v.available_models) : [...new Set([...DEFAULT_MODELS, model])],
    solver_default_time_limit: num(v.solver_default_time_limit, 120),
    solver_default_workers: num(v.solver_default_workers, num(v.solver_workers, 8)),
    solver_default_seed: num(v.solver_default_seed, 0),
    default_weights: Object.keys(parseWeights(v.default_weights)).length ? parseWeights(v.default_weights) : parseWeights(v.solver_weights),
  };
}

/** Frontend SettingsUpdate → backend SettingsUpdate (app/schemas/settings.py); keys without a column ride in `extra`. */
export function settingsUpdateBody(body: Rec): Rec {
  const out: Rec = {};
  const extra: Rec = {};
  if (body.anthropic_api_key !== undefined) out.anthropic_api_key = body.anthropic_api_key;
  if (body.anthropic_model !== undefined) out.anthropic_model = body.anthropic_model;
  if (body.solver_default_time_limit !== undefined) out.solver_default_time_limit = body.solver_default_time_limit;
  if (body.solver_default_workers !== undefined) out.solver_workers = body.solver_default_workers;
  if (body.default_weights !== undefined) out.solver_weights = body.default_weights;
  if (body.solver_default_seed !== undefined) extra.solver_default_seed = body.solver_default_seed;
  return { ...out, ...(Object.keys(extra).length ? { extra } : {}) };
}

export function testAi(v: unknown): unknown {
  if (!isRec(v)) return v;
  return { ok: v.ok === true, model: str(v.model), latency_ms: num(v.latency_ms), error: str(v.error) ?? (v.ok === true ? null : str(v.detail)) };
}

/** Backend list query names: q→search, page/page_size→limit/offset. */
export function listQuery(q: Record<string, string | number | boolean | null | undefined> | undefined): Record<string, string | number | boolean | null | undefined> | undefined {
  if (!q) return q;
  const { q: text, page, page_size, ...rest } = q;
  const limit = page_size !== undefined && page_size !== null ? Number(page_size) : undefined;
  const pageNo = page !== undefined && page !== null ? Number(page) : 1;
  return { ...rest, q: text, search: text, page, page_size, limit, offset: limit !== undefined ? (pageNo - 1) * limit : undefined };
}

/* ------------------------------------------------------------------ AI chat (app/ai/chat.py) */

const periodsOf = (v: unknown): [number, number] => {
  const m = /P(\d+)\s*-\s*P?(\d+)/.exec(str(v) ?? "");
  return m ? [Number(m[1]), Number(m[2])] : [1, 1];
};
const roomsText = (v: unknown): string => strs(v).join(" + ") || "?";

/** Backend `ProposedDiff` (stored on the assistant message) → UI `ChatProposal`. */
export function proposalFromDiff(diff: unknown, applied: unknown): unknown {
  if (!isRec(diff)) return null;
  const moves: Rec[] = [];
  const constraints: Rec[] = [];
  const notes: string[] = [];
  for (const op of arr(diff.operations)) {
    if (!isRec(op)) continue;
    const kind = str(op.op);
    if (kind === "move") {
      const b = isRec(op.before) ? op.before : {};
      const a = isRec(op.after) ? op.after : {};
      const [bs, be] = periodsOf(b.periods);
      const [as, ae] = periodsOf(a.periods);
      moves.push({
        assignment_id: num(op.assignment_id, 0),
        label: str(op.label) ?? str(b.label) ?? `#${num(op.assignment_id, 0)}`,
        from: { room: roomsText(b.rooms), day: num(b.day, 1), start_period: bs, end_period: be },
        to: { room: roomsText(a.rooms), day: num(a.day, num(b.day, 1)), start_period: as, end_period: ae },
      });
    } else if (kind === "add_constraint" && isRec(op.constraint)) {
      const c = op.constraint;
      constraints.push({ op: "add", kind: str(c.kind) ?? "?", hardness: c.hardness === "hard" ? "hard" : "soft", weight: num(c.weight, 1), nl_text: str(c.nl_text) ?? str(c.title) ?? "" });
    } else if (kind === "remove_constraint") {
      constraints.push({ op: "remove", kind: str(op.label) ?? `#${num(op.constraint_id, 0)}`, hardness: "soft", weight: 0, nl_text: str(op.label) ?? "" });
    } else if (kind === "set_weight") {
      constraints.push({ op: "update", kind: str(op.label) ?? `#${num(op.constraint_id, 0)}`, hardness: op.hardness === "hard" ? "hard" : "soft", weight: num(op.weight, 0), nl_text: str(op.label) ?? "" });
    } else if (kind === "swap") {
      notes.push(`swap #${num(op.assignment_id_a, 0)} ↔ #${num(op.assignment_id_b, 0)}${op.label ? ` (${str(op.label)})` : ""}`);
    } else if (kind) {
      notes.push(`${kind}${op.label ? ` ${str(op.label)}` : op.assignment_id ? ` #${num(op.assignment_id, 0)}` : ""}`);
    }
  }
  if (diff.re_solve === true) notes.push(diff.stability === false ? "re-solve" : "re-solve (stable)");
  notes.push(...strs(diff.warnings));
  const child = num(applied);
  return { id: str(diff.id) ?? "", summary: str(diff.summary) ?? "", moves, constraints, notes, applied: child !== null, child_run_id: child };
}

/** `GET /runs/{id}/chat` (list of ChatMessageOut) or the mock's `{messages}` → `{messages: ChatMessage[]}`. */
export function chatHistory(v: unknown, runId: number): unknown {
  if (isRec(v) && Array.isArray(v.messages)) return v;
  return {
    messages: arr(v).map((m) => {
      if (!isRec(m)) return m;
      const role = str(m.role);
      const diffCall = arr(m.tool_calls).find((tc) => isRec(tc) && tc.type === "diff");
      return {
        id: num(m.id, 0),
        run_id: num(m.run_id, runId),
        role: role === "user" || role === "assistant" ? role : "system",
        content: str(m.content) ?? "",
        proposal: isRec(diffCall) ? proposalFromDiff(diffCall.diff, diffCall.applied) : null,
        created_at: utcIso(m.created_at) ?? new Date().toISOString(),
      };
    }),
  };
}

/** `GET /dashboard`: the embedded TermOut / RunOut need the same normalisation as their own routes. */
export function dashboard(v: unknown): unknown {
  if (!isRec(v)) return v;
  return { ...v, term: term(v.term), last_runs: listOf(v.last_runs).map(run) };
}
