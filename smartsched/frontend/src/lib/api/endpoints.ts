/**
 * Typed endpoint functions. One function per API route in docs/ARCHITECTURE.md.
 * Responses go through ./adapters.ts so both the FastAPI backend and the MSW mocks validate.
 */
import { z } from "zod";
import * as adapt from "./adapters";
import { HttpError, request, type Query } from "./client";
import {
  Assignment,
  Building,
  ChatResponse,
  Constraint,
  DashboardSummary,
  ExamRequest,
  ExamRequestUpdate,
  GridResponse,
  ImportJob,
  ImportKind,
  MeetingRequest,
  MeetingRequestUpdate,
  MoveRequest,
  MoveResponse,
  Paginated,
  Program,
  ProposedConstraints,
  Room,
  RunCreate,
  RunCreated,
  ScheduleRun,
  Settings,
  SettingsUpdate,
  Term,
  TestAiResponse,
  User,
  Week,
} from "./schemas";

const RoomsList = z.preprocess((v) => adapt.listOf(v).map(adapt.room), z.array(Room));
const RoomOne = z.preprocess(adapt.room, Room);
const ProgramsList = z.preprocess((v) => adapt.listOf(v).map(adapt.program), z.array(Program));
const TermsList = z.preprocess((v) => adapt.listOf(v).map(adapt.term), z.array(Term));
const WeeksList = z.preprocess((v) => adapt.listOf(v).map(adapt.week), z.array(Week));
const MeetingsPage = z.preprocess((v) => { const p = adapt.page(v) as { items?: unknown[] }; return { ...p, items: (p.items ?? []).map(adapt.meeting) }; }, Paginated(MeetingRequest));
const MeetingOne = z.preprocess(adapt.meeting, MeetingRequest);
const ExamsPage = z.preprocess((v) => { const p = adapt.page(v) as { items?: unknown[] }; return { ...p, items: (p.items ?? []).map(adapt.exam) }; }, Paginated(ExamRequest));
const ExamOne = z.preprocess(adapt.exam, ExamRequest);
const ImportOne = z.preprocess(adapt.importJob, ImportJob);
const ImportsList = z.preprocess((v) => adapt.listOf(v).map(adapt.importJob), z.array(ImportJob));
const RunsList = z.preprocess((v) => adapt.listOf(v).map(adapt.run), z.array(ScheduleRun));
const RunOne = z.preprocess(adapt.run, ScheduleRun);
const AssignmentsList = z.preprocess((v) => adapt.listOf(v).map(adapt.assignment), z.array(Assignment));
const AssignmentOne = z.preprocess(adapt.assignment, Assignment);
const Grid = z.preprocess(adapt.grid, GridResponse);
const Move = z.preprocess(adapt.moveResponse, MoveResponse);
const SettingsOut = z.preprocess(adapt.settings, Settings);
const TestAi = z.preprocess(adapt.testAi, TestAiResponse);
const ConstraintsList = z.preprocess(adapt.listOf, z.array(Constraint));
const BuildingsList = z.preprocess(adapt.listOf, z.array(Building));
const UsersList = z.preprocess(adapt.listOf, z.array(User));

const lq = adapt.listQuery;

export const api = {
  auth: {
    /** Login goes through the Next route handler so the JWT lands in an httpOnly cookie. */
    login: (email: string, password: string) =>
      request("/auth/login", { method: "POST", body: { email, password }, schema: z.object({ user: User }), silent: true }),
    me: () => request("/auth/me", { schema: User, silent: true }),
    logout: () => fetch("/api/auth/logout", { method: "POST" }),
  },
  dashboard: {
    /** `GET /dashboard` when the backend has it; otherwise composed client-side from the reference routes. */
    summary: async (termId?: number): Promise<DashboardSummary> => {
      try {
        return await request("/dashboard", { query: { term_id: termId }, schema: DashboardSummary, silent: true });
      } catch (e) {
        if (!(e instanceof HttpError) || (e.status !== 404 && e.status !== 501 && e.status !== 405)) throw e;
        return composeDashboard(termId);
      }
    },
  },
  terms: {
    list: () => request("/terms", { schema: TermsList }),
    weeks: (termId: number) => request(`/terms/${termId}/weeks`, { schema: WeeksList }),
  },
  rooms: {
    list: (query?: Query) => request("/rooms", { query: lq(query), schema: RoomsList }),
    get: (id: number) => request(`/rooms/${id}`, { schema: RoomOne }),
    update: (id: number, body: Partial<Room>) => request(`/rooms/${id}`, { method: "PUT", body, schema: RoomOne }),
  },
  buildings: { list: () => request("/buildings", { schema: BuildingsList }) },
  programs: { list: () => request("/programs", { query: { limit: 500 }, schema: ProgramsList }) },
  requests: {
    meetings: (query?: Query) => request("/requests/meetings", { query: lq(query), schema: MeetingsPage }),
    updateMeeting: (id: number, body: MeetingRequestUpdate) =>
      request(`/requests/meetings/${id}`, { method: "PUT", body, schema: MeetingOne }),
    exams: (query?: Query) => request("/requests/exams", { query: lq(query), schema: ExamsPage }),
    updateExam: (id: number, body: ExamRequestUpdate) => request(`/requests/exams/${id}`, { method: "PUT", body, schema: ExamOne }),
  },
  imports: {
    upload: (kind: ImportKind, file: File | null, termId: number, dsn?: string) => {
      const fd = new FormData();
      if (file) fd.append("file", file);
      fd.append("term_id", String(termId));
      if (dsn) fd.append("dsn", dsn);
      return request(`/imports/${kind}`, { method: "POST", formData: fd, query: { term_id: termId }, schema: ImportOne });
    },
    get: (jobId: number) => request(`/imports/${jobId}`, { schema: ImportOne }),
    list: () => request("/imports", { schema: ImportsList }),
  },
  constraints: {
    list: (query?: Query) => request("/constraints", { query, schema: ConstraintsList }),
    create: (body: Omit<Constraint, "id">) => request("/constraints", { method: "POST", body, schema: Constraint }),
    /** Mock-only today: the backend's `propose_constraints` tool lives in app/ai (see hand-off). */
    propose: (termId: number, prompt: string) =>
      request("/constraints/propose", { method: "POST", body: { term_id: termId, prompt }, schema: ProposedConstraints }),
  },
  runs: {
    list: (query?: Query) => request("/runs", { query, schema: RunsList }),
    get: (id: number) => request(`/runs/${id}`, { schema: RunOne }),
    create: (body: RunCreate) => request("/runs", { method: "POST", body, schema: RunCreated }),
    assignments: (id: number, query?: Query) => request(`/runs/${id}/assignments`, { query, schema: AssignmentsList }),
    grid: (id: number, week?: number) => request(`/runs/${id}/grid`, { query: { week }, schema: Grid }),
    move: (runId: number, assignmentId: number, body: MoveRequest) =>
      request(`/runs/${runId}/assignments/${assignmentId}/move`, { method: "POST", body, schema: Move, silent: true }),
    /** Backend reads `?locked=`; the body is kept for the mock. */
    lock: (runId: number, assignmentId: number, locked: boolean) =>
      request(`/runs/${runId}/assignments/${assignmentId}/lock`, { method: "POST", query: { locked }, body: { locked }, schema: AssignmentOne }),
    chat: (runId: number) => request(`/runs/${runId}/chat`, { schema: ChatResponse }),
    sendChat: (runId: number, message: string) => request(`/runs/${runId}/chat`, { method: "POST", body: { message }, schema: ChatResponse }),
    applyProposal: (runId: number, proposalId: string) =>
      request(`/runs/${runId}/chat/${proposalId}/apply`, { method: "POST", schema: z.object({ child_run_id: z.number().nullable(), messages: ChatResponse.shape.messages }) }),
    undoProposal: (runId: number, proposalId: string) =>
      request(`/runs/${runId}/chat/${proposalId}/undo`, { method: "POST", schema: z.object({ ok: z.boolean(), messages: ChatResponse.shape.messages }) }),
    applyFix: (runId: number, diagnosisId: string, suggestionId: string) =>
      request(`/runs/${runId}/diagnosis/${diagnosisId}/apply`, { method: "POST", body: { suggestion_id: suggestionId }, schema: RunCreated }),
    exportUrl: (runId: number, format: "xlsx" | "ics" | "csv" | "crbs") => `/api/v1/runs/${runId}/export?format=${format}`,
  },
  settings: {
    get: () => request("/settings", { schema: SettingsOut }),
    update: (body: SettingsUpdate) => request("/settings", { method: "PUT", body: adapt.settingsUpdateBody(body), schema: SettingsOut }),
    testAi: () => request("/settings/test-ai", { method: "POST", body: {}, schema: TestAi, silent: true }),
    users: () => request("/users", { schema: UsersList }),
    createUser: (body: { email: string; full_name: string; role: User["role"]; password: string }) =>
      request("/users", { method: "POST", body, schema: User }),
  },
};

async function composeDashboard(termId?: number): Promise<DashboardSummary> {
  const [terms, rooms, runs, needsReview, all] = await Promise.all([
    api.terms.list(),
    api.rooms.list(),
    api.runs.list(termId ? { term_id: termId } : undefined),
    api.requests.meetings({ status: "NEEDS_REVIEW", page_size: 1, term_id: termId }),
    api.requests.meetings({ page_size: 1, term_id: termId }),
  ]);
  const term = terms.find((t) => t.id === termId) ?? terms.find((t) => t.is_active) ?? terms[0];
  if (!term) throw new HttpError(404, "No terms");
  const bookable = rooms.filter((r) => r.is_bookable);
  const byBuilding = [...new Set(rooms.map((r) => r.building_code))].sort().map((b) => {
    const rs = bookable.filter((r) => r.building_code === b);
    return { building: b, utilisation: rs.reduce((s, r) => s + (r.utilisation ?? 0), 0) / Math.max(1, rs.length), rooms: rs.length };
  });
  const sorted = [...runs].sort((a, b) => b.id - a.id);
  return {
    term,
    current_week: 1,
    rooms_total: rooms.length,
    rooms_bookable: bookable.length,
    sections_total: all.total,
    requests_total: all.total,
    requests_needs_review: needsReview.total,
    utilisation: byBuilding.reduce((s, b) => s + b.utilisation * b.rooms, 0) / Math.max(1, bookable.length),
    utilisation_by_building: byBuilding,
    peak_hours: [],
    conflicts: 0,
    last_runs: sorted.slice(0, 5),
  };
}
