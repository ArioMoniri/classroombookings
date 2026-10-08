"use client";
/**
 * Extra API calls for the Liquid Glass shell and its pages (glass-shell agent, 2026-10-08).
 * New file on purpose: `endpoints.ts` / `hooks.ts` / `schemas.ts` are owned elsewhere. Everything here is a
 * thin wrapper over routes that already exist in the FastAPI backend (see `/api/openapi.json`):
 *
 * - search for ⌘K: `GET /courses|/instructors|/programs?search=`, `GET /sections?term_id=&search=`
 * - `POST /settings/test-ai` with a transient `api_key` (test before save; never claims "connected" itself)
 * - `GET /runs/{id}/data-issues` (planner-facing groups with TR/EN titles) and `GET /runs/{id}/summary`
 * - `GET /dashboard?term_id=&week=` (the week the planner remembered, not only the calendar week)
 * - import upload over XMLHttpRequest so the UI can show real byte progress
 * - chat apply of a subset of a proposed diff (`POST /runs/{id}/chat/apply` with an edited `diff`)
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import * as adapt from "./adapters";
import { API_PREFIX, HttpError, request } from "./client";
import { responseSchemas } from "./endpoints";
import { ImportJob, type ImportKind, type Term } from "./schemas";

/* ------------------------------------------------------------------------------------------- search */

const Page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item).default([]), total: z.number().default(0) });

export const CourseHit = z.object({ id: z.number(), code: z.string(), display_code: z.string().nullable().optional(), name: z.string().nullable().optional() });
export const InstructorHit = z.object({ id: z.number(), full_name: z.string(), title: z.string().nullable().optional() });
export const ProgramHit = z.object({ id: z.number(), name: z.string(), is_evening: z.boolean().nullable().optional() });
export const SectionHit = z.object({
  id: z.number(),
  label: z.string().nullable().optional(),
  enrolment: z.number().nullable().optional(),
  course_code: z.string().nullable().optional(),
  course_name: z.string().nullable().optional(),
  program_name: z.string().nullable().optional(),
});
export type CourseHit = z.infer<typeof CourseHit>;
export type InstructorHit = z.infer<typeof InstructorHit>;
export type ProgramHit = z.infer<typeof ProgramHit>;
export type SectionHit = z.infer<typeof SectionHit>;

export interface ShellSearchResult {
  courses: CourseHit[];
  sections: SectionHit[];
  instructors: InstructorHit[];
  programs: ProgramHit[];
}

/** "PHAR240", "phar 240", "a204" → "PHAR 240", "A 204": the backend matches both, the UI shows the spaced form. */
export function normaliseQuery(q: string): string {
  return q.trim().replace(/\s+/g, " ");
}

export async function shellSearch(q: string, termId: number | undefined, signal?: AbortSignal): Promise<ShellSearchResult> {
  const search = normaliseQuery(q);
  const opts = { silent: true, signal } as const;
  const settle = async <T>(p: Promise<{ items: T[] }>): Promise<T[]> => {
    try {
      return (await p).items;
    } catch {
      return []; // one failing source (403 for viewers, 404 on an older backend) must not empty the palette
    }
  };
  const [courses, sections, instructors, programs] = await Promise.all([
    settle(request("/courses", { query: { search, limit: 6 }, schema: Page(CourseHit), ...opts })),
    termId ? settle(request("/sections", { query: { term_id: termId, search, limit: 6 }, schema: Page(SectionHit), ...opts })) : Promise.resolve([]),
    settle(request("/instructors", { query: { search, limit: 5 }, schema: Page(InstructorHit), ...opts })),
    settle(request("/programs", { query: { search, limit: 5 }, schema: Page(ProgramHit), ...opts })),
  ]);
  return { courses, sections, instructors, programs };
}

export function useShellSearch(q: string, termId: number | undefined) {
  const search = normaliseQuery(q);
  return useQuery({
    queryKey: ["shell-search", search, termId ?? null, "term"],
    queryFn: ({ signal }) => shellSearch(search, termId, signal),
    enabled: search.length >= 2 && !search.startsWith(">"),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

/* ------------------------------------------------------------------------------------- AI key test */

export const AiKeyTest = z.object({ ok: z.boolean(), model: z.string().nullable().optional(), detail: z.string().default(""), used_key: z.string().default("") });
export type AiKeyTest = z.infer<typeof AiKeyTest>;

/** Tests the typed key (not saved) or, without one, the stored key. The backend is the only source of "connected". */
export function testAiKey(body: { api_key?: string; model?: string }): Promise<AiKeyTest> {
  return request("/settings/test-ai", { method: "POST", body, schema: AiKeyTest, silent: true });
}

/** Turkish/English wording for the backend's English failure detail (planner usability M12). */
export function aiFailureKind(detail: string): "auth" | "network" | "quota" | "model" | "other" {
  const d = detail.toLowerCase();
  if (/auth|api key|401|invalid x-api-key|permission/.test(d)) return "auth";
  if (/connect|timeout|timed out|network|unreachable|dns|resolve/.test(d)) return "network";
  if (/rate|quota|credit|429|overloaded|billing/.test(d)) return "quota";
  if (/model|not_found|404/.test(d)) return "model";
  return "other";
}

/* --------------------------------------------------------------------------- run report sources */

const LocalText = z.object({ tr: z.string().default(""), en: z.string().default("") });

export const DataIssueClass = z
  .object({
    request_id: z.number().nullable().optional(),
    course_code: z.string().nullable().optional(),
    course_name: z.string().nullable().optional(),
    section: z.string().nullable().optional(),
    program: z.string().nullable().optional(),
    enrolment: z.number().nullable().optional(),
    day: z.number().nullable().optional(),
    time: z.string().nullable().optional(),
    planner_rooms: z.string().nullable().optional(),
    instructors: z.string().nullable().optional(),
    source_row: z.number().nullable().optional(),
  })
  .passthrough();

export const DataIssueItem = z
  .object({
    diagnosis_index: z.number().nullable().optional(),
    code: z.string().default(""),
    severity: z.string().default("warning"),
    message: z.string().default(""),
    message_tr: z.string().nullable().optional(),
    event_ids: z.array(z.number()).default([]),
    unplaced: z.boolean().default(false),
    params: z.record(z.string(), z.unknown()).default({}),
    classes: z.array(DataIssueClass).default([]),
  })
  .passthrough();

export const DataIssueGroup = z.object({
  code: z.string(),
  title: LocalText,
  hint: LocalText.optional(),
  count: z.number().default(0),
  requests: z.number().optional(),
  items: z.array(DataIssueItem).default([]),
});

export const DataIssues = z.object({
  run_id: z.number(),
  status: z.string().optional(),
  totals: z
    .object({
      issues: z.number().default(0),
      events_total: z.number().default(0),
      placed: z.number().default(0),
      unplaced: z.number().default(0),
      by_group: z.record(z.string(), z.number()).default({}),
    })
    .partial()
    .default({}),
  groups: z.array(DataIssueGroup).default([]),
});
export type DataIssues = z.infer<typeof DataIssues>;
export type DataIssueGroup = z.infer<typeof DataIssueGroup>;
export type DataIssueItem = z.infer<typeof DataIssueItem>;

export const RunSummary = z
  .object({
    run_id: z.number(),
    status: z.string(),
    partial: z.boolean().default(false),
    placed: z.number().nullable().optional(),
    events_total: z.number().nullable().optional(),
    headline: LocalText.nullable().optional(),
    assignments: z.number().nullable().optional(),
    diagnoses: z.number().nullable().optional(),
    hard_score: z.number().nullable().optional(),
    soft_score: z.number().nullable().optional(),
  })
  .passthrough();
export type RunSummary = z.infer<typeof RunSummary>;

export const dataIssuesXlsxUrl = (runId: number) => `${API_PREFIX}/runs/${runId}/data-issues?format=xlsx`;

export function useRunDataIssues(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["run-data-issues", runId],
    queryFn: () => request(`/runs/${runId}/data-issues`, { schema: DataIssues, silent: true }),
    enabled: enabled && runId !== null,
    staleTime: 60_000,
    retry: false,
  });
}

export function useRunSummary(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["run-summary", runId],
    queryFn: () => request(`/runs/${runId}/summary`, { schema: RunSummary, silent: true }),
    enabled: enabled && runId !== null,
    staleTime: 60_000,
    retry: false,
  });
}

/* ------------------------------------------------------------------------------ dashboard by week */

const DashboardParser = responseSchemas.dashboard;

/** `GET /dashboard?term_id=&week=`; same parser as `useDashboard`, plus the remembered week. */
export function useDashboardWeek(termId: number | undefined, week: number | undefined) {
  return useQuery({
    queryKey: ["dashboard", termId ?? null, week ?? null, "term", "week"],
    queryFn: () => request("/dashboard", { query: { term_id: termId, week }, schema: DashboardParser, silent: true }),
    enabled: termId !== undefined,
    placeholderData: keepPreviousData,
  });
}

/* ------------------------------------------------------------------------- import with progress */

const ImportOne = z.preprocess(adapt.importJob, ImportJob);

export interface UploadProgress {
  loaded: number;
  total: number;
}

/**
 * `POST /imports/{kind}` over XMLHttpRequest: `onProgress` reports real bytes sent (fetch has no upload
 * progress). Form fields match `api.imports.upload`. Resolves with the parsed import job.
 */
export function uploadImportWithProgress(
  kind: ImportKind,
  file: File | null,
  term: Pick<Term, "id" | "code" | "start_date">,
  opts: { dsn?: string; onProgress?: (p: UploadProgress) => void; signal?: AbortSignal } = {},
): Promise<ImportJob> {
  const fd = new FormData();
  if (file) fd.append(kind === "crbs" ? "files" : "file", file);
  if (kind !== "crbs") fd.append("term_code", term.code);
  if (kind === "weekly-grid") fd.append("year", String(Number(term.start_date.slice(0, 4)) || new Date().getFullYear()));
  if (kind === "planning-list") fd.append("week_count", "14");
  fd.append("term_id", String(term.id));
  if (opts.dsn) fd.append("dsn", opts.dsn);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_PREFIX}/imports/${kind}`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) opts.onProgress?.({ loaded: e.loaded, total: e.total });
    };
    xhr.onerror = () => reject(new HttpError(0, "Network error"));
    xhr.onabort = () => reject(new HttpError(0, "Aborted"));
    xhr.onload = () => {
      let json: unknown = null;
      try {
        json = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error page */
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = json && typeof json === "object" && "detail" in json ? (json as { detail: unknown }).detail : xhr.statusText;
        reject(new HttpError(xhr.status, typeof detail === "string" ? detail : `${xhr.status} ${xhr.statusText}`, detail));
        return;
      }
      const parsed = ImportOne.safeParse(json);
      if (parsed.success) resolve(parsed.data);
      else reject(new HttpError(500, "Invalid import response", parsed.error.issues));
    };
    opts.signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(fd);
  });
}

/* ------------------------------------------------------------------------- chat: apply a subset */

type RawToolCall = { type?: string; diff?: { id?: string; operations?: { op?: string; assignment_id?: number }[] } };
const RawHistory = z.array(z.object({ tool_calls: z.array(z.unknown()).default([]) }).passthrough());

/**
 * Applies only the moves the planner kept ticked in the DiffTable. When every move is kept the
 * stored diff is applied by id (the normal path); otherwise the stored diff is fetched, its excluded
 * move operations are dropped and the edited diff is posted (`ApplyIn.diff`).
 */
export async function applyProposalSubset(runId: number, diffId: string, keepAssignmentIds: number[], allAssignmentIds: number[]): Promise<{ child_run_id: number | null }> {
  const Out = z.object({ child_run_id: z.number().nullable() }).passthrough();
  const keep = new Set(keepAssignmentIds);
  if (allAssignmentIds.every((id) => keep.has(id))) {
    return request(`/runs/${runId}/chat/apply`, { method: "POST", body: { diff_id: diffId }, schema: Out });
  }
  const history = await request(`/runs/${runId}/chat`, { schema: RawHistory });
  const call = history
    .flatMap((m) => m.tool_calls as RawToolCall[])
    .find((tc) => tc && typeof tc === "object" && tc.type === "diff" && tc.diff?.id === diffId);
  if (!call?.diff) throw new HttpError(404, "Proposal not found");
  const operations = (call.diff.operations ?? []).filter((op) => op.op !== "move" || (op.assignment_id !== undefined && keep.has(op.assignment_id)));
  return request(`/runs/${runId}/chat/apply`, { method: "POST", body: { diff: { ...call.diff, operations } }, schema: Out });
}

/* ------------------------------------------------------------------- identity with permissions */

/**
 * `GET /auth/me` with the CRBS-parity fields. `useMe()` parses `User`, whose role enum predates TEACHER /
 * CUSTOM / NONE and which drops `permissions`; the shell gates navigation on permissions instead.
 */
export const MeFull = z
  .object({
    id: z.number(),
    email: z.string().nullable().optional(),
    username: z.string().nullable().optional(),
    full_name: z.string().nullable().optional(),
    role: z.string().default("NONE"),
    permissions: z.array(z.string()).default([]),
    force_password_reset: z.boolean().default(false),
  })
  .passthrough();
export type MeFull = z.infer<typeof MeFull>;

export function useMeFull() {
  return useQuery({ queryKey: ["me", "full"], queryFn: () => request("/auth/me", { schema: MeFull, silent: true }), staleTime: 60_000, retry: false });
}

/** `true` when the user holds any of `perm` (no permission list yet → planning pages stay visible while loading). */
export function hasPermission(perms: readonly string[] | undefined, perm: string | readonly string[] | undefined): boolean {
  if (!perm) return true;
  if (!perms) return false;
  const want = typeof perm === "string" ? [perm] : perm;
  return want.some((p) => perms.includes(p));
}

/** The permission list is exactly what `GET /auth/me` returns (no role-based fallback). */
export function effectivePermissions(me: Pick<MeFull, "permissions"> | undefined): string[] | undefined {
  return me?.permissions;
}

export function usePermissions(): { perms: string[] | undefined; can: (perm: string | readonly string[] | undefined) => boolean; me: MeFull | undefined } {
  const me = useMeFull();
  const perms = effectivePermissions(me.data);
  return { perms, me: me.data, can: (perm) => hasPermission(perms, perm) };
}

/** Login with an e-mail **or** a username (CRBS parity); the proxy stores the JWT and returns `/auth/me`. */
export async function loginWithIdentifier(identifier: string, password: string): Promise<{ user: MeFull | null; mustChangePassword: boolean }> {
  const id = identifier.trim();
  const body = id.includes("@") ? { email: id, password } : { username: id, password };
  const out = await request<{ user?: unknown; password_change_required?: boolean }>("/auth/login", { method: "POST", body, silent: true });
  const parsed = MeFull.safeParse(out?.user);
  const user = parsed.success ? parsed.data : null;
  return { user, mustChangePassword: Boolean(out?.password_change_required) || Boolean(user?.force_password_reset) };
}

export function changePassword(body: { current_password?: string | null; new_password: string }) {
  return request("/auth/change-password", { method: "POST", body, silent: true });
}
