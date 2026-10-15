"use client";
/**
 * The wizard's state and its autosave (program-wizard spec §0, §9): every draft is kept in this browser (so an
 * offline edit is never lost) and saved to the server through the catalog_admin endpoints 800 ms after the last
 * edit, in the dependency order of `planSync`. "Tüm değişiklikler kaydedildi · 1 dk önce" / "Kaydediliyor…" /
 * "Kaydedilemedi · Yeniden dene". Resume: the local draft, or a programme rebuilt from the server.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { catalogApi } from "@/lib/api/catalog-admin";
import { HttpError } from "@/lib/api/client";
import { emptyPattern, hashes, patternBody, meetingIds, newCourse, newDraft, newSection, normalizeCode, planSync, type CourseDraft, type Draft, type SectionDraft, type SyncOp } from "./wizard-model";

interface DraftStore {
  drafts: Record<string, Draft>;
  put: (d: Draft) => void;
  remove: (key: string) => void;
}

export const useDraftStore = create<DraftStore>()(
  persist(
    (set) => ({
      drafts: {},
      put: (d) => set((s) => ({ drafts: { ...s.drafts, [d.key]: d } })),
      remove: (key) =>
        set((s) => {
          const next = { ...s.drafts };
          delete next[key];
          return { drafts: next };
        }),
    }),
    { name: "smartsched.programWizard.drafts" },
  ),
);

export type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; at: string } | { kind: "error"; message: string };

const DEBOUNCE_MS = 800;

function findSection(d: Draft, course: string, section: string): { c: CourseDraft; s: SectionDraft } | null {
  const c = d.courses.find((x) => x.key === course);
  const s = c?.sections.find((x) => x.key === section);
  return c && s ? { c, s } : null;
}

function patchCourse(d: Draft, key: string, fn: (c: CourseDraft) => CourseDraft): Draft {
  return { ...d, courses: d.courses.map((c) => (c.key === key ? fn(c) : c)) };
}
function patchSection(d: Draft, course: string, section: string, fn: (s: SectionDraft) => SectionDraft): Draft {
  return patchCourse(d, course, (c) => ({ ...c, sections: c.sections.map((s) => (s.key === section ? fn(s) : s)) }));
}

/** one write; returns the draft with the ids the server gave and the new hash, plus server warnings */
async function runOp(d: Draft, op: SyncOp): Promise<{ draft: Draft; warnings: string[] }> {
  const warnings: string[] = [];
  const p = d.program;
  switch (op.kind) {
    case "faculty": {
      const found = (await catalogApi.faculties(p.facultyName.trim())).items.find((f) => f.name.toLocaleLowerCase("tr-TR") === p.facultyName.trim().toLocaleLowerCase("tr-TR"));
      const f = found ?? (await catalogApi.createFaculty(p.facultyName.trim()));
      return { draft: { ...d, program: { ...p, facultyId: f.id, facultyName: f.name } }, warnings };
    }
    case "program": {
      const body = { name: p.name.trim(), faculty_id: p.facultyId, is_evening: p.evening };
      const row = p.id ? await catalogApi.updateProgram(p.id, body) : await catalogApi.createProgram(body);
      const next = { ...d, program: { ...p, id: row.id } };
      return { draft: { ...next, synced: { ...d.synced, program: hashes.program(next) } }, warnings };
    }
    case "course": {
      const c = d.courses.find((x) => x.key === op.course)!;
      const code = normalizeCode(c.code).code;
      const body = { code, name: c.name.trim() || null, t_hours: c.t, u_hours: c.u, l_hours: c.l, ects: c.ects };
      let id = c.id;
      let own = c.own;
      if (!id) {
        const check = await catalogApi.codeCheck(code);
        if (check.duplicate) {
          // an existing catalogue course (MBG 014, lisans) is reused as is, never edited from here
          id = check.duplicate.id;
          own = false;
          warnings.push(`reused:${check.duplicate.display_code}`);
        } else {
          id = (await catalogApi.createCourse(body)).id;
          own = true;
        }
      } else if (own) {
        await catalogApi.updateCourse(id, body);
      }
      const next = patchCourse(d, c.key, (x) => ({ ...x, id, own, code }));
      const nc = next.courses.find((x) => x.key === c.key)!;
      return { draft: { ...next, synced: { ...next.synced, [c.key]: hashes.course(nc) } }, warnings };
    }
    case "instructor": {
      const hit = findSection(d, op.course, op.section)!;
      const ref = hit.s.instructors[op.slot]!;
      const row = await catalogApi.createInstructor({ full_name: ref.name.trim(), title: ref.title ?? null });
      return { draft: patchSection(d, op.course, op.section, (s) => ({ ...s, instructors: s.instructors.map((i, j) => (j === op.slot ? { id: row.id, name: row.full_name, title: row.title } : i)) as SectionDraft["instructors"] })), warnings };
    }
    case "section": {
      const hit = findSection(d, op.course, op.section)!;
      if (!hit.c.id || !p.id || !d.termId) return { draft: d, warnings };
      const instructors = hit.s.instructors.flatMap((i, j) => (i?.id ? [{ instructor_id: i.id, role: (j === 0 ? "PRIMARY" : "SECONDARY") as "PRIMARY" | "SECONDARY" }] : []));
      const body = { program_id: p.id, label: hit.s.label, class_years: [hit.c.year], enrolment: hit.s.enrolment, mode: hit.c.mode, instructors };
      const row = hit.s.id ? await catalogApi.updateSection(hit.s.id, body) : await catalogApi.createSection({ term_id: d.termId, course_id: hit.c.id, ...body });
      const next = patchSection(d, op.course, op.section, (s) => ({ ...s, id: row.id }));
      const h = findSection(next, op.course, op.section)!;
      return { draft: { ...next, synced: { ...next.synced, [op.section]: hashes.section(next, h.c, h.s) } }, warnings };
    }
    case "pattern": {
      const hit = findSection(d, op.course, op.section)!;
      if (!hit.s.id) return { draft: d, warnings };
      const out = await catalogApi.pattern(hit.s.id, patternBody(hit.c, hit.s.enrolment));
      warnings.push(...out.warnings);
      const next = patchSection(d, op.course, op.section, (s) => ({ ...s, meetingIds: out.created.map((m) => m.id) }));
      const h = findSection(next, op.course, op.section)!;
      return { draft: { ...next, synced: { ...next.synced, [`${op.section}:pattern`]: hashes.pattern(h.c, h.s) } }, warnings };
    }
    case "rules": {
      if (!d.termId) return { draft: d, warnings };
      for (const id of d.rules.ruleIds) await catalogApi.deleteRule(id).catch(() => undefined);
      const events = meetingIds(d);
      const ids: number[] = [];
      const w = d.rules.window;
      if (w.enabled) ids.push((await catalogApi.createRule({ term_id: d.termId, kind: "day_window", params: { event_ids: events, earliest: w.earliest, latest: w.latest }, hardness: w.hard ? "hard" : "soft", weight: w.hard ? 1 : 10, nl_text: `${p.name}: P${w.earliest}–P${w.latest}` })).id);
      if (d.rules.sameRoom) ids.push((await catalogApi.createRule({ term_id: d.termId, kind: "same_room_across_weeks", params: { event_ids: events }, hardness: "soft", weight: 10, nl_text: `${p.name}: aynı oda / same room` })).id);
      const next = { ...d, rules: { ...d.rules, ruleIds: ids } };
      return { draft: { ...next, synced: { ...next.synced, rules: hashes.rules(next) } }, warnings };
    }
  }
}

export function errorText(e: unknown): string {
  if (e instanceof HttpError) {
    const raw = e.detail as { detail?: unknown } | undefined;
    const body = raw && typeof raw === "object" && "detail" in raw ? raw.detail : raw;
    if (typeof body === "string") return body;
    if (body && typeof body === "object" && "message" in (body as Record<string, unknown>)) return String((body as Record<string, unknown>).message);
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

/** the draft of the URL (`?draft=`), its updater, and the autosave state */
export function useWizard(key: string | null) {
  const stored = useDraftStore((s) => (key ? s.drafts[key] : undefined));
  const put = useDraftStore((s) => s.put);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const [warnings, setWarnings] = useState<string[]>([]);
  const latest = useRef<Draft | undefined>(stored);
  const running = useRef(false);
  const again = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushRef = useRef<() => Promise<boolean>>(async () => true);
  useEffect(() => {
    latest.current = stored;
  }, [stored]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (running.current) {
      again.current = true;
      return false;
    }
    running.current = true;
    let ok = true;
    try {
      // a pass can make the next one possible (sections need the course ids, rules the meeting ids): re-plan,
      // at most 5 passes (an op that cannot run yet must not spin)
      for (let pass = 0; pass < 5; pass++) {
        again.current = false;
        let d = latest.current;
        if (!d) break;
        const ops = planSync(d);
        if (!ops.length) break;
        setSave({ kind: "saving" });
        const found: string[] = [];
        for (const op of ops) {
          const cur = useDraftStore.getState().drafts[d.key] ?? d;
          const out = await runOp(mergeIds(cur, d), op);
          d = out.draft;
          found.push(...out.warnings);
          put(mergeIds(useDraftStore.getState().drafts[d.key] ?? d, d));
          latest.current = useDraftStore.getState().drafts[d.key];
        }
        if (found.length) setWarnings((w) => [...new Set([...w, ...found])].slice(-20));
      }
      const at = new Date().toISOString();
      const cur = latest.current;
      if (cur) put({ ...useDraftStore.getState().drafts[cur.key]!, savedAt: at });
      setSave({ kind: "saved", at });
    } catch (e) {
      ok = false;
      setSave({ kind: "error", message: errorText(e) });
    } finally {
      running.current = false;
      if (again.current && ok) timer.current = setTimeout(() => void flushRef.current(), DEBOUNCE_MS);
    }
    return ok;
  }, [put]);
  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);

  const update = useCallback(
    (fn: (d: Draft) => Draft) => {
      const cur = latest.current;
      if (!cur) return;
      const next = fn(cur);
      latest.current = next;
      put(next);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), DEBOUNCE_MS);
    },
    [put, flush],
  );

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { draft: stored, update, save, flush, warnings };
}

/**
 * The user may have edited while a write was in flight: keep their fields (`cur`) and take only the server ids,
 * meeting ids and rule ids from the write's result (`done`).
 */
export function mergeIds(cur: Draft, done: Draft): Draft {
  const courses = cur.courses.map((c) => {
    const dc = done.courses.find((x) => x.key === c.key);
    if (!dc) return c;
    return {
      ...c,
      id: dc.id ?? c.id,
      own: dc.id ? dc.own : c.own,
      code: dc.id && !c.id ? dc.code : c.code,
      sections: c.sections.map((s) => {
        const ds = dc.sections.find((x) => x.key === s.key);
        if (!ds) return s;
        return { ...s, id: ds.id ?? s.id, meetingIds: ds.meetingIds.length || ds.id ? ds.meetingIds : s.meetingIds, instructors: s.instructors.map((i, j) => (i && i.id === null && ds.instructors[j]?.id && ds.instructors[j]!.name === i.name ? ds.instructors[j] : i)) as SectionDraft["instructors"] };
      }),
    };
  });
  return {
    ...cur,
    program: { ...cur.program, id: done.program.id ?? cur.program.id, facultyId: cur.program.facultyId ?? done.program.facultyId, facultyName: cur.program.facultyId ? cur.program.facultyName : done.program.facultyName || cur.program.facultyName },
    courses,
    rules: { ...cur.rules, ruleIds: done.rules.ruleIds },
    synced: { ...cur.synced, ...done.synced },
  };
}

/** start a new draft (optionally on a term), stored locally; returns its key */
export function createDraft(termId: number | null, termCode: string | null): string {
  const d = { ...newDraft(), termId, termCode };
  useDraftStore.getState().put(d);
  return d.key;
}

/** resume a programme that exists on the server (another device, a cleared browser): rebuild the draft */
export async function draftFromServer(termId: number, termCode: string, programId: number): Promise<string> {
  const programs = await catalogApi.programs({});
  const prog = programs.items.find((p) => p.id === programId);
  if (!prog) throw new Error(`program ${programId} not found`);
  const sections = (await catalogApi.sections({ term_id: termId, program_id: programId })).items;
  const meetings = (await catalogApi.meetings({ term_id: termId, program_id: programId })).items;
  const d = newDraft();
  d.termId = termId;
  d.termCode = termCode;
  d.step = "courses";
  d.program = { ...d.program, id: prog.id, facultyId: prog.faculty_id, name: prog.name, evening: prog.is_evening };
  const byCourse = new Map<number, CourseDraft>();
  for (const s of sections) {
    const full = await catalogApi.section(s.id);
    let c = byCourse.get(s.course_id);
    if (!c) {
      const found = (await catalogApi.courses(full.course_code ?? "")).items.find((x) => x.id === s.course_id);
      c = newCourse({ id: s.course_id, own: true, code: full.course_code ?? "", name: full.course_name ?? "", t: found?.t_hours ?? 0, u: found?.u_hours ?? 0, l: found?.l_hours ?? 0, ects: found?.ects ?? null, year: s.class_year ?? 1, mode: (["F2F", "ONLINE", "HYBRID"].includes(s.mode) ? s.mode : "F2F") as CourseDraft["mode"], sections: [], pattern: emptyPattern() });
      byCourse.set(s.course_id, c);
    }
    const sec = newSection(s.label ?? "1", s.enrolment);
    sec.id = s.id;
    const prim = full.instructors.find((i) => i.role === "PRIMARY");
    const second = full.instructors.find((i) => i.role !== "PRIMARY");
    sec.instructors = [prim ? { id: prim.instructor_id, name: prim.full_name, title: prim.title } : null, second ? { id: second.instructor_id, name: second.full_name, title: second.title } : null];
    sec.meetingIds = meetings.filter((m) => m.section_id === s.id).map((m) => m.id);
    c.sections.push(sec);
  }
  d.courses = [...byCourse.values()];
  // what is on the server counts as saved: only the next edit writes again
  d.synced.program = hashes.program(d);
  for (const c of d.courses) {
    d.synced[c.key] = hashes.course(c);
    for (const s of c.sections) {
      d.synced[s.key] = hashes.section(d, c, s);
      if (s.meetingIds.length) d.synced[`${s.key}:pattern`] = hashes.pattern(c, s);
    }
  }
  useDraftStore.getState().put(d);
  return d.key;
}
