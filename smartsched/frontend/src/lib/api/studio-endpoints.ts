/**
 * Generator Studio endpoints (backend `app/api/v1/studio.py`, `app/api/v1/presets.py`).
 * One function per route; every response is validated with the schemas in ./studio-schemas.ts.
 */
import { z } from "zod";
import { API_PREFIX, HttpError, request } from "./client";
import type { ProposedConstraint } from "./schemas";
import {
  AcceptOut,
  BulkEditResult,
  ClassPage,
  ClassRow,
  CopyResult,
  Draft,
  DraftConflict,
  type DraftPatch,
  Extraction,
  FixResult,
  GenerateOut,
  MappingResult,
  type MappingSpec,
  type MeetingPatch,
  Precheck,
  Preset,
  PresetApply,
  Preview,
  type ProposedSectionEdit,
  RulesOut,
  type StudioKind,
  StudioMeta,
  StudioSummary,
} from "./studio-schemas";

export class DraftConflictError extends Error {
  readonly current: Draft;
  constructor(message: string, current: Draft) {
    super(message);
    this.name = "DraftConflictError";
    this.current = current;
  }
}

export interface UploadProgress {
  /** 0..100 of the bytes sent; the server-side reading has no percentage, so it is reported as a stage. */
  percent: number;
  stage: "uploading" | "reading";
}

/** multipart POST with real upload progress (fetch has no upload progress events). */
function postWithProgress<T>(path: string, form: FormData, schema: z.ZodType<T>, onProgress?: (p: UploadProgress) => void, signal?: AbortSignal): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_PREFIX}${path}`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const percent = Math.round((e.loaded / Math.max(1, e.total)) * 100);
      onProgress?.({ percent, stage: percent >= 100 ? "reading" : "uploading" });
    };
    xhr.upload.onload = () => onProgress?.({ percent: 100, stage: "reading" });
    xhr.onerror = () => reject(new HttpError(0, "Network error"));
    xhr.onabort = () => reject(new HttpError(0, "aborted"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText || "null");
      } catch {
        body = null;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = (body as { detail?: unknown } | null)?.detail;
        const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => (d as { msg?: string }).msg ?? "").join("; ") : `${xhr.status} ${xhr.statusText}`;
        reject(new HttpError(xhr.status, message, detail));
        return;
      }
      const parsed = schema.safeParse(body);
      if (!parsed.success) reject(new HttpError(500, `Invalid response for POST ${path}: ${parsed.error.issues[0]?.message ?? "schema mismatch"}`, parsed.error.issues));
      else resolve(parsed.data);
    };
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(form);
  });
}

export interface ClassQuery {
  faculty_id?: number;
  program_id?: number;
  class_year?: number;
  day?: number;
  building?: string;
  mode?: string;
  status?: string;
  changed?: boolean;
  included?: boolean;
  rule_id?: number;
  ids?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

const kindQ = (kind: StudioKind) => ({ kind });

export const studioApi = {
  meta: () => request("/studio/meta", { schema: StudioMeta }),
  draft: (termId: number, kind: StudioKind) => request(`/terms/${termId}/studio`, { query: kindQ(kind), schema: Draft }),
  /** Partial update with `version`; a stale version raises {@link DraftConflictError} with the server copy. */
  saveDraft: async (termId: number, kind: StudioKind, version: number, patch: DraftPatch): Promise<Draft> => {
    try {
      return await request(`/terms/${termId}/studio`, { method: "PUT", body: { ...patch, kind, version }, schema: Draft, silent: true });
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) {
        const parsed = DraftConflict.safeParse(e.detail);
        if (parsed.success) throw new DraftConflictError(parsed.data.detail.message, parsed.data.detail.current);
      }
      throw e;
    }
  },
  summary: (termId: number, kind: StudioKind) => request(`/terms/${termId}/studio/summary`, { query: kindQ(kind), schema: StudioSummary }),
  classes: (termId: number, kind: StudioKind, q: ClassQuery = {}) =>
    request(`/terms/${termId}/studio/classes`, { query: { kind, limit: 2000, ...q }, schema: ClassPage }),
  bulkEdit: (body: { ids?: number[]; patch?: MeetingPatch; items?: { id: number; patch: MeetingPatch }[]; dry_run?: boolean }) =>
    request("/studio/meetings/bulk", { method: "PUT", body, schema: BulkEditResult, silent: true }),
  revert: (id: number, fields?: string[]) => request(`/studio/meetings/${id}/revert`, { method: "POST", body: { fields: fields ?? null }, schema: ClassRow }),
  revertMany: (ids: number[], fields?: string[]) =>
    request("/studio/meetings/revert", { method: "POST", body: { ids, fields: fields ?? null }, schema: z.array(ClassRow) }),
  precheck: (termId: number, kind: StudioKind) => request(`/terms/${termId}/studio/precheck`, { method: "POST", query: kindQ(kind), body: {}, schema: Precheck, silent: true }),
  applyFix: (termId: number, kind: StudioKind, itemId: string, option: string) =>
    request(`/terms/${termId}/studio/precheck/fix`, { method: "POST", query: kindQ(kind), body: { item_id: itemId, option }, schema: FixResult }),
  rules: (termId: number, kind: StudioKind) => request(`/terms/${termId}/studio/rules`, { query: kindQ(kind), schema: RulesOut }),
  preview: (body: { term_id: number; kind: string; params: Record<string, unknown>; hardness: "hard" | "soft"; draft_kind: StudioKind; sample?: number }, signal?: AbortSignal) =>
    request("/studio/constraints/preview", { method: "POST", body, schema: Preview, silent: true, signal }),
  copy: (body: { to_term_id: number; from_run_id?: number | null; from_term_id?: number | null; constraint_ids?: number[] | null; dry_run: boolean }) =>
    request("/studio/constraints/copy", { method: "POST", body, schema: CopyResult }),
  /** Review-tray accept: provenance lands in `constraints.source_ref`. */
  accept: (termId: number, proposals: ProposedConstraint[], sectionEdits: ProposedSectionEdit[] = []) =>
    request(`/terms/${termId}/studio/proposals/accept`, { method: "POST", body: { proposals, section_edits: sectionEdits }, schema: AcceptOut }),
  /** AI preference-file reader (`POST /terms/{id}/preferences/upload`); 409 = no AI key → column mapping. */
  uploadPreferences: (termId: number, file: File, lang: "tr" | "en", onProgress?: (p: UploadProgress) => void, signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("lang", lang);
    return postWithProgress(`/terms/${termId}/preferences/upload`, fd, Extraction, onProgress, signal);
  },
  /** Pasted e-mail text goes through the NL reader. */
  elicit: (termId: number, text: string, lang: "tr" | "en") =>
    request(`/terms/${termId}/elicit`, { method: "POST", body: { text, lang }, schema: Extraction, silent: true }),
  /** No-AI Excel/CSV fallback: without `mapping` → detected columns; with it → proposals. */
  mapping: (termId: number, file: File, lang: "tr" | "en", mapping?: MappingSpec, onProgress?: (p: UploadProgress) => void) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("lang", lang);
    if (mapping) fd.append("mapping", JSON.stringify(mapping));
    return postWithProgress(`/terms/${termId}/studio/preferences/mapping`, fd, MappingResult, onProgress);
  },
  generate: (termId: number, kind: StudioKind, body: { label?: string | null; params?: Record<string, unknown>; parent_run_id?: number | null; stability?: boolean | null }) =>
    request(`/terms/${termId}/studio/generate`, { method: "POST", query: kindQ(kind), body, schema: GenerateOut }),
};

export const presetsApi = {
  list: (kind?: StudioKind) => request("/presets", { query: { kind }, schema: z.array(Preset) }),
  create: (body: { name: string; description?: string | null; kind: StudioKind; from_term_id?: number | null }) =>
    request("/presets", { method: "POST", body, schema: Preset }),
  update: (id: number, body: { name?: string; description?: string | null }) => request(`/presets/${id}`, { method: "PUT", body, schema: Preset }),
  remove: (id: number) => request(`/presets/${id}`, { method: "DELETE" }),
  apply: (id: number, termId: number, dryRun: boolean) => request(`/presets/${id}/apply`, { method: "POST", body: { term_id: termId, dry_run: dryRun }, schema: PresetApply }),
};
