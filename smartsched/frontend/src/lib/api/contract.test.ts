/**
 * Contract test: payloads recorded from the real FastAPI backend (SQLite, real Bahar fixtures:
 * `python -m app.cli import weekly-grid|planning-list`, see docs/testing/2026-10-08-real-backend-e2e.md)
 * must parse with the exact schemas + adapters the UI uses. Re-record after backend schema changes.
 */
import { describe, expect, it } from "vitest";
import { responseSchemas as S } from "./endpoints";

import aiCatalog from "./__fixtures__/real/ai_catalog.json";
import assignments from "./__fixtures__/real/assignments.json";
import buildings from "./__fixtures__/real/buildings.json";
import chatEmpty from "./__fixtures__/real/chat_empty.json";
import constraints from "./__fixtures__/real/constraints.json";
import dashboard from "./__fixtures__/real/dashboard.json";
import grid from "./__fixtures__/real/grid.json";
import imports from "./__fixtures__/real/imports.json";
import me from "./__fixtures__/real/me.json";
import meetings from "./__fixtures__/real/meetings.json";
import meetingsNeedsReview from "./__fixtures__/real/meetings_needs_review.json";
import moveConflict from "./__fixtures__/real/move_conflict.json";
import programs from "./__fixtures__/real/programs.json";
import rooms from "./__fixtures__/real/rooms.json";
import runInfeasible from "./__fixtures__/real/run_infeasible.json";
import runs from "./__fixtures__/real/runs.json";
import settings from "./__fixtures__/real/settings.json";
import terms from "./__fixtures__/real/terms.json";
import users from "./__fixtures__/real/users.json";
import weeks from "./__fixtures__/real/weeks.json";

function ok<T>(schema: { safeParse: (v: unknown) => { success: true; data: T } | { success: false; error: { issues: unknown[] } } }, v: unknown): T {
  const r = schema.safeParse(v);
  if (!r.success) throw new Error(JSON.stringify(r.error.issues.slice(0, 3)));
  return r.data;
}

describe("real backend contract (recorded payloads)", () => {
  it("reference data: me, terms, weeks, rooms, buildings, programs", () => {
    expect(ok(S.me, me).role).toBe("ADMIN");
    const t = ok(S.terms, terms);
    expect(t[0].code).toBe("2026-BAHAR");
    expect(ok(S.weeks, weeks)[0].label).toContain("Şubat");
    const r = ok(S.rooms, rooms);
    const a204 = r.find((x) => x.display_name === "A 204");
    expect(a204).toMatchObject({ capacity: 156, building_code: "A" });
    expect(r.find((x) => x.code === "A201")?.tags).toContain("TIP");
    expect(ok(S.buildings, buildings).length).toBeGreaterThan(0);
    expect(ok(S.programs, programs).length).toBeGreaterThan(0);
  });

  it("requests inbox pages (Turkish text, comma decimals, dotted times already normalised server-side)", () => {
    const m = ok(S.meetings, meetings);
    expect(m.total).toBeGreaterThan(0);
    expect(m.items[0].course_code).toMatch(/^PSI/);
    expect(m.items.every((x) => x.start_time === null || /^\d{2}:\d{2}$/.test(x.start_time))).toBe(true);
    const nr = ok(S.meetings, meetingsNeedsReview);
    expect(nr.items.every((x) => x.status === "NEEDS_REVIEW")).toBe(true);
  });

  it("runs: term code from the backend, structured diagnoses with applicable options", () => {
    const list = ok(S.runs, runs);
    expect(list.every((x) => x.term_code === "2026-BAHAR")).toBe(true);
    const inf = ok(S.run, runInfeasible);
    expect(inf.status).toBe("INFEASIBLE");
    expect(inf.diagnosis.length).toBeGreaterThan(0);
    expect(inf.diagnosis.every((d, i) => d.index === i && d.event_labels.length === d.event_ids.length)).toBe(true);
    expect(inf.diagnosis.flatMap((d) => d.suggestions).some((s) => s.applicable)).toBe(true);
  });

  it("grid + assignments + move conflicts carry the enrichment the UI needs", () => {
    const g = ok(S.grid, grid);
    expect(g.weeks.length).toBeGreaterThan(10);
    expect(g.assignments.length).toBeGreaterThan(0);
    expect(g.rooms.every((r) => r.building_code.length === 1)).toBe(true);
    const a = ok(S.assignments, assignments);
    expect(a.every((x) => x.weeks.includes(3) && x.day === 1)).toBe(true);
    const mv = ok(S.move, moveConflict);
    expect(mv.ok).toBe(false);
    expect(mv.conflicts[0].message).toMatch(/is taken by/);
  });

  it("settings, dashboard, users, constraints, AI catalogue, chat", () => {
    const st = ok(S.settings, settings);
    expect(st.available_models[0]).toBe("claude-opus-5-5");
    const d = ok(S.dashboard, dashboard);
    expect(d.term.code).toBe("2026-BAHAR");
    expect(d.utilisation_building_day.length).toBe(7 * d.utilisation_by_building.length);
    expect(d.requests_total).toBeGreaterThan(1000);
    const u = ok(S.users, users);
    expect(u[0]).not.toHaveProperty("password_hash");
    ok(S.constraints, constraints);
    expect(ok(S.imports, imports).length).toBeGreaterThanOrEqual(0);
    expect(ok(S.aiCatalog, aiCatalog).kinds.length).toBeGreaterThan(0);
    expect(ok(S.chat(1), chatEmpty)).toEqual({ messages: [] });
  });
});
