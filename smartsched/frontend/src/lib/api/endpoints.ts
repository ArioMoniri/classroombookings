/**
 * Typed endpoint functions. One function per API route in docs/ARCHITECTURE.md.
 */
import { z } from "zod";
import { request, type Query } from "./client";
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

export const api = {
  auth: {
    /** Login goes through the Next route handler so the JWT lands in an httpOnly cookie. */
    login: (email: string, password: string) =>
      request("/auth/login", { method: "POST", body: { email, password }, schema: z.object({ user: User }), silent: true }),
    me: () => request("/auth/me", { schema: User, silent: true }),
    logout: () => fetch("/api/auth/logout", { method: "POST" }),
  },
  dashboard: {
    summary: (termId?: number) => request("/dashboard", { query: { term_id: termId }, schema: DashboardSummary }),
  },
  terms: {
    list: () => request("/terms", { schema: z.array(Term) }),
    weeks: (termId: number) => request(`/terms/${termId}/weeks`, { schema: z.array(Week) }),
  },
  rooms: {
    list: (query?: Query) => request("/rooms", { query, schema: z.array(Room) }),
    get: (id: number) => request(`/rooms/${id}`, { schema: Room }),
    update: (id: number, body: Partial<Room>) => request(`/rooms/${id}`, { method: "PUT", body, schema: Room }),
  },
  buildings: { list: () => request("/buildings", { schema: z.array(Building) }) },
  programs: { list: () => request("/programs", { schema: z.array(Program) }) },
  requests: {
    meetings: (query?: Query) => request("/requests/meetings", { query, schema: Paginated(MeetingRequest) }),
    updateMeeting: (id: number, body: MeetingRequestUpdate) =>
      request(`/requests/meetings/${id}`, { method: "PUT", body, schema: MeetingRequest }),
    exams: (query?: Query) => request("/requests/exams", { query, schema: Paginated(ExamRequest) }),
    updateExam: (id: number, body: ExamRequestUpdate) => request(`/requests/exams/${id}`, { method: "PUT", body, schema: ExamRequest }),
  },
  imports: {
    upload: (kind: ImportKind, file: File | null, termId: number, dsn?: string) => {
      const fd = new FormData();
      if (file) fd.append("file", file);
      fd.append("term_id", String(termId));
      if (dsn) fd.append("dsn", dsn);
      return request(`/imports/${kind}`, { method: "POST", formData: fd, schema: ImportJob });
    },
    get: (jobId: number) => request(`/imports/${jobId}`, { schema: ImportJob }),
    list: () => request("/imports", { schema: z.array(ImportJob) }),
  },
  constraints: {
    list: (query?: Query) => request("/constraints", { query, schema: z.array(Constraint) }),
    create: (body: Omit<Constraint, "id">) => request("/constraints", { method: "POST", body, schema: Constraint }),
    propose: (termId: number, prompt: string) =>
      request("/constraints/propose", { method: "POST", body: { term_id: termId, prompt }, schema: ProposedConstraints }),
  },
  runs: {
    list: (query?: Query) => request("/runs", { query, schema: z.array(ScheduleRun) }),
    get: (id: number) => request(`/runs/${id}`, { schema: ScheduleRun }),
    create: (body: RunCreate) => request("/runs", { method: "POST", body, schema: RunCreated }),
    assignments: (id: number, query?: Query) => request(`/runs/${id}/assignments`, { query, schema: z.array(Assignment) }),
    grid: (id: number, week?: number) => request(`/runs/${id}/grid`, { query: { week }, schema: GridResponse }),
    move: (runId: number, assignmentId: number, body: MoveRequest) =>
      request(`/runs/${runId}/assignments/${assignmentId}/move`, { method: "POST", body, schema: MoveResponse, silent: true }),
    lock: (runId: number, assignmentId: number, locked: boolean) =>
      request(`/runs/${runId}/assignments/${assignmentId}/lock`, { method: "POST", body: { locked }, schema: Assignment }),
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
    get: () => request("/settings", { schema: Settings }),
    update: (body: SettingsUpdate) => request("/settings", { method: "PUT", body, schema: Settings }),
    testAi: () => request("/settings/test-ai", { method: "POST", schema: TestAiResponse, silent: true }),
    users: () => request("/users", { schema: z.array(User) }),
    createUser: (body: { email: string; full_name: string; role: User["role"]; password: string }) =>
      request("/users", { method: "POST", body, schema: User }),
  },
};
