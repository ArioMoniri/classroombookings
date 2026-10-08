/**
 * MSW request handlers for /api/v1. Used by the Next route-handler proxy in mock mode
 * (NEXT_PUBLIC_API_MOCK=1) via `getResponse()`, and by vitest via `setupServer()`.
 * State is in-memory and deterministic at start-up (see data.ts).
 */
import { HttpResponse, http, type DefaultBodyType, type PathParams } from "msw";
import { PERIODS, PERIODS_PER_DAY, rangesOverlap } from "@/lib/time";
import type {
  Assignment,
  DashboardSummary,
  ExamRequest,
  ImportJob,
  ImportKind,
  MeetingRequest,
  MoveRequest,
  MoveResponse,
  ProposedConstraint,
  RunCreate,
  ScheduleRun,
  Settings,
  SettingsUpdate,
  User,
} from "@/lib/api/schemas";
import {
  assignmentsByRun,
  blocks,
  buildings,
  chatSeed,
  constraints,
  examRequests,
  findRoom,
  importJobsSeed,
  meetingRequests,
  programs,
  rooms,
  runs,
  sampleWarnings,
  settingsSeed,
  terms,
  users,
  weeks,
} from "./data";
import { createCouncilHandlers, resetCouncilMock } from "./council";
import { createStudioHandlers, freshStudioState, studioSeedConstraints, type MockConstraint, type StudioMockState } from "./studio";

/* ------------------------------------------------------------------------------- state */
/** Backend `ChatMessageOut`: the proposed diff rides on the assistant message's tool_calls. */
interface MockChatMessage {
  id: number;
  run_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  tool_calls: Record<string, unknown>[];
  created_at: string;
}
/** Backend `ProposedDiff` (app/schemas/ai.py), the subset the mock produces. */
interface MockDiff {
  id: string;
  run_id: number;
  operations: Record<string, unknown>[];
  re_solve: boolean;
  stability: boolean;
  summary: string;
  warnings: string[];
}

interface MockState {
  meetings: MeetingRequest[];
  exams: ExamRequest[];
  runs: ScheduleRun[];
  assignments: Map<number, Assignment[]>;
  chats: Map<number, MockChatMessage[]>;
  settings: Settings;
  users: User[];
  imports: ImportJob[];
  runStartedAt: Map<number, number>;
  nextId: number;
  constraints: MockConstraint[];
  studio: StudioMockState;
}

function freshState(): MockState {
  return {
    meetings: structuredClone(meetingRequests),
    exams: structuredClone(examRequests),
    runs: structuredClone(runs),
    assignments: new Map([...assignmentsByRun.entries()].map(([k, v]) => [k, structuredClone(v)])),
    chats: new Map([[1, chatSeed.map((m) => ({ id: m.id, run_id: m.run_id, role: m.role, content: m.content, tool_calls: [], created_at: m.created_at }))]]),
    settings: structuredClone(settingsSeed),
    users: structuredClone(users),
    imports: structuredClone(importJobsSeed),
    runStartedAt: new Map(),
    nextId: 5000,
    constraints: [...structuredClone(constraints), ...structuredClone(studioSeedConstraints)],
    studio: freshStudioState(),
  };
}

let state: MockState = freshState();
export function resetMockState(): void {
  state = freshState();
  resetCouncilMock();
}

const SOLVE_MS = Number(process.env.MOCK_SOLVE_MS ?? 5000);

const json = <T extends DefaultBodyType>(body: T, init?: ResponseInit) => HttpResponse.json(body, init);
const notFound = (what: string) => json({ detail: `${what} not found` }, { status: 404 });
const num = (v: string | readonly string[] | undefined): number => Number(Array.isArray(v) ? v[0] : v);

/* ----------------------------------------------------------------------- run lifecycle */
function tickRun(run: ScheduleRun): ScheduleRun {
  if (run.status !== "QUEUED" && run.status !== "RUNNING") return run;
  const started = state.runStartedAt.get(run.id) ?? Date.now();
  const elapsed = Date.now() - started;
  if (elapsed < 600) {
    run.status = "QUEUED";
    run.progress = 0;
  } else if (elapsed < SOLVE_MS) {
    run.status = "RUNNING";
    run.progress = Math.min(99, Math.round(((elapsed - 600) / (SOLVE_MS - 600)) * 100));
  } else {
    const wantsInfeasible = /imkans|impossible|infeasible|olmaz/i.test(run.prompt_text ?? "");
    const base = state.assignments.get(wantsInfeasible ? 2 : 1) ?? [];
    const source = run.parent_run_id !== null ? (state.assignments.get(run.parent_run_id) ?? base) : base;
    state.assignments.set(
      run.id,
      source.map((a, i) => ({ ...a, id: run.id * 10_000 + i + 1, run_id: run.id, origin: "SOLVER" as const })),
    );
    run.status = wantsInfeasible ? "INFEASIBLE" : "FEASIBLE";
    run.progress = 100;
    run.hard_score = wantsInfeasible ? 96 : 100;
    run.soft_score = wantsInfeasible ? 74 : Math.min(99, 88 + (run.id % 7));
    run.objective_value = wantsInfeasible ? null : 1700 + run.id * 13;
    run.objective_breakdown = { room_preference: 400 + run.id, building_preference: 205, min_capacity_waste: 960, same_room_across_weeks: 60, stability: 150 };
    run.stats = { solve_time_s: SOLVE_MS / 1000, events: state.assignments.get(run.id)?.length ?? 0, rooms: rooms.length, conflicts: wantsInfeasible ? 3 : 0, unplaced: 0 };
    run.diagnosis = wantsInfeasible ? structuredClone(runs[1].diagnosis) : [];
    run.finished_at = new Date().toISOString();
  }
  return run;
}

function getRun(id: number): ScheduleRun | undefined {
  const run = state.runs.find((r) => r.id === id);
  return run ? tickRun(run) : undefined;
}

/* -------------------------------------------------------------------- move validation */
function weeksOf(a: Assignment): number[] {
  if (a.week !== null) return [a.week];
  const req = state.meetings.find((m) => m.id === a.meeting_request_id);
  return req?.weeks ?? Array.from({ length: 14 }, (_, i) => i + 1);
}

function validateMove(runId: number, moving: Assignment, body: MoveRequest): MoveResponse["conflicts"] {
  const conflicts: MoveResponse["conflicts"] = [];
  if (body.start_period < 1 || body.end_period > PERIODS_PER_DAY || body.end_period < body.start_period) {
    conflicts.push({ kind: "day_window", message: `Periods must be within P1–P${PERIODS_PER_DAY}` });
  }
  const targetRooms = body.room_ids.map((id) => rooms.find((r) => r.id === id)).filter((r): r is NonNullable<typeof r> => r !== undefined);
  if (targetRooms.length === 0) conflicts.push({ kind: "room_pin", message: "Unknown room" });
  const capacity = targetRooms.reduce((s, r) => s + r.capacity, 0);
  if (capacity < moving.size) conflicts.push({ kind: "capacity", message: `${targetRooms.map((r) => r.display_name).join(" + ")} holds ${capacity} < ${moving.size} students` });
  const isMedicine = moving.program_name === "Tıp";
  for (const r of targetRooms) {
    if (r.tags.includes("TIP") && !isMedicine) conflicts.push({ kind: "room_tags", message: `${r.display_name} is a TIP room (Faculty of Medicine only)` });
  }
  const movingWeeks = body.week !== null && body.week !== undefined ? [body.week] : weeksOf(moving);
  const others = (state.assignments.get(runId) ?? []).filter((a) => a.id !== moving.id);
  for (const r of targetRooms) {
    for (const other of others) {
      if (!other.room_ids.includes(r.id) || other.day !== body.day) continue;
      if (!rangesOverlap(other.start_period, other.end_period, body.start_period, body.end_period)) continue;
      if (!weeksOf(other).some((w) => movingWeeks.includes(w))) continue;
      conflicts.push({ kind: "no_room_overlap", message: `${r.display_name} is taken by ${other.label} (P${other.start_period}–P${other.end_period})`, with_assignment_id: other.id, with_label: other.label });
    }
    for (const b of blocks) {
      if (b.room_id !== r.id || b.day !== body.day) continue;
      if (!rangesOverlap(b.start_period, b.end_period, body.start_period, body.end_period)) continue;
      if (!b.weeks.some((w) => movingWeeks.includes(w))) continue;
      conflicts.push({ kind: "room_closed", message: `${r.display_name} is pre-occupied (${b.label}) on P${b.start_period}–P${b.end_period}` });
    }
  }
  return conflicts;
}

/* ---------------------------------------------------------------------------- chat */
function proposeFromMessage(runId: number, text: string): MockDiff | null {
  const assignments = state.assignments.get(runId) ?? [];
  const codeMatch = /([A-ZÇĞİÖŞÜ]{2,4})\s?(\d{3})/i.exec(text);
  const roomMatch = /\b([A-D])\s?([zZ]?\d{2,3})\b/.exec(text.replace(/[A-ZÇĞİÖŞÜ]{2,4}\s?\d{3}/gi, ""));
  const dayWords: Record<string, number> = { pazartesi: 1, monday: 1, salı: 2, sali: 2, tuesday: 2, çarşamba: 3, carsamba: 3, wednesday: 3, perşembe: 4, persembe: 4, thursday: 4, cuma: 5, friday: 5 };
  const dayMatch = Object.keys(dayWords).find((k) => text.toLocaleLowerCase("tr-TR").includes(k));
  const diff = (operations: Record<string, unknown>[], summary: string, reSolve = false): MockDiff => ({ id: `d${state.nextId++}`, run_id: runId, operations, re_solve: reSolve, stability: true, summary, warnings: [] });
  if (codeMatch) {
    const code = `${codeMatch[1].toLocaleUpperCase("tr-TR")} ${codeMatch[2]}`;
    const target = assignments.find((a) => a.course_code.startsWith(code));
    if (!target) return null;
    const room = roomMatch ? findRoom(`${roomMatch[1]}${roomMatch[2]}`) : undefined;
    const fromRoom = rooms.find((r) => r.id === target.room_ids[0]);
    const day = dayMatch ? dayWords[dayMatch] : target.day;
    const dest = room ?? rooms.find((r) => r.is_bookable && r.capacity >= target.size && validateMove(runId, target, { room_ids: [r.id], day, start_period: target.start_period, end_period: target.end_period }).length === 0);
    if (!dest) return null;
    return diff(
      [
        {
          op: "move",
          assignment_id: target.id,
          day: day !== target.day ? day : null,
          room_ids: [dest.id],
          label: target.label,
          before: { label: target.label, day: target.day, periods: `P${target.start_period}-P${target.end_period}`, rooms: [fromRoom?.display_name ?? "?"] },
          after: { day, periods: `P${target.start_period}-P${target.end_period}`, rooms: [dest.display_name] },
        },
      ],
      `1 move: ${target.label} → ${dest.display_name}`,
    );
  }
  if (/tip|blok|block|akşam|evening|kapasite|capacity|aynı derslik|same room/i.test(text)) {
    const kind = /tip/i.test(text) ? "room_tags" : /blok|block/i.test(text) ? "building_preference" : "same_room_across_weeks";
    return diff([{ op: "add_constraint", constraint: { kind, params: {}, hardness: "soft", weight: 3, nl_text: text, status: "ok" } }], "1 new rule · re-solve (stable)", true);
  }
  return null;
}

function chatFor(runId: number): MockChatMessage[] {
  let list = state.chats.get(runId);
  if (!list) {
    list = [];
    state.chats.set(runId, list);
  }
  return list;
}

function findDiff(runId: number, diffId: string): { diff: MockDiff; call: Record<string, unknown> } | null {
  for (const m of chatFor(runId)) {
    for (const call of m.tool_calls) {
      const d = call.diff as MockDiff | undefined;
      if (call.type === "diff" && d?.id === diffId) return { diff: d, call };
    }
  }
  return null;
}

/** Child run sharing the parent's settings (backend: `apply_diff`, diagnosis apply). */
function childRun(parent: ScheduleRun, prompt: string, status: ScheduleRun["status"]): ScheduleRun {
  const id = Math.max(...state.runs.map((r) => r.id)) + 1;
  const child: ScheduleRun = { ...structuredClone(parent), id, status, progress: status === "QUEUED" ? 0 : 100, parent_run_id: parent.id, prompt_text: prompt, created_at: new Date().toISOString(), finished_at: status === "QUEUED" ? null : new Date().toISOString(), diagnosis: [] };
  state.runs.push(child);
  if (status === "QUEUED") state.runStartedAt.set(id, Date.now());
  return child;
}

/* ---------------------------------------------------------------------------- utils */
function paginate<T>(items: T[], url: URL) {
  const page = Number(url.searchParams.get("page") ?? 1);
  const pageSize = Number(url.searchParams.get("page_size") ?? 50);
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), total: items.length, page, page_size: pageSize };
}

function textOf(m: MeetingRequest | ExamRequest): string {
  const instr = "instructor" in m ? m.instructor : m.instructor_text;
  return `${m.course_code} ${m.course_name} ${m.program_name} ${instr ?? ""}`.toLocaleLowerCase("tr-TR");
}

function roomUtilisation(runId: number, week: number): Map<number, number> {
  const map = new Map<number, number>();
  const list = (state.assignments.get(runId) ?? []).filter((a) => weeksOf(a).includes(week));
  for (const a of list) for (const rid of a.room_ids) map.set(rid, (map.get(rid) ?? 0) + (a.end_period - a.start_period + 1));
  for (const b of blocks) if (b.weeks.includes(week)) map.set(b.room_id, (map.get(b.room_id) ?? 0) + (b.end_period - b.start_period + 1));
  const total = 5 * 11; // weekday daytime periods
  return new Map([...map.entries()].map(([k, v]) => [k, Math.min(1, v / total)]));
}

/* -------------------------------------------------------------------------- handlers */
const base = "*/api/v1";

const studioHandlers = createStudioHandlers(() => ({
  meetings: state.meetings,
  exams: state.exams,
  constraints: state.constraints,
  runs: state.runs,
  settings: state.settings,
  studio: state.studio,
  nextId: () => state.nextId++,
  startRun: (run: ScheduleRun) => {
    state.runs.push(run);
    state.runStartedAt.set(run.id, Date.now());
  },
  getRun,
}));

export const handlers = [
  ...createCouncilHandlers(base),
  ...studioHandlers,
  http.post(`${base}/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    if (!body.email || body.password !== "admin") return json({ detail: "Invalid credentials" }, { status: 401 });
    const user = state.users.find((u) => u.email === body.email) ?? { ...state.users[0], email: body.email };
    return json({ access_token: `mock.${Buffer.from(body.email).toString("base64url")}.token`, token_type: "bearer", user });
  }),
  http.get(`${base}/auth/me`, ({ request }) => {
    const auth = request.headers.get("authorization") ?? "";
    if (!auth.startsWith("Bearer mock.")) return json({ detail: "Not authenticated" }, { status: 401 });
    const email = Buffer.from(auth.split(".")[1] ?? "", "base64url").toString();
    return json(state.users.find((u) => u.email === email) ?? { ...state.users[0], email });
  }),

  http.get(`${base}/dashboard`, ({ request }) => {
    const url = new URL(request.url);
    const termId = Number(url.searchParams.get("term_id") ?? 1);
    const term = terms.find((t) => t.id === termId) ?? terms[0];
    const util = roomUtilisation(1, 7);
    const byBuilding = buildings.map((b) => {
      const rs = rooms.filter((r) => r.building_id === b.id && r.is_bookable);
      const avg = rs.reduce((s, r) => s + (util.get(r.id) ?? 0), 0) / Math.max(1, rs.length);
      return { building: b.code, utilisation: Number(avg.toFixed(2)), rooms: rs.length };
    });
    const peak: DashboardSummary["peak_hours"] = [];
    const list = state.assignments.get(1) ?? [];
    for (let day = 1; day <= 5; day++) {
      for (const p of PERIODS) {
        const occ = list.filter((a) => a.day === day && a.start_period <= p.index && a.end_period >= p.index).length;
        peak.push({ day, period: p.index, occupancy: Number((occ / rooms.filter((r) => r.is_bookable).length).toFixed(2)) });
      }
    }
    const summary: DashboardSummary = {
      term,
      current_week: 7,
      rooms_total: rooms.length,
      rooms_bookable: rooms.filter((r) => r.is_bookable).length,
      sections_total: state.meetings.length,
      requests_total: state.meetings.length + state.exams.length,
      requests_needs_review: state.meetings.filter((m) => m.status === "NEEDS_REVIEW").length + state.exams.filter((e) => e.status === "NEEDS_REVIEW").length,
      utilisation: Number((byBuilding.reduce((s, b) => s + b.utilisation * b.rooms, 0) / Math.max(1, byBuilding.reduce((s, b) => s + b.rooms, 0))).toFixed(2)),
      utilisation_by_building: byBuilding,
      peak_hours: peak,
      utilisation_building_day: byBuilding.flatMap((b) => [1, 2, 3, 4, 5, 6, 7].map((day) => ({ building: b.building, day, utilisation: day <= 5 ? b.utilisation : Number((b.utilisation * 0.2).toFixed(2)) }))),
      utilisation_building_period: byBuilding.flatMap((b) => PERIODS.map((p) => ({ building: b.building, period: p.index, utilisation: Number(Math.min(1, b.utilisation * (p.index <= 11 ? 1.2 : 0.4)).toFixed(2)) }))),
      utilisation_week: 7,
      requests_pending: state.meetings.filter((m) => m.status !== "LOCKED").length + state.exams.filter((e) => e.status !== "LOCKED").length,
      active_run_id: 1,
      utilisation_run_id: 1,
      conflicts: (state.assignments.get(2) ?? []).filter((a) => a.conflict).length,
      last_runs: state.runs.map(tickRun).slice(-5).reverse(),
    };
    return json(summary);
  }),

  http.get(`${base}/terms`, () => json(terms)),
  http.get(`${base}/terms/:id/weeks`, ({ params }) => json(weeks.filter((w) => w.term_id === num(params.id)))),
  http.get(`${base}/buildings`, () => json(buildings)),
  http.get(`${base}/programs`, () => json(programs)),

  http.get(`${base}/rooms`, ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.toLocaleLowerCase("tr-TR");
    const building = url.searchParams.get("building");
    const tag = url.searchParams.get("tag");
    const util = roomUtilisation(1, 7);
    let list = rooms.map((r) => ({ ...r, utilisation: Number((util.get(r.id) ?? 0).toFixed(2)) }));
    if (q) list = list.filter((r) => `${r.display_name} ${r.code} ${r.tags.join(" ")} ${r.capacity}`.toLocaleLowerCase("tr-TR").includes(q));
    if (building) list = list.filter((r) => r.building_code === building);
    if (tag) list = list.filter((r) => r.tags.includes(tag as (typeof r.tags)[number]));
    return json(list);
  }),
  http.get(`${base}/rooms/:id`, ({ params }) => {
    const room = rooms.find((r) => r.id === num(params.id));
    if (!room) return notFound("Room");
    const util = roomUtilisation(1, 7);
    return json({ ...room, utilisation: Number((util.get(room.id) ?? 0).toFixed(2)) });
  }),
  http.put(`${base}/rooms/:id`, async ({ params, request }) => {
    const room = rooms.find((r) => r.id === num(params.id));
    if (!room) return notFound("Room");
    Object.assign(room, (await request.json()) as Partial<typeof room>);
    return json(room);
  }),

  http.get(`${base}/requests/meetings`, ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.toLocaleLowerCase("tr-TR");
    const status = url.searchParams.get("status");
    const program = url.searchParams.get("program_id");
    let list = state.meetings;
    if (q) list = list.filter((m) => textOf(m).includes(q));
    if (status) list = list.filter((m) => m.status === status);
    if (program) list = list.filter((m) => m.program_id === Number(program));
    return json(paginate(list, url));
  }),
  http.put(`${base}/requests/meetings/:id`, async ({ params, request }) => {
    const m = state.meetings.find((x) => x.id === num(params.id));
    if (!m) return notFound("Request");
    Object.assign(m, (await request.json()) as Partial<MeetingRequest>);
    return json(m);
  }),
  http.get(`${base}/requests/exams`, ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.toLocaleLowerCase("tr-TR");
    const status = url.searchParams.get("status");
    let list = state.exams;
    if (q) list = list.filter((m) => textOf(m).includes(q));
    if (status) list = list.filter((m) => m.status === status);
    return json(paginate(list, url));
  }),
  http.put(`${base}/requests/exams/:id`, async ({ params, request }) => {
    const m = state.exams.find((x) => x.id === num(params.id));
    if (!m) return notFound("Request");
    Object.assign(m, (await request.json()) as Partial<ExamRequest>);
    return json(m);
  }),

  http.get(`${base}/imports`, () => json([...state.imports].reverse())),
  http.get(`${base}/imports/:id`, ({ params }) => {
    const job = state.imports.find((j) => j.id === num(params.id));
    return job ? json(job) : notFound("Import job");
  }),
  http.post<PathParams<"kind">>(`${base}/imports/:kind`, async ({ params, request }) => {
    const kind = String(params.kind) as ImportKind;
    const fd = await request.formData().catch(() => null);
    const file = fd?.get("file");
    const filename = file instanceof File ? file.name : kind === "crbs" ? String(fd?.get("dsn") ?? "mysql://crbs") : "upload.xlsx";
    const rowsByKind: Record<ImportKind, number> = { "planning-list": 1529, "exam-list": 926, "weekly-grid": 19, crbs: 412 };
    const warnings = kind === "planning-list" ? sampleWarnings() : kind === "exam-list" ? sampleWarnings().slice(0, 5) : sampleWarnings().slice(0, 2);
    const rows = rowsByKind[kind] ?? 100;
    const job: ImportJob = {
      id: state.nextId++,
      kind,
      filename,
      status: "DONE",
      summary: { rows, created: rows - warnings.filter((w) => w.severity === "error").length, updated: 0, skipped: warnings.filter((w) => w.severity === "error").length, warnings },
      created_at: new Date().toISOString(),
    };
    state.imports.push(job);
    return json(job, { status: 201 });
  }),

  http.get(`${base}/constraints`, ({ request }) => {
    const url = new URL(request.url);
    const runId = url.searchParams.get("run_id");
    const run = runId ? state.runs.find((r) => r.id === Number(runId)) : undefined;
    const termId = url.searchParams.get("term_id") ? Number(url.searchParams.get("term_id")) : (run?.term_id ?? null);
    return json(state.constraints.filter((c) => (termId === null || c.term_id === termId) && (!runId || c.run_id === null || c.run_id === Number(runId))));
  }),
  http.post(`${base}/terms/:id/elicit/accept`, async ({ params, request }) => {
    const body = (await request.json()) as { proposals: ProposedConstraint[]; run_id?: number | null };
    const created = body.proposals.map((p) => {
      const id = state.nextId++;
      state.constraints.push({ id, term_id: num(params.id), run_id: body.run_id ?? null, kind: p.kind, params: p.params, hardness: p.hardness, weight: p.weight, source: "AI", nl_text: p.nl_text, enabled: true });
      return id;
    });
    return json({ created, rejected: [], section_edits_applied: [] });
  }),
  http.get(`${base}/ai/catalog`, () =>
    json({ kinds: ["capacity", "room_tags", "building_preference", "day_window", "room_preference", "same_room_across_weeks"].map((kind) => ({ kind, title: { tr: kind, en: kind }, description: { tr: "", en: "" }, params_schema: {}, examples: [], allowed_hardness: ["hard", "soft"], default_hardness: "soft", implicit: false, registered: true })), tools: [], selectors: {} }),
  ),
  http.post(`${base}/runs/:id/explain`, ({ params }) => {
    const run = getRun(num(params.id));
    if (!run) return notFound("Run");
    const text = run.status === "INFEASIBLE" ? `Çizelge #${run.id} uygun değil: ${run.diagnosis.length} sorun bulundu.` : `Çizelge #${run.id}: katı kısıtlar ${run.hard_score ?? "—"}/100, yumuşak ${run.soft_score ?? "—"}/100.`;
    return json({ text, sections: [], source: "template" });
  }),

  http.get(`${base}/runs`, ({ request }) => {
    const url = new URL(request.url);
    const termId = url.searchParams.get("term_id");
    const list = state.runs.map(tickRun).filter((r) => !termId || r.term_id === Number(termId));
    return json([...list].sort((a, b) => b.id - a.id));
  }),
  http.post(`${base}/runs`, async ({ request }) => {
    const body = (await request.json()) as RunCreate;
    const term = terms.find((t) => t.id === body.term_id) ?? terms[0];
    const id = Math.max(...state.runs.map((r) => r.id)) + 1;
    const run: ScheduleRun = {
      id,
      term_id: term.id,
      term_code: term.code,
      kind: body.kind,
      horizon: body.horizon,
      horizon_params: { weeks: body.horizon_params?.weeks ?? [], dates: body.horizon_params?.dates ?? [] },
      status: "QUEUED",
      progress: 0,
      params: { time_limit_s: 60, seed: 0, workers: 8, stability: true, weights: {}, ...body.params },
      objective_value: null,
      soft_score: null,
      hard_score: null,
      stats: {},
      objective_breakdown: {},
      diagnosis: [],
      parent_run_id: body.parent_run_id ?? null,
      prompt_text: body.prompt ?? null,
      created_at: new Date().toISOString(),
      finished_at: null,
    };
    state.runs.push(run);
    state.runStartedAt.set(id, Date.now());
    return json({ run_id: id }, { status: 202 });
  }),
  http.get(`${base}/runs/:id`, ({ params }) => {
    const run = getRun(num(params.id));
    return run ? json(run) : notFound("Run");
  }),
  http.delete(`${base}/runs/:id`, ({ params }) => {
    const run = getRun(num(params.id));
    if (!run) return notFound("Run");
    if (run.status === "QUEUED" || run.status === "RUNNING") {
      run.status = "CANCELLED";
      run.finished_at = new Date().toISOString();
      state.runStartedAt.delete(run.id);
    }
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${base}/runs/:id/assignments`, ({ params, request }) => {
    const url = new URL(request.url);
    const week = url.searchParams.get("week");
    const day = url.searchParams.get("day");
    const room = url.searchParams.get("room");
    let list = state.assignments.get(num(params.id)) ?? [];
    if (week) list = list.filter((a) => weeksOf(a).includes(Number(week)));
    if (day) list = list.filter((a) => a.day === Number(day));
    if (room) list = list.filter((a) => a.room_ids.includes(Number(room)));
    return json(list);
  }),
  http.get(`${base}/runs/:id/grid`, ({ params, request }) => {
    const run = getRun(num(params.id));
    if (!run) return notFound("Run");
    const url = new URL(request.url);
    const termWeeks = weeks.filter((w) => w.term_id === run.term_id);
    const week = Number(url.searchParams.get("week") ?? run.horizon_params.weeks[0] ?? 1);
    const wk = termWeeks.find((w) => w.index === week) ?? termWeeks[0];
    const list = (state.assignments.get(run.id) ?? []).filter((a) => weeksOf(a).includes(week));
    return json({
      run_id: run.id,
      week,
      week_start: wk?.start_date ?? "2026-02-02",
      weeks: termWeeks,
      periods: PERIODS,
      rooms,
      assignments: list,
      blocks: blocks.filter((b) => b.weeks.includes(week)),
    });
  }),
  http.post(`${base}/runs/:id/assignments/:aid/move`, async ({ params, request }) => {
    const runId = num(params.id);
    const list = state.assignments.get(runId);
    const a = list?.find((x) => x.id === num(params.aid));
    if (!list || !a) return notFound("Assignment");
    const body = (await request.json()) as MoveRequest;
    // like the backend: conflicts → 200 {ok:false}; a successful move is MANUAL and locked
    const conflicts = validateMove(runId, a, body);
    if (conflicts.length > 0) return json({ ok: false, assignment: a, conflicts } satisfies MoveResponse);
    a.room_ids = body.room_ids;
    a.day = body.day;
    a.start_period = body.start_period;
    a.end_period = body.end_period;
    a.origin = "MANUAL";
    a.is_locked = true;
    a.conflict = false;
    a.conflict_reason = null;
    const run = state.runs.find((r) => r.id === runId);
    if (run && run.soft_score !== null) run.soft_score = Math.max(0, run.soft_score - 1);
    return json({ ok: true, assignment: a, conflicts: [], hard_score: run?.hard_score ?? 100, soft_score: run?.soft_score ?? null } satisfies MoveResponse);
  }),
  http.post(`${base}/runs/:id/assignments/:aid/lock`, async ({ params, request }) => {
    const a = state.assignments.get(num(params.id))?.find((x) => x.id === num(params.aid));
    if (!a) return notFound("Assignment");
    const q = new URL(request.url).searchParams.get("locked");
    const body = (await request.json().catch(() => ({}))) as { locked?: boolean };
    a.is_locked = q !== null ? q === "true" : body.locked === true;
    return json(a);
  }),
  http.post(`${base}/runs/:id/activate`, ({ params }) => {
    const run = getRun(num(params.id));
    if (!run) return notFound("Run");
    return json(run);
  }),
  http.get(`${base}/runs/:id/chat`, ({ params }) => json(chatFor(num(params.id)))),
  http.post(`${base}/runs/:id/chat`, async ({ params, request }) => {
    const runId = num(params.id);
    const body = (await request.json()) as { message: string };
    if (!state.settings.anthropic_api_key_masked) return json({ detail: "No Anthropic API key is configured. An admin can add one under Settings > AI (Ayarlar > Yapay zekâ)." }, { status: 409 });
    const list = chatFor(runId);
    const now = new Date().toISOString();
    list.push({ id: state.nextId++, run_id: runId, role: "user", content: body.message, tool_calls: [], created_at: now });
    const diff = proposeFromMessage(runId, body.message);
    const content = diff
      ? diff.operations.some((o) => o.op === "move")
        ? `I can do that: ${diff.summary}. The target slot is free and capacity fits. Apply?`
        : "Understood — I'll add this as a soft preference and re-solve with stability on. Apply?"
      : "I couldn't map that to a concrete change. Try a course code and a room, e.g. \"MAT 112'yi A 204'e taşı\".";
    const reply: MockChatMessage = { id: state.nextId++, run_id: runId, role: "assistant", content, tool_calls: diff ? [{ type: "diff", diff, applied: null }] : [], created_at: now };
    list.push(reply);
    return json({ message_id: reply.id, assistant_message: content, proposed_diff: diff, explanations: [], usage: { model: state.settings.anthropic_model, input_tokens: 0, output_tokens: 0 } });
  }),
  http.post(`${base}/runs/:id/chat/apply`, async ({ params, request }) => {
    const runId = num(params.id);
    const body = (await request.json()) as { diff_id?: string };
    const found = body.diff_id ? findDiff(runId, body.diff_id) : null;
    const parent = state.runs.find((r) => r.id === runId);
    if (!found || !parent) return json({ detail: `diff ${body.diff_id ?? "?"} not found for run ${runId}` }, { status: 400 });
    if (found.call.applied) return json({ detail: `diff ${found.diff.id} was already applied (child run #${String(found.call.applied)})` }, { status: 409 });
    // backend semantics: the result is always a child run — a patched copy, or a queued re-solve
    const reSolve = found.diff.re_solve || found.diff.operations.some((o) => o.op === "add_constraint");
    const child = childRun(parent, `chat: ${found.diff.summary}`, reSolve ? "QUEUED" : "FEASIBLE");
    const copy = (state.assignments.get(runId) ?? []).map((a, i) => ({ ...structuredClone(a), id: child.id * 10_000 + i + 1, run_id: child.id }));
    const applied: Record<string, unknown>[] = [];
    for (const op of found.diff.operations) {
      if (op.op !== "move") continue;
      const original = (state.assignments.get(runId) ?? []).findIndex((x) => x.id === op.assignment_id);
      const a = copy[original];
      if (!a) continue;
      a.room_ids = (op.room_ids as number[] | undefined) ?? a.room_ids;
      if (typeof op.day === "number") a.day = op.day;
      a.origin = "AI_EDIT";
      a.is_locked = true;
      applied.push({ op: "move", assignment_id: a.id });
    }
    state.assignments.set(child.id, copy);
    found.call.applied = child.id;
    chatFor(runId).push({ id: state.nextId++, run_id: runId, role: "system", content: reSolve ? `Applied. Re-solve queued as run #${child.id}.` : `Applied as run #${child.id}. Hard score still 100/100.`, tool_calls: [], created_at: new Date().toISOString() });
    return json({ child_run_id: child.id, applied, rejected: [], constraints_created: [], re_solve_queued: reSolve, mode: reSolve ? "full" : "patch", status: child.status, hard_score: child.hard_score, soft_score: child.soft_score });
  }),
  http.post(`${base}/runs/:id/diagnoses/:idx/apply`, async ({ params, request }) => {
    const parent = state.runs.find((r) => r.id === num(params.id));
    if (!parent) return notFound("Run");
    const body = (await request.json()) as { option_index?: number; re_solve?: boolean };
    const diag = parent.diagnosis[num(params.idx)];
    if (!diag) return json({ detail: `diagnosis ${String(params.idx)} not found (run has ${parent.diagnosis.length})` }, { status: 404 });
    const opt = diag.suggestions[body.option_index ?? 0];
    if (!opt?.applicable || opt.action === "manual") return json({ detail: `suggestion '${opt?.text ?? "?"}' has no structured fix; apply it by hand` }, { status: 422 });
    const child = body.re_solve === false ? null : childRun(parent, `fix: diagnosis ${String(params.idx)} option ${body.option_index ?? 0}: ${opt.text}`, "QUEUED");
    return json({ run_id: parent.id, child_run_id: child?.id ?? null, action: opt.action, message: opt.text, details: {}, constraint_id: null });
  }),
  http.get(`${base}/runs/:id/export`, ({ params, request }) => {
    const format = new URL(request.url).searchParams.get("format") ?? "csv";
    const rows = (state.assignments.get(num(params.id)) ?? []).map((a) => `${a.label},${a.day},${a.start_period},${a.end_period},${a.room_ids.join("+")}`);
    return new HttpResponse(["label,day,start,end,rooms", ...rows].join("\n"), { headers: { "Content-Type": "text/csv", "Content-Disposition": `attachment; filename="run-${String(params.id)}.${format}"` } });
  }),

  http.get(`${base}/settings`, () => json(state.settings)),
  http.put(`${base}/settings`, async ({ request }) => {
    const body = (await request.json()) as SettingsUpdate;
    const { anthropic_api_key, ...rest } = body;
    Object.assign(state.settings, rest);
    if (anthropic_api_key) state.settings.anthropic_api_key_masked = `sk-ant-…${anthropic_api_key.slice(-4)}`;
    return json(state.settings);
  }),
  http.post(`${base}/settings/test-ai`, async () => {
    await new Promise((r) => setTimeout(r, 400));
    if (!state.settings.anthropic_api_key_masked) return json({ ok: false, model: null, latency_ms: null, error: "No API key saved" });
    return json({ ok: true, model: state.settings.anthropic_model, latency_ms: 412, error: null });
  }),
  http.get(`${base}/users`, () => json(state.users)),
  http.post(`${base}/users`, async ({ request }) => {
    const body = (await request.json()) as { email: string; full_name: string; role: User["role"]; password?: string };
    const email = body.email.trim().toLocaleLowerCase("en-US");
    if (state.users.some((u) => u.email === email)) return json({ detail: `a user with e-mail ${email} already exists` }, { status: 409 });
    if (!body.password || body.password.length < 8) return json({ detail: [{ msg: "String should have at least 8 characters", loc: ["body", "password"] }] }, { status: 422 });
    const user: User = { id: state.nextId++, email, full_name: body.full_name, role: body.role, is_active: true, created_at: new Date().toISOString() };
    state.users.push(user);
    return json(user, { status: 201 });
  }),
  http.put(`${base}/users/:id`, async ({ params, request }) => {
    const u = state.users.find((x) => x.id === num(params.id));
    if (!u) return notFound("User");
    const body = (await request.json()) as Partial<User>;
    const admins = state.users.filter((x) => x.role === "ADMIN" && x.is_active && x.id !== u.id).length;
    if (u.role === "ADMIN" && ((body.role && body.role !== "ADMIN") || body.is_active === false) && admins === 0) return json({ detail: "cannot demote or deactivate the last active admin" }, { status: 409 });
    Object.assign(u, { ...body, id: u.id });
    return json(u);
  }),
  http.post(`${base}/users/:id/password`, ({ params }) => {
    const u = state.users.find((x) => x.id === num(params.id));
    return u ? json(u) : notFound("User");
  }),
  http.delete(`${base}/users/:id`, ({ params }) => {
    const i = state.users.findIndex((x) => x.id === num(params.id));
    if (i < 0) return notFound("User");
    state.users.splice(i, 1);
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${base}/health`, () => json({ status: "ok", mock: true })),
];
