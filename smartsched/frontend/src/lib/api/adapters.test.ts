import { describe, expect, it } from "vitest";
import { z } from "zod";
import * as adapt from "./adapters";
import { Assignment, GridResponse, ImportJob, MeetingRequest, MoveResponse, Paginated, Room, ScheduleRun, Settings, TestAiResponse } from "./schemas";

/** Payload shapes copied from smartsched/backend/app/schemas/*.py and services/grid.py. */
describe("backend adapters", () => {
  it("turns a FastAPI Page into the frontend pagination and derives meeting fields", () => {
    const page = adapt.page({ items: [{ id: 1, section_id: 3, day: 2, days: [2], start_period: 7, end_period: 9, start_time: "13:30:00", end_time: "15:50:00", weeks: [1, 2], requested_room_text: "A 105", requested_room_ids: [5], requested_building: null, requested_tags: ["pc"], requested_capacity: null, flexible_day: false, needs_room: true, definitive_room_text: null, definitive_room_ids: [], status: "PARSED", parse_warnings: [{ row: 4, column: "Sınıf", raw: "1.Sınıf ", code: "CLASS_YEAR", severity: "info" }], notes: null, archived: false, source_row_index: 4, course_code: "MAT 112", course_name: "Matematik", section_label: "1", program_name: "Tıp", enrolment: 40, mode: "F2F", instructors: ["Prof. Dr. Ayşe Kaya", "Dr. Can Aksoy"] }], total: 1, limit: 100, offset: 200 }) as { items: unknown[] };
    const parsed = Paginated(z.preprocess(adapt.meeting, MeetingRequest)).parse(page);
    expect(parsed.page).toBe(3);
    expect(parsed.page_size).toBe(100);
    const m = parsed.items[0];
    expect(m.start_time).toBe("13:30");
    expect(m.instructor).toBe("Prof. Dr. Ayşe Kaya / Dr. Can Aksoy");
    expect(m.requested_tags).toEqual([]);
    expect(m.parse_warnings[0]).toMatchObject({ field: "Sınıf", value: "1.Sınıf ", severity: "info" });
  });

  it("normalises RoomOut (string floor, no building_code)", () => {
    const r = Room.parse(adapt.room({ id: 7, building_id: null, code: "CZ01", display_name: "C z01", floor: "z", capacity: 30, exam_capacity: 16, tags: ["lab"], is_bookable: true, notes: null, photo_url: null, legacy_crbs_room_id: 12, room_group: null, custom_fields: {} }));
    expect(r.building_code).toBe("C");
    expect(r.floor).toBe(0);
    expect(r.tags).toEqual(["LAB"]);
  });

  it("converts the backend grid (day × room × cells) into room/assignment/block spans", () => {
    const cell = (id: number, sp: number, ep: number, p: number, extra: Record<string, unknown> = {}) => ({ kind: "assignment", id, label: "BME 419", start_period: sp, end_period: ep, head: p === sp, locked: false, origin: "SOLVER", tags: [], notes: null, ...extra });
    const cells = Array.from({ length: 18 }, (_, i) => (i + 1 >= 7 && i + 1 <= 9 ? cell(42, 7, 9, i + 1) : null));
    const blockCells = Array.from({ length: 18 }, (_, i) => (i < 6 ? { kind: "block", id: 9, label: "HAZIRLIK", start_period: 1, end_period: 6, head: i === 0, tags: [], notes: null } : null));
    const g = GridResponse.parse(adapt.grid({ run_id: 1, term_id: 1, week: 7, periods: [], days: [{ day: 3, label: "Çarşamba", date: "2026-03-18", rooms: [{ room_id: 1, code: "A204", display_name: "A 204", capacity: 156, exam_capacity: 74, tags: ["AMPHI"], cells }, { room_id: 2, code: "A101", display_name: "A 101", capacity: 58, exam_capacity: 30, tags: [], cells: blockCells }] }], assignments: 1, blocks: 1 }));
    expect(g.rooms.map((r) => r.display_name)).toEqual(["A 204", "A 101"]);
    expect(g.periods).toHaveLength(18);
    expect(g.assignments).toHaveLength(1);
    expect(g.assignments[0]).toMatchObject({ id: 42, day: 3, start_period: 7, end_period: 9, room_ids: [1], course_code: "BME 419" });
    expect(g.blocks[0]).toMatchObject({ room_id: 2, label: "HAZIRLIK", start_period: 1, end_period: 6 });
  });

  it("maps RunOut / AssignmentOut / MoveOut field names", () => {
    const run = ScheduleRun.parse(adapt.run({ id: 3, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [7] }, status: "RUNNING", params: {}, objective_value: null, soft_score: null, hard_score: null, stats: { progress: 42, phase: "search" }, diagnosis: [{ message: "BME 419 needs 102 seats", suggestions: ["Release A 204"] }], parent_run_id: null, prompt_text: null, label: null, is_active: true, error: null, created_at: "2026-03-14T14:02:00Z", started_at: null, finished_at: null }));
    expect(run.progress).toBe(42);
    expect(run.term_code).toBe("2026-BAHAR");
    expect(run.diagnosis[0]).toMatchObject({ id: "0", index: 0, severity: "high", suggestions: [{ id: "s0", text: "Release A 204", action: "manual", applicable: false }] });
    // a RunOut without term_code is a contract violation now (no more `term-{id}` synthesis)
    expect(ScheduleRun.safeParse(adapt.run({ ...run, term_code: undefined })).success).toBe(false);
    const a = Assignment.parse(adapt.assignment({ id: 5, run_id: 3, meeting_request_id: 1, exam_request_id: null, week: null, weeks: [1, 2], day: 2, date: null, start_period: 1, end_period: 2, room_ids: ["4"], label: null, course_codes: ["HEM 334", "NRS 304"], tags: [], notes: null, is_locked: true, origin: "IMPORT", archived: false, display_label: "HEM 334 / NRS 304", room_codes: ["A102"] }));
    expect(a).toMatchObject({ label: "HEM 334 / NRS 304", course_code: "HEM 334", room_ids: [4], is_locked: true, size: 0 });
    const mv = MoveResponse.parse(adapt.moveResponse({ ok: false, assignment: null, conflicts: [{ type: "room", detail: "A 204 busy", assignment_id: 9 }] }));
    expect(mv.conflicts[0]).toMatchObject({ kind: "room", message: "A 204 busy", with_assignment_id: 9 });
  });

  it("maps masked settings and test-ai results", () => {
    const s = Settings.parse(adapt.settings({ anthropic_api_key: { set: true, masked: "sk-ant-…3f9a", source: "db" }, anthropic_model: "claude-sonnet-5-5", solver_default_time_limit: 90, solver_workers: 4, solver_weights: '{"room_preference": 5}' }));
    expect(s).toMatchObject({ anthropic_api_key_masked: "sk-ant-…3f9a", solver_default_workers: 4, default_weights: { room_preference: 5 }, solver_default_time_limit: 90 });
    expect(s.available_models[0]).toBe("claude-opus-5-5");
    expect(adapt.DEFAULT_MODELS[0]).toBe("claude-opus-5-5");
    expect(Settings.parse(adapt.settings({ anthropic_api_key: { set: false }, solver_default_time_limit: 60 })).anthropic_model).toBe("claude-opus-5-5");
    // only backend field names: no frontend duplicates ride along
    expect(adapt.settingsUpdateBody({ anthropic_model: "claude-opus-5-5", solver_default_workers: 6, default_weights: { stability: 2 }, solver_default_seed: 9 })).toEqual({ anthropic_model: "claude-opus-5-5", solver_workers: 6, solver_weights: { stability: 2 }, extra: { solver_default_seed: 9 } });
    expect(TestAiResponse.parse(adapt.testAi({ ok: false, model: "claude-sonnet-5-5", detail: "AuthenticationError: invalid", used_key: "stored" }))).toMatchObject({ ok: false, error: "AuthenticationError: invalid" });
    expect(adapt.listQuery({ q: "MAT", page: 2, page_size: 50 })).toMatchObject({ search: "MAT", limit: 50, offset: 50 });
  });

  it("reads naive backend datetimes as UTC", () => {
    expect(adapt.utcIso("2026-10-08T07:30:12.5")).toBe("2026-10-08T07:30:12.5Z");
    expect(adapt.utcIso("2026-10-08T07:30:12Z")).toBe("2026-10-08T07:30:12Z");
    expect(adapt.utcIso("2026-10-08T10:30:12+03:00")).toBe("2026-10-08T10:30:12+03:00");
    expect(adapt.utcIso("2026-10-08")).toBe("2026-10-08");
  });

  it("reads the backend import job (ImportReport.to_dict) and its empty summary while it runs", () => {
    // trimmed from GET /imports/{id} after the Bahar planning list (the real e2e backend)
    const done = ImportJob.parse(
      adapt.importJob({
        id: 1, kind: "planning-list", filename: "bahar_derslik_planlama_listesi_v5.xlsx", term_code: "2026-BAHAR", status: "DONE", error: null,
        created_at: "2026-10-08T14:05:39.899007", finished_at: "2026-10-08T14:06:01",
        summary: {
          rows_total: 1529, rows_imported: 1524, rows_skipped_count: 2,
          rows_skipped: [{ row: 117, reason: "no course code", detail: null }, { row: 1406, reason: "no course code", detail: "MDF-516" }],
          warnings: ["row 11: weeks value 0; assuming all", "row 132: start time 09:00 not on the grid; snapped to P1 (08:30)"],
          created: { sections: 3, meeting_requests: 4 }, updated: {}, warnings_count: 2,
        },
      }),
    );
    expect(done.summary).toMatchObject({ rows: 1529, created: 7, updated: 0, skipped: 2 });
    expect(done.summary.warnings).toEqual([
      { row: 117, field: "", value: null, message: "no course code", severity: "error" },
      { row: 1406, field: "", value: "MDF-516", message: "no course code", severity: "error" },
      { row: 11, field: "", value: null, message: "weeks value 0; assuming all", severity: "warning" },
      { row: 132, field: "", value: null, message: "start time 09:00 not on the grid; snapped to P1 (08:30)", severity: "warning" },
    ]);
    expect(done.created_at).toBe("2026-10-08T14:05:39.899007Z");
    const queued = ImportJob.parse(adapt.importJob({ id: 2, kind: "weekly-grid", filename: "grid.xlsx", status: "QUEUED", summary: {}, created_at: "2026-10-08T14:07:00" }));
    expect(queued.summary).toEqual({ rows: 0, created: 0, updated: 0, skipped: 0, warnings: [] });
  });
});
