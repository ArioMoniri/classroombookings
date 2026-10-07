"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import type { Query } from "./client";
import { api } from "./endpoints";
import type { ExamRequestUpdate, MeetingRequestUpdate, MoveRequest, RunCreate, ScheduleRun, SettingsUpdate } from "./schemas";

export const qk = {
  me: ["me"] as const,
  dashboard: (termId?: number) => ["dashboard", termId ?? null, "term"] as const,
  terms: ["terms"] as const,
  weeks: (termId: number) => ["weeks", termId, "term"] as const,
  rooms: (q?: Query) => ["rooms", q ?? {}] as const,
  room: (id: number) => ["room", id] as const,
  buildings: ["buildings"] as const,
  programs: ["programs"] as const,
  meetings: (q?: Query) => ["requests", "meetings", q ?? {}, "term"] as const,
  exams: (q?: Query) => ["requests", "exams", q ?? {}, "term"] as const,
  imports: ["imports"] as const,
  importJob: (id: number) => ["import", id] as const,
  runs: (q?: Query) => ["runs", q ?? {}, "term"] as const,
  run: (id: number) => ["run", id] as const,
  grid: (id: number, week?: number) => ["grid", id, week ?? null] as const,
  chat: (id: number) => ["chat", id] as const,
  settings: ["settings"] as const,
  users: ["users"] as const,
  constraints: (q?: Query) => ["constraints", q ?? {}] as const,
};

const RUN_ACTIVE: ReadonlySet<ScheduleRun["status"]> = new Set(["QUEUED", "RUNNING"]);

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: api.auth.me, retry: false, staleTime: 5 * 60_000 });
}
export function useDashboard(termId?: number) {
  return useQuery({ queryKey: qk.dashboard(termId), queryFn: () => api.dashboard.summary(termId) });
}
export function useTerms() {
  return useQuery({ queryKey: qk.terms, queryFn: api.terms.list, staleTime: 10 * 60_000 });
}
export function useWeeks(termId: number | undefined) {
  return useQuery({ queryKey: qk.weeks(termId ?? 0), queryFn: () => api.terms.weeks(termId ?? 0), enabled: termId !== undefined });
}
export function useRooms(q?: Query) {
  return useQuery({ queryKey: qk.rooms(q), queryFn: () => api.rooms.list(q), staleTime: 60_000 });
}
export function useRoom(id: number) {
  return useQuery({ queryKey: qk.room(id), queryFn: () => api.rooms.get(id) });
}
export function useBuildings() {
  return useQuery({ queryKey: qk.buildings, queryFn: api.buildings.list, staleTime: 10 * 60_000 });
}
export function usePrograms() {
  return useQuery({ queryKey: qk.programs, queryFn: api.programs.list, staleTime: 10 * 60_000 });
}
export function useMeetings(q?: Query) {
  return useQuery({ queryKey: qk.meetings(q), queryFn: () => api.requests.meetings(q), placeholderData: (prev) => prev });
}
export function useExams(q?: Query) {
  return useQuery({ queryKey: qk.exams(q), queryFn: () => api.requests.exams(q), placeholderData: (prev) => prev });
}
export function useUpdateMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: MeetingRequestUpdate }) => api.requests.updateMeeting(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });
}
export function useUpdateExam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ExamRequestUpdate }) => api.requests.updateExam(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });
}
export function useImports() {
  return useQuery({ queryKey: qk.imports, queryFn: api.imports.list });
}
export function useImportJob(id: number | null) {
  return useQuery({
    queryKey: qk.importJob(id ?? 0),
    queryFn: () => api.imports.get(id ?? 0),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data && (query.state.data.status === "QUEUED" || query.state.data.status === "RUNNING") ? 800 : false),
  });
}
export function useRuns(q?: Query) {
  return useQuery({
    queryKey: qk.runs(q),
    queryFn: () => api.runs.list(q),
    refetchInterval: (query) => (query.state.data?.some((r) => RUN_ACTIVE.has(r.status)) ? 1500 : false),
  });
}
export function useRun(id: number | null, opts?: Partial<UseQueryOptions<ScheduleRun>>) {
  return useQuery({
    queryKey: qk.run(id ?? 0),
    queryFn: () => api.runs.get(id ?? 0),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data && RUN_ACTIVE.has(query.state.data.status) ? 1000 : false),
    ...opts,
  });
}
export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RunCreate) => api.runs.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
}
export function useGrid(runId: number | null, week?: number) {
  return useQuery({ queryKey: qk.grid(runId ?? 0, week), queryFn: () => api.runs.grid(runId ?? 0, week), enabled: runId !== null, staleTime: 30_000 });
}
export function useMoveAssignment(runId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assignmentId, body }: { assignmentId: number; body: MoveRequest }) => api.runs.move(runId, assignmentId, body),
    onSuccess: (res) => {
      if (res.ok) {
        void qc.invalidateQueries({ queryKey: ["grid", runId] });
        void qc.invalidateQueries({ queryKey: qk.run(runId) });
      }
    },
  });
}
export function useLockAssignment(runId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assignmentId, locked }: { assignmentId: number; locked: boolean }) => api.runs.lock(runId, assignmentId, locked),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["grid", runId] }),
  });
}
export function useChat(runId: number) {
  return useQuery({ queryKey: qk.chat(runId), queryFn: () => api.runs.chat(runId) });
}
export function useSendChat(runId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (message: string) => api.runs.sendChat(runId, message),
    onSuccess: (data) => qc.setQueryData(qk.chat(runId), data),
  });
}
export function useApplyProposal(runId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (proposalId: string) => api.runs.applyProposal(runId, proposalId),
    onSuccess: (data) => {
      qc.setQueryData(qk.chat(runId), { messages: data.messages });
      void qc.invalidateQueries({ queryKey: ["grid", runId] });
      void qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}
export function useUndoProposal(runId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (proposalId: string) => api.runs.undoProposal(runId, proposalId),
    onSuccess: (data) => {
      qc.setQueryData(qk.chat(runId), { messages: data.messages });
      void qc.invalidateQueries({ queryKey: ["grid", runId] });
    },
  });
}
export function useApplyFix(runId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ diagnosisId, suggestionId }: { diagnosisId: string; suggestionId: string }) => api.runs.applyFix(runId, diagnosisId, suggestionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
}
export function useSettings() {
  return useQuery({ queryKey: qk.settings, queryFn: api.settings.get });
}
export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (body: SettingsUpdate) => api.settings.update(body), onSuccess: (data) => qc.setQueryData(qk.settings, data) });
}
export function useUsers() {
  return useQuery({ queryKey: qk.users, queryFn: api.settings.users });
}
export function useConstraints(q?: Query) {
  return useQuery({ queryKey: qk.constraints(q), queryFn: () => api.constraints.list(q) });
}
