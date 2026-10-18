"use client";
/**
 * From-scratch programme creation (backend app/api/v1/catalog_admin.py + app/services/{catalog_admin,patterns}.py,
 * the read lists of app/api/v1/reference.py). The program wizard (docs/design/v2/phase19-program-wizard.md) saves
 * through these endpoints as the coordinator types: every row it creates is a hand-made `MAN:` row of the target
 * term, audited, archivable, and kept by later planning-list imports. Nothing is solved or published until the
 * last step starts a run.
 */
import { z } from "zod";
import { request } from "./client";
import { Pair } from "./moderation";
import { Precheck } from "./studio-schemas";

const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), total: z.number(), limit: z.number(), offset: z.number() });

export const Faculty = z.object({ id: z.number(), name: z.string(), canonical_name: z.string() });
export type Faculty = z.infer<typeof Faculty>;
export const ProgramRow = z.object({ id: z.number(), faculty_id: z.number().nullable(), name: z.string(), canonical_name: z.string(), is_evening: z.boolean() });
export type ProgramRow = z.infer<typeof ProgramRow>;
export const Course = z.object({
  id: z.number(),
  code: z.string(),
  display_code: z.string(),
  name: z.string().nullable(),
  t_hours: z.number().nullable(),
  u_hours: z.number().nullable(),
  l_hours: z.number().nullable(),
  credits: z.number().nullable(),
  ects: z.number().nullable(),
});
export type Course = z.infer<typeof Course>;
export const Instructor = z.object({ id: z.number(), full_name: z.string(), canonical_name: z.string(), title: z.string().nullable(), email: z.string().nullable() });
export type Instructor = z.infer<typeof Instructor>;
export const SectionRow = z.object({
  id: z.number(),
  term_id: z.number(),
  course_id: z.number(),
  program_id: z.number().nullable(),
  label: z.string().nullable(),
  class_year: z.number().nullable(),
  class_years: z.array(z.unknown()).default([]),
  enrolment: z.number().nullable(),
  mode: z.string(),
  notes: z.string().nullable(),
  archived: z.boolean(),
  course_code: z.string().nullable().optional(),
  course_name: z.string().nullable().optional(),
  program_name: z.string().nullable().optional(),
});
export type SectionRow = z.infer<typeof SectionRow>;
export const SectionAdmin = SectionRow.extend({
  source_key: z.string(),
  instructors: z.array(z.object({ instructor_id: z.number(), full_name: z.string(), title: z.string().nullable(), role: z.string() })).default([]),
  meeting_count: z.number().default(0),
});
export type SectionAdmin = z.infer<typeof SectionAdmin>;
export const CodeCheck = z.object({ input: z.string(), code: z.string().nullable(), display_code: z.string().nullable(), key: z.string().nullable(), duplicate: Course.nullable().optional(), message: z.string().nullable().optional() });
export type CodeCheck = z.infer<typeof CodeCheck>;
export const Meeting = z.object({ id: z.number(), section_id: z.number(), day: z.number().nullable().optional(), start_period: z.number().nullable().optional(), end_period: z.number().nullable().optional() }).passthrough();
export const PatternOut = z.object({ section_id: z.number(), created: z.array(Meeting), archived_ids: z.array(z.number()), warnings: z.array(z.string()).default([]), audit_id: z.number().nullable().optional() });
export type PatternOut = z.infer<typeof PatternOut>;

export interface CourseBody { code: string; name?: string | null; t_hours?: number | null; u_hours?: number | null; l_hours?: number | null; credits?: number | null; ects?: number | null }
export interface SectionBody {
  term_id: number;
  course_id: number;
  program_id?: number | null;
  label?: string | null;
  class_years?: number[] | null;
  enrolment?: number | null;
  mode?: string;
  instructors?: { instructor_id: number; role: "PRIMARY" | "SECONDARY" }[];
}
export interface PatternBody {
  theory?: number;
  practice?: number;
  lab?: number;
  block_size?: number | number[];
  days?: string | number | (string | number)[];
  start?: string | number | (string | number)[];
  weeks?: string | number[];
  room_needs?: { tags?: string[]; building?: string; preferred_room?: string; capacity?: number };
  replace?: boolean;
}

export const catalogApi = {
  faculties: (search?: string) => request(`/faculties`, { query: { search, limit: 500 }, schema: page(Faculty), silent: true }),
  createFaculty: (name: string) => request(`/faculties`, { method: "POST", body: { name }, schema: Faculty, silent: true }),
  programs: (q: { search?: string; faculty_id?: number } = {}) => request(`/programs`, { query: { ...q, limit: 500 }, schema: page(ProgramRow), silent: true }),
  createProgram: (body: { name: string; faculty_id?: number | null; is_evening?: boolean | null }) => request(`/programs`, { method: "POST", body, schema: ProgramRow, silent: true }),
  updateProgram: (id: number, body: { name?: string; faculty_id?: number | null; is_evening?: boolean | null }) => request(`/programs/${id}`, { method: "PUT", body, schema: ProgramRow, silent: true }),
  courses: (search?: string) => request(`/courses`, { query: { search, limit: 100 }, schema: page(Course), silent: true }),
  codeCheck: (code: string) => request(`/courses/code-check`, { query: { code }, schema: CodeCheck, silent: true }),
  createCourse: (body: CourseBody) => request(`/courses`, { method: "POST", body, schema: Course, silent: true }),
  updateCourse: (id: number, body: Partial<CourseBody>) => request(`/courses/${id}`, { method: "PUT", body, schema: Course, silent: true }),
  instructors: (search?: string) => request(`/instructors`, { query: { search, limit: 50 }, schema: page(Instructor), silent: true }),
  createInstructor: (body: { full_name: string; title?: string | null; email?: string | null }) => request(`/instructors`, { method: "POST", body, schema: Instructor, silent: true }),
  sections: (q: { term_id: number; program_id?: number; search?: string }) => request(`/sections`, { query: { ...q, limit: 1000 }, schema: page(SectionRow), silent: true }),
  section: (id: number) => request(`/sections/${id}`, { schema: SectionAdmin, silent: true }),
  createSection: (body: SectionBody) => request(`/sections`, { method: "POST", body, schema: SectionAdmin, silent: true }),
  updateSection: (id: number, body: Partial<Omit<SectionBody, "term_id" | "course_id">>) => request(`/sections/${id}`, { method: "PUT", body, schema: SectionAdmin, silent: true }),
  deleteSection: (id: number) => request(`/sections/${id}`, { method: "DELETE", silent: true }),
  pattern: (sectionId: number, body: PatternBody) => request(`/sections/${sectionId}/pattern`, { method: "POST", body, schema: PatternOut, silent: true }),
  meetings: (q: { term_id: number; program_id: number }) => request(`/requests/meetings`, { query: { ...q, limit: 2000 }, schema: page(Meeting), silent: true }),
  /** the Studio pre-check of the term draft (the wizard keeps the items of its own meetings) */
  precheck: (termId: number) => request(`/terms/${termId}/studio/precheck`, { method: "POST", query: { kind: "COURSE" }, body: {}, schema: Precheck, silent: true }),
  createRule: (body: { term_id: number; kind: string; params: Record<string, unknown>; hardness: "soft" | "hard"; weight: number; nl_text?: string }) =>
    request(`/constraints`, { method: "POST", body: { ...body, source: "ADMIN" }, schema: z.object({ id: z.number() }).passthrough(), silent: true }),
  deleteRule: (id: number) => request(`/constraints/${id}`, { method: "DELETE", silent: true }),
};

/** RF-05: what a delete would touch and "Son değişiklik" (`GET /catalog/usage/{entity}/{id}`, planning.view). */
export const CatalogUsage = z.object({
  entity: z.string(),
  id: z.number(),
  uses: z.record(z.string(), z.number()).default({}),
  blocked: z.boolean(),
  action: z.enum(["delete", "archive"]),
  last_change: z.object({ actor: z.string().nullish(), at: z.string().nullish(), action: z.string() }).nullish(),
});
export type CatalogUsage = z.infer<typeof CatalogUsage>;
export type CatalogEntity = "instructor" | "course" | "faculty" | "program" | "section";
const Deleted = z.object({ id: z.number(), action: z.string(), audit_id: z.number().nullish() });
const pageQuery = (q: { search?: string; limit?: number; offset?: number }) => ({ search: q.search || undefined, limit: q.limit ?? 100, offset: q.offset ?? 0 });

/** RF-05: the /admin/catalog screens (view, edit, delete what the workbooks imported); every write is audited. */
export const catalogAdminApi = {
  usage: (entity: CatalogEntity, id: number) => request(`/catalog/usage/${entity}/${id}`, { schema: CatalogUsage, silent: true }),
  instructorsPage: (q: { search?: string; limit?: number; offset?: number }) => request(`/instructors`, { query: pageQuery(q), schema: page(Instructor), silent: true }),
  updateInstructor: (id: number, body: { full_name?: string; title?: string | null; email?: string | null }) => request(`/instructors/${id}`, { method: "PUT", body, schema: Instructor, silent: true }),
  deleteInstructor: (id: number) => request(`/instructors/${id}`, { method: "DELETE", schema: Deleted, silent: true }),
  coursesPage: (q: { search?: string; limit?: number; offset?: number }) => request(`/courses`, { query: pageQuery(q), schema: page(Course), silent: true }),
  deleteCourse: (id: number) => request(`/courses/${id}`, { method: "DELETE", schema: Deleted, silent: true }),
  programsPage: (q: { search?: string; limit?: number; offset?: number }) => request(`/programs`, { query: pageQuery(q), schema: page(ProgramRow), silent: true }),
  deleteProgram: (id: number) => request(`/programs/${id}`, { method: "DELETE", schema: Deleted, silent: true }),
  facultiesPage: (q: { search?: string; limit?: number; offset?: number }) => request(`/faculties`, { query: pageQuery(q), schema: page(Faculty), silent: true }),
  updateFaculty: (id: number, name: string) => request(`/faculties/${id}`, { method: "PUT", body: { name }, schema: Faculty, silent: true }),
  deleteFaculty: (id: number) => request(`/faculties/${id}`, { method: "DELETE", schema: Deleted, silent: true }),
  sectionsPage: (q: { term_id: number; search?: string; limit?: number; offset?: number }) => request(`/sections`, { query: { ...pageQuery(q), term_id: q.term_id }, schema: page(SectionRow), silent: true }),
  updateSection: (id: number, body: { label?: string | null; program_id?: number | null; enrolment?: number | null; mode?: string; notes?: string | null; class_years?: number[] }) =>
    request(`/sections/${id}`, { method: "PUT", body, schema: SectionAdmin, silent: true }),
  archiveSection: (id: number) => request(`/sections/${id}`, { method: "DELETE", schema: Deleted, silent: true }),
};

export { Pair };
