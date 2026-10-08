/**
 * MSW handlers for the Generator Studio (backend `app/api/v1/studio.py` + `presets.py`), speaking the
 * backend shapes (`app/schemas/studio.py`). State lives in the shared mock state (see handlers.ts) so a
 * class edit here shows up in the Requests inbox and vice versa. Deterministic for Playwright.
 */
import { HttpResponse, http, type DefaultBodyType } from "msw";
import type { Constraint, ExamRequest, MeetingRequest, ProposedConstraint, ScheduleRun, Settings } from "@/lib/api/schemas";
import { PERIODS } from "@/lib/time";
import { programs, rooms, terms, weeks } from "./data";
import { BUILTINS, BUILTIN_TEXT, MAPPING_ROLES, allowedHardness, catalogTitle, studioMeta } from "./studio-data";

type Rec = Record<string, unknown>;
export type MockConstraint = Constraint & { source_ref?: Rec | null };

interface MockDraft {
  draft_id: number;
  term_id: number;
  user_id: number;
  kind: "COURSE" | "EXAM";
  version: number;
  horizon: "WEEK" | "MONTH" | "TERM";
  horizon_params: Rec;
  excluded_event_ids: number[];
  pins: { event_id: number; room_ids?: number[]; day?: number | null; start_period?: number | null }[];
  disabled_builtin_kinds: string[];
  disabled_rule_ids: number[];
  rule_overrides: Record<string, { hardness?: "hard" | "soft" | null; weight?: number | null }>;
  preset_id: number | null;
  last_step: string | null;
  params: Rec;
  updated_at: string;
}

interface MockPreset {
  id: number;
  name: string;
  description: string | null;
  kind: string;
  rules: Rec[];
  scope: Rec;
  filters: Rec;
  disabled_builtin_kinds: string[];
  created_by: number | null;
  author: string | null;
  created_at: string;
  updated_at: string;
}

interface PrecheckItemOut {
  id: string;
  category: "impossible" | "clash" | "no_match" | "info";
  severity: "error" | "warning" | "info";
  group: string;
  title: { tr: string; en: string };
  message: { tr: string; en: string };
  detail: string;
  event_ids: number[];
  classes: Rec[];
  constraint_kinds: string[];
  constraint_ids: number[];
  fixes: { option: string; label: { tr: string; en: string }; action: { type: string; payload: Rec }; admin_only: boolean }[];
}

export interface StudioMockState {
  drafts: Map<string, MockDraft>;
  /** imported values per meeting id, captured before the first studio edit (backend `imported_snapshots`) */
  snapshots: Map<number, Partial<MeetingRequest>>;
  presets: MockPreset[];
  lastPrecheck: Map<string, PrecheckItemOut[]>;
}

export interface StudioHost {
  meetings: MeetingRequest[];
  exams: ExamRequest[];
  constraints: MockConstraint[];
  runs: ScheduleRun[];
  settings: Settings;
  studio: StudioMockState;
  nextId: () => number;
  startRun: (run: ScheduleRun) => void;
  getRun: (id: number) => ScheduleRun | undefined;
}

const t = (tr: string, en: string) => ({ tr, en });
const now = () => new Date().toISOString();

/** Rules of the previous terms, so "Copy from last term" has something to copy. */
export const studioSeedConstraints: MockConstraint[] = [
  { id: 901, term_id: 3, run_id: null, kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 5, source: "ADMIN", nl_text: "Her hafta aynı derslik", enabled: true },
  { id: 902, term_id: 3, run_id: null, kind: "room_forbid", params: { room_ids: [61], programs: ["Psikoloji"] }, hardness: "hard", weight: 5, source: "ADMIN", nl_text: "D 107 Psikoloji için kullanılmasın", enabled: true },
  { id: 903, term_id: 3, run_id: null, kind: "building_preference", params: { building: "C", days: [1], programs: ["Eczacılık"] }, hardness: "soft", weight: 5, source: "AI", nl_text: "Eczacılık pazartesi C blokta kalsın", enabled: true },
  { id: 904, term_id: 3, run_id: null, kind: "room_pin", params: { room_ids: [9], event_ids: [99999] }, hardness: "hard", weight: 5, source: "FILE", nl_text: "MAT 112 her zaman A 206", enabled: true },
];

export function freshStudioState(): StudioMockState {
  const ts = "2026-09-20T09:00:00Z";
  return {
    drafts: new Map(),
    snapshots: new Map(),
    presets: [
      { id: 1, name: "Bahar standard", description: "Same room every week, evening programmes in B/C, small classes out of big halls", kind: "COURSE", rules: [
        { kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 5, enabled: true, nl_text: "Same room every week" },
        { kind: "evening_programs_in_buildings", params: { buildings: ["B", "C"] }, hardness: "soft", weight: 5, enabled: true, nl_text: "İkinci öğretim B/C bloklarda" },
        { kind: "min_capacity_waste", params: { unit: 10 }, hardness: "soft", weight: 2, enabled: true, nl_text: "Küçük sınıfları büyük amfiye koyma" },
      ], scope: { horizon: "TERM" }, filters: {}, disabled_builtin_kinds: [], created_by: 1, author: "Fatih Demir", created_at: ts, updated_at: ts },
      { id: 2, name: "Final week", description: "At least one period between exams of the same class", kind: "EXAM", rules: [
        { kind: "exam_gap", params: { min_periods: 1 }, hardness: "hard", weight: 5, enabled: true, nl_text: "Sınavlar arasında en az 1 ders saati" },
      ], scope: { horizon: "WEEK" }, filters: {}, disabled_builtin_kinds: [], created_by: 2, author: "Gözde Ayrancıgil", created_at: ts, updated_at: ts },
    ],
    lastPrecheck: new Map(),
  };
}

/** FormData file entry (duck-typed: jsdom and undici have different File classes). */
function fileOf(v: FormDataEntryValue | null): { name: string; text: () => Promise<string> } | null {
  return v !== null && typeof v === "object" && "name" in v && typeof (v as { text?: unknown }).text === "function" ? (v as unknown as { name: string; text: () => Promise<string> }) : null;
}

const json = <T extends DefaultBodyType>(body: T, init?: ResponseInit) => HttpResponse.json(body, init);
const err = (status: number, detail: unknown) => json({ detail } as DefaultBodyType, { status });
const kindOf = (url: URL): "COURSE" | "EXAM" => (url.searchParams.get("kind") === "EXAM" ? "EXAM" : "COURSE");
const roomCode = (id: number) => rooms.find((r) => r.id === id)?.display_name ?? `#${id}`;
const programOf = (id: number) => programs.find((p) => p.id === id);
const asNums = (v: unknown): number[] => (Array.isArray(v) ? v : v === undefined || v === null ? [] : [v]).map(Number).filter(Number.isFinite);
const asStrs = (v: unknown): string[] => (Array.isArray(v) ? v : v === undefined || v === null ? [] : [v]).map(String);

const MEETING_FIELDS = ["enrolment", "mode", "day", "start_period", "end_period", "weeks", "requested_room_ids", "requested_building", "requested_tags", "definitive_room_ids", "flexible_day", "status"] as const;
type MeetingField = (typeof MEETING_FIELDS)[number];
const REMOTE = new Set(["ONLINE", "UZEM", "ASYNC", "HOSPITAL"]);

function termWeeks(termId: number) {
  return weeks.filter((w) => w.term_id === termId);
}

function resolveWeeks(d: MockDraft): number[] {
  const tw = termWeeks(d.term_id);
  const lecture = tw.filter((w) => w.kind === "LECTURE" || w.kind === "MAKEUP").map((w) => w.index);
  if (d.horizon === "TERM") return d.kind === "EXAM" ? tw.filter((w) => w.kind === "EXAM").map((w) => w.index) : lecture;
  const chosen = asNums(d.horizon_params.weeks).sort((a, b) => a - b);
  if (d.horizon === "MONTH") {
    const start = Number(d.horizon_params.start_week ?? chosen[0] ?? lecture[0] ?? 1);
    return [0, 1, 2, 3].map((k) => start + k).filter((w) => tw.some((x) => x.index === w));
  }
  return chosen;
}

export function createStudioHandlers(host: () => StudioHost) {
  const base = "*/api/v1";

  /* ----------------------------------------------------------------------- drafts */
  function draftFor(termId: number, kind: "COURSE" | "EXAM"): MockDraft {
    const h = host();
    const key = `${termId}:${kind}`;
    let d = h.studio.drafts.get(key);
    if (!d) {
      d = { draft_id: h.nextId(), term_id: termId, user_id: 1, kind, version: 1, horizon: "TERM", horizon_params: {}, excluded_event_ids: [], pins: [], disabled_builtin_kinds: [], disabled_rule_ids: [], rule_overrides: {}, preset_id: null, last_step: null, params: {}, updated_at: now() };
      h.studio.drafts.set(key, d);
    }
    return d;
  }

  function termRules(termId: number): MockConstraint[] {
    return host().constraints.filter((c) => c.term_id === termId && c.run_id === null);
  }
  function inPlay(d: MockDraft): MockConstraint[] {
    const off = new Set(d.disabled_rule_ids);
    return termRules(d.term_id).filter((c) => c.enabled && !off.has(c.id));
  }
  function effHard(d: MockDraft, c: MockConstraint): boolean {
    return (d.rule_overrides[String(c.id)]?.hardness ?? c.hardness) === "hard";
  }

  function draftOut(d: MockDraft) {
    const wk = resolveWeeks(d);
    const holidays = new Set(termWeeks(d.term_id).filter((w) => w.kind === "HOLIDAY").map((w) => w.index));
    return {
      draft_id: d.draft_id, term_id: d.term_id, user_id: d.user_id, kind: d.kind, version: d.version, etag: `"${d.version}"`,
      scope: { horizon: d.horizon, horizon_params: d.horizon_params, weeks: wk, holiday_weeks: wk.filter((w) => holidays.has(w)) },
      excluded_event_ids: d.excluded_event_ids, pins: d.pins, disabled_builtin_kinds: d.disabled_builtin_kinds, disabled_rule_ids: d.disabled_rule_ids,
      rule_overrides: d.rule_overrides, rule_ids: inPlay(d).map((c) => c.id), preset_id: d.preset_id, last_step: d.last_step, params: d.params, updated_at: d.updated_at,
    };
  }

  /* ---------------------------------------------------------------------- classes */
  type Row = ReturnType<typeof meetingRow>;
  function snapshot(m: MeetingRequest) {
    const s = host().studio.snapshots;
    if (!s.has(m.id)) s.set(m.id, structuredClone(Object.fromEntries(MEETING_FIELDS.map((f) => [f, m[f]]))) as Partial<MeetingRequest>);
  }
  function changedFields(m: MeetingRequest) {
    const snap = host().studio.snapshots.get(m.id);
    if (!snap) return [];
    return MEETING_FIELDS.filter((f) => JSON.stringify(snap[f] ?? null) !== JSON.stringify(m[f] ?? null)).map((f) => ({ field: f, imported: snap[f] ?? null, current: m[f] ?? null }));
  }
  function meetingRow(m: MeetingRequest, d: MockDraft) {
    const p = programOf(m.program_id);
    const needsRoom = !REMOTE.has(m.mode);
    const pinned = new Set(d.pins.map((x) => x.event_id));
    return {
      id: m.id, kind: "COURSE" as const, section_id: m.section_id, course_code: m.course_code, course_name: m.course_name, section_label: m.section_label,
      program_id: m.program_id, program_name: m.program_name, faculty_id: p?.faculty_id ?? null, faculty_name: p?.faculty_name ?? null, is_evening: p?.is_evening ?? false,
      class_year: m.class_year, class_years: m.class_year ? [m.class_year] : [], day: m.day, days: m.day ? [m.day] : [], start_period: m.start_period, end_period: m.end_period,
      time_label: m.start_period && m.end_period ? `${PERIODS[m.start_period - 1].start}-${PERIODS[m.end_period - 1].end}` : null,
      weeks: m.weeks, enrolment: m.enrolment, mode: m.mode, needs_room: needsRoom, flexible_day: m.flexible_day,
      requested_room_ids: m.requested_room_ids, requested_room_codes: m.requested_room_ids.map(roomCode), requested_building: m.requested_building, requested_tags: m.requested_tags,
      definitive_room_ids: m.definitive_room_ids, definitive_room_codes: m.definitive_room_ids.map(roomCode), status: m.status, locked: m.status === "LOCKED",
      instructors: m.instructor ? [m.instructor] : [], included: !d.excluded_event_ids.includes(m.id), schedulable: needsRoom && m.start_period !== null && m.end_period !== null,
      pinned: pinned.has(m.id), changed_fields: changedFields(m), rule_ids: inPlay(d).filter((c) => select(c.kind, c.params, d).ids.has(m.id) && select(c.kind, c.params, d).targeted).map((c) => c.id),
    };
  }
  function examRow(e: ExamRequest, d: MockDraft) {
    const p = programOf(e.program_id);
    return {
      id: e.id, kind: "EXAM" as const, section_id: null, course_code: e.course_code, course_name: e.course_name, section_label: null, program_id: e.program_id, program_name: e.program_name,
      faculty_id: p?.faculty_id ?? null, faculty_name: p?.faculty_name ?? null, is_evening: p?.is_evening ?? false, class_year: e.class_year, class_years: e.class_year ? [e.class_year] : [],
      day: null, days: [], start_period: e.start_period, end_period: e.end_period, time_label: e.start_time && e.end_time ? `${e.start_time}-${e.end_time}` : null, date: e.date, weeks: [],
      enrolment: e.enrolment, mode: "F2F", needs_room: !e.no_exam, flexible_day: false, requested_room_ids: [], requested_room_codes: [], requested_building: null, requested_tags: e.requested_tags,
      definitive_room_ids: e.definitive_room_ids, definitive_room_codes: e.definitive_room_ids.map(roomCode), requested_room_count: e.requested_room_count, status: e.status, locked: e.status === "LOCKED",
      instructors: e.instructor_text ? [e.instructor_text] : [], included: !d.excluded_event_ids.includes(e.id), schedulable: !e.no_exam && e.date !== null && e.start_period !== null,
      pinned: d.pins.some((x) => x.event_id === e.id), changed_fields: [], rule_ids: [],
    };
  }
  function rows(d: MockDraft): Row[] {
    const h = host();
    if (d.kind === "EXAM") return h.exams.filter((e) => e.term_id === d.term_id).map((e) => examRow(e, d) as unknown as Row);
    return d.term_id === 1 ? h.meetings.map((m) => meetingRow(m, d)) : [];
  }

  /** Mirror of the solver selectors (event_ids, programs, cohorts, match, instructors). */
  function select(kind: string, params: Rec, d: MockDraft): { ids: Set<number>; targeted: boolean } {
    const h = host();
    const list = d.kind === "EXAM" ? h.exams.filter((e) => e.term_id === d.term_id).map((e) => ({ id: e.id, program: e.program_name, year: e.class_year, label: e.course_code, instructor: e.instructor_text ?? "", rooms: [] as number[], evening: programOf(e.program_id)?.is_evening ?? false })) : h.meetings.map((m) => ({ id: m.id, program: m.program_name, year: m.class_year, label: `${m.course_code} §${m.section_label}`, instructor: m.instructor ?? "", rooms: m.requested_room_ids, evening: programOf(m.program_id)?.is_evening ?? false }));
    if (kind === "room_closed") {
      const rid = Number(params.room_id);
      return { ids: new Set(list.filter((e) => e.rooms.includes(rid)).map((e) => e.id)), targeted: true };
    }
    if (kind === "evening_programs_in_buildings") return { ids: new Set(list.filter((e) => e.evening).map((e) => e.id)), targeted: false };
    const ids = new Set(asNums(params.event_ids));
    const progs = [...asStrs(params.program), ...asStrs(params.programs)];
    const cohorts = [...asStrs(params.cohort), ...asStrs(params.cohorts)];
    const match = asStrs(params.match).map((x) => x.toLocaleLowerCase("tr-TR"));
    const instr = [...asStrs(params.instructor), ...asStrs(params.instructors)];
    const targeted = ids.size > 0 || progs.length > 0 || cohorts.length > 0 || match.length > 0 || instr.length > 0;
    if (!targeted) return { ids: new Set(list.map((e) => e.id)), targeted: false };
    const hit = list.filter((e) => ids.has(e.id) || progs.includes(e.program) || cohorts.includes(`PROG:${e.program}:Y${e.year ?? 0}`) || instr.includes(e.instructor) || match.some((m) => e.label.toLocaleLowerCase("tr-TR").includes(m) || e.program.toLocaleLowerCase("tr-TR").includes(m)));
    return { ids: new Set(hit.map((e) => e.id)), targeted };
  }
  function affected(c: { kind: string; params: Rec }, d: MockDraft): number {
    const excluded = new Set(d.excluded_event_ids);
    return [...select(c.kind, c.params, d).ids].filter((i) => !excluded.has(i)).length;
  }

  function editMeeting(m: MeetingRequest, patch: Rec): { changed: string[]; warnings: string[]; errors: string[] } {
    const changed: string[] = [];
    const errors: string[] = [];
    const warnings: string[] = [];
    if (patch.start_period !== undefined && patch.end_period !== undefined && patch.start_period !== null && patch.end_period !== null && Number(patch.end_period) < Number(patch.start_period)) errors.push("end_period must be ≥ start_period");
    if (patch.enrolment !== undefined && patch.enrolment !== null && (Number(patch.enrolment) < 0 || Number(patch.enrolment) > 5000)) errors.push("enrolment must be within 0..5000");
    if (errors.length) return { changed, warnings, errors };
    snapshot(m);
    const rec = m as unknown as Rec;
    for (const [k, v] of Object.entries(patch)) {
      if (k === "locked") {
        m.status = v ? "LOCKED" : "PARSED";
        changed.push("status");
        continue;
      }
      if (!(MEETING_FIELDS as readonly string[]).includes(k)) continue;
      if (JSON.stringify(rec[k]) !== JSON.stringify(v)) {
        rec[k] = v;
        changed.push(k);
      }
    }
    if (patch.start_period !== undefined || patch.end_period !== undefined) {
      m.start_time = m.start_period ? PERIODS[m.start_period - 1].start : null;
      m.end_time = m.end_period ? PERIODS[m.end_period - 1].end : null;
    }
    const size = m.enrolment ?? 0;
    for (const rid of m.requested_room_ids) {
      const r = rooms.find((x) => x.id === rid);
      if (r && r.capacity < size) warnings.push(`${r.display_name} has ${r.capacity} seats, this class has ${size}`);
    }
    return { changed, warnings, errors };
  }

  /* --------------------------------------------------------------------- precheck */
  function estimate(nEvents: number, nWeeks: number, limit: number) {
    if (nEvents <= 0) return { low: 0, high: 1, words: t("birkaç saniye", "a few seconds") };
    const base = 16 * (nEvents / 300) ** 1.25 * Math.max(0.6, Math.min(1.2, (Math.max(nWeeks, 1) / 14) ** 0.25));
    const low = Math.max(1, Math.round(Math.min(base * 0.6, limit)));
    const high = Math.max(low + 1, Math.round(Math.min(base * 2, limit + Math.min(limit * 0.5, 120))));
    const mid = (low + high) / 2;
    if (high < 60) return { low, high, words: t("bir dakikadan az", "under a minute") };
    const m = Math.max(1, Math.round(mid / 60));
    return { low, high, words: m === 1 ? t("yaklaşık 1 dakika", "about a minute") : t(`yaklaşık ${m} dakika`, `about ${m} minutes`) };
  }

  function precheck(d: MockDraft) {
    const h = host();
    const items: PrecheckItemOut[] = [];
    const excluded = new Set(d.excluded_event_ids);
    const all = rows(d);
    const included = all.filter((r) => r.included && r.schedulable);
    if (d.kind === "COURSE") {
      const bme = h.meetings.find((m) => m.course_code === "BME 419");
      if (bme && !excluded.has(bme.id) && bme.day === 3 && bme.start_period === 7 && bme.requested_room_ids.length === 1 && bme.requested_room_ids[0] === 1) {
        const label = "BME 419 §1";
        items.push({
          id: `impossible:${bme.id}`, category: "impossible", severity: "error", group: "capacity",
          title: t(`${label} · Çar 13:30–15:50 · 102 öğrenci`, `${label} · Wed 13:30–15:50 · 102 students`),
          message: t("O saatte yeterince büyük derslik yok. Sadece A 204 (156 kişilik) yetiyor ve 7. haftada ETKİNLİK için ayrılmış.", "No room is big enough at that time. Only A 204 (156 seats) is big enough, and it is reserved for ETKİNLİK in week 7."),
          detail: "capacity + room_closed: A 204 blocked W7 Fri P10-P12; requested room_ids=[1]", event_ids: [bme.id], classes: [{ event_id: bme.id, label, request_ids: [bme.id] }],
          constraint_kinds: ["capacity", "room_pin"], constraint_ids: [],
          fixes: [
            { option: "rooms", label: t(`${label} için A 203, C 201 dersliklerini kullan`, `Use A 203, C 201 for ${label}`), action: { type: "meeting_update", payload: { request_ids: [bme.id], patch: { requested_room_ids: [2, 3] } } }, admin_only: false },
            { option: "move", label: t(`${label} dersini 16:00–18:00'e al`, `Move ${label} to 16:00–18:00`), action: { type: "meeting_update", payload: { request_ids: [bme.id], patch: { start_period: 10, end_period: 12 } } }, admin_only: false },
            { option: "exclude", label: t(`${label} bu planın dışında kalsın`, `Leave ${label} out of this plan`), action: { type: "exclude", payload: { request_ids: [bme.id] } }, admin_only: false },
          ],
        });
      }
      const noTime = all.filter((r) => r.included && r.needs_room && !r.schedulable);
      if (noTime.length) {
        items.push({
          id: "info:no_time", category: "info", severity: "info", group: "no_time",
          title: t(`${noTime.length} dersin günü/saati yok`, `${noTime.length} classes have no day/time`),
          message: t("Bu dersler plana alınamaz. Derslerde gün ve saat ekleyin veya plan dışında bırakın.", "These classes can't be planned. Add a day and time in Classes, or leave them out."),
          detail: "", event_ids: noTime.map((r) => r.id), classes: [], constraint_kinds: [], constraint_ids: [],
          fixes: [{ option: "exclude", label: t("Hepsini plan dışında bırak", "Leave them all out"), action: { type: "exclude", payload: { request_ids: noTime.map((r) => r.id) } }, admin_only: false }],
        });
      }
    }
    const play = inPlay(d);
    for (const c of play) {
      const s = select(c.kind, c.params, d);
      if (s.targeted && affected(c, d) === 0) {
        const name = c.nl_text ?? catalogTitle(c.kind).en;
        items.push({
          id: `no_match:${c.id}`, category: "no_match", severity: "warning", group: "rule_no_match",
          title: t(`"${name}" hiçbir dersle eşleşmiyor`, `"${name}" matches no classes`), message: t("Adı kontrol edin veya kuralı bu plan için kapatın.", "Check the name, or turn the rule off for this plan."),
          detail: `${c.kind} ${JSON.stringify(c.params)}`, event_ids: [], classes: [], constraint_kinds: [c.kind], constraint_ids: [c.id],
          fixes: [{ option: `off:${c.id}`, label: t("Bu planda kapat", "Turn it off for this plan"), action: { type: "rule_off", payload: { constraint_id: c.id } }, admin_only: false }],
        });
      }
    }
    const pins = play.filter((c) => c.kind === "room_pin");
    const forbids = play.filter((c) => c.kind === "room_forbid");
    for (const p of pins) for (const f of forbids) {
      const shared = asNums(p.params.room_ids).filter((r) => asNums(f.params.room_ids).includes(r));
      const a = select(p.kind, p.params, d).ids;
      const both = [...select(f.kind, f.params, d).ids].filter((i) => a.has(i));
      if (!shared.length || !both.length) continue;
      const hard = effHard(d, p) && effHard(d, f);
      items.push({
        id: `clash:${p.id}:${f.id}`, category: "clash", severity: hard ? "error" : "warning", group: "rule_conflict",
        title: t("Bu iki kural aynı anda doğru olamaz", "These two rules can't both be true"),
        message: t(`"${p.nl_text ?? "#" + p.id}" ve "${f.nl_text ?? "#" + f.id}" (${roomCode(shared[0])})`, `"${p.nl_text ?? "#" + p.id}" and "${f.nl_text ?? "#" + f.id}" (${roomCode(shared[0])})`),
        detail: `room_pin #${p.id} vs room_forbid #${f.id}`, event_ids: both, classes: [], constraint_kinds: ["room_pin", "room_forbid"], constraint_ids: [p.id, f.id],
        fixes: [
          { option: `soften:${f.id}`, label: t("İkincisi bu planda 'mümkünse' olsun", "Make the second one a Try-to in this plan"), action: { type: "rule_override", payload: { constraint_id: f.id, hardness: "soft" } }, admin_only: false },
          { option: `off:${f.id}`, label: t("İkincisini bu planda kapat", "Turn the second one off for this plan"), action: { type: "rule_off", payload: { constraint_id: f.id } }, admin_only: false },
        ],
      });
    }
    if (d.disabled_builtin_kinds.length) {
      items.push({ id: "info:builtins_off", category: "info", severity: "info", group: "other", title: t("Bazı temel kurallar kapalı", "Some built-in rules are off"), message: t(d.disabled_builtin_kinds.map((k) => BUILTIN_TEXT[k]?.tr ?? k).join(", "), d.disabled_builtin_kinds.map((k) => BUILTIN_TEXT[k]?.en ?? k).join(", ")), detail: "", event_ids: [], classes: [], constraint_kinds: d.disabled_builtin_kinds, constraint_ids: [], fixes: [] });
    }
    h.studio.lastPrecheck.set(`${d.term_id}:${d.kind}`, items);
    const errors = items.filter((i) => i.severity === "error").length;
    const warnings = items.filter((i) => i.severity === "warning").length;
    const readiness = errors ? "blocked" : warnings || items.some((i) => i.category !== "info") ? "needs_look" : "ready";
    const blocked = new Set(items.filter((i) => i.severity === "error").flatMap((i) => i.event_ids)).size;
    const order = { error: 0, warning: 1, info: 2 } as const;
    const groupMap = new Map<string, { group: string; title: { tr: string; en: string }; severity: PrecheckItemOut["severity"]; count: number }>();
    for (const it of items) {
      const g = groupMap.get(it.group) ?? { group: it.group, title: it.title, severity: it.severity, count: 0 };
      g.count += 1;
      groupMap.set(it.group, g);
    }
    const groups = [...groupMap.values()].sort((a, b) => order[a.severity] - order[b.severity] || b.count - a.count);
    const limit = Number(d.params.time_limit_s ?? h.settings.solver_default_time_limit ?? 120);
    return {
      draft_id: d.draft_id, version: d.version, readiness,
      counts: { impossible: items.filter((i) => i.category === "impossible").length, clash: items.filter((i) => i.category === "clash").length, no_match: items.filter((i) => i.category === "no_match").length, info: items.filter((i) => i.category === "info").length, errors, warnings, events: included.length, rooms: rooms.filter((r) => r.is_bookable).length, blocked_classes: blocked },
      groups, items, estimate_s: estimate(included.length, resolveWeeks(d).length, limit),
      summary: readiness === "ready" ? t("Hazır: imkânsız bir şey bulunmadı.", "Ready: nothing impossible found.") : readiness === "needs_look" ? t(`Bakılması gereken ${items.length} madde var; plan yine de oluşturulabilir.`, `${items.length} things to look at; the plan can still be generated.`) : t(`${blocked} ders kesin kurallarınızla yerleştirilemiyor.`, `${blocked} classes can't be placed under your Must-rules.`),
      duration_s: 0.04,
    };
  }

  function bump(d: MockDraft) {
    d.version += 1;
    d.updated_at = now();
  }

  function summary(d: MockDraft) {
    const h = host();
    const all = rows(d);
    const play = inPlay(d);
    const must = play.filter((c) => effHard(d, c)).length;
    const wk = resolveWeeks(d);
    const inCount = all.filter((r) => r.included && r.schedulable).length;
    const noTime = all.filter((r) => r.needs_room && !r.schedulable).length;
    const roomsN = rooms.filter((r) => r.is_bookable).length;
    const est = estimate(inCount, wk.length, Number(d.params.time_limit_s ?? h.settings.solver_default_time_limit ?? 120));
    const lastGood = [...h.runs].filter((r) => r.term_id === d.term_id && r.kind === d.kind && (r.status === "FEASIBLE" || r.status === "OPTIMAL")).sort((a, b) => b.id - a.id)[0];
    const holidays = new Set(termWeeks(d.term_id).filter((w) => w.kind === "HOLIDAY").map((w) => w.index));
    return {
      draft_id: d.draft_id, version: d.version, kind: d.kind,
      counts: { classes_total: all.length, classes_need_room: all.filter((r) => r.needs_room).length, classes_in: inCount, classes_out: d.excluded_event_ids.length, classes_without_time: noTime, events: inCount, rooms: roomsN, weeks: wk.length, pinned: d.pins.length, rules_must: must, rules_try: play.length - must, builtins_off: d.disabled_builtin_kinds.length },
      weeks: wk, holiday_weeks: wk.filter((w) => holidays.has(w)), readiness: "unknown", estimate_s: est,
      sentence: t(`${wk.length} hafta boyunca ${roomsN} derslikte ${inCount.toLocaleString("tr-TR")} ders planlıyorsunuz.`, `You are planning ${inCount.toLocaleString("en-US")} classes in ${roomsN} rooms for ${wk.length} weeks.`),
      human_summary: t(`SmartSched ${inCount} dersi ${roomsN} dersliğe yerleştirecek.`, `SmartSched will place ${inCount} classes into ${roomsN} rooms.`),
      warnings: noTime ? [{ code: "no_time", count: noTime, message: t(`${noTime} dersin günü/saati yok; plana alınamaz.`, `${noTime} classes have no day/time and cannot be planned.`) }] : [],
      last_good_run: lastGood ? { id: lastGood.id, status: lastGood.status, soft_score: lastGood.soft_score, hard_score: lastGood.hard_score, finished_at: lastGood.finished_at } : null,
      disabled_builtin_kinds: d.disabled_builtin_kinds,
    };
  }

  /* ---------------------------------------------------------------- uploads/mapping */
  function demoRows(): { row: number; course: string; section: string; program: string; enrolment: string; room: string; note: string }[] {
    const h = host();
    const ecz = h.meetings.find((m) => m.program_name === "Eczacılık" && m.day !== null) ?? h.meetings[0];
    const hem = h.meetings.find((m) => m.program_name === "Hemşirelik" && m.day !== null) ?? h.meetings[1];
    return [
      { row: 2, course: ecz.course_code, section: ecz.section_label, program: "Eczacılık", enrolment: "60", room: "A 206", note: "Her hafta aynı derslik" },
      { row: 3, course: hem.course_code, section: hem.section_label, program: "Hemşirelik", enrolment: "", room: "A 20", note: "" },
      { row: 4, course: "", section: "", program: "", enrolment: "", room: "", note: "Pazartesi sabah toplantı var, ders koymayın" },
    ];
  }
  function demoProposals(filename: string, sheet: string | null): { proposals: ProposedConstraint[]; edits: Rec[]; unparsed: Rec[] } {
    const h = host();
    const [r1, r2, r3] = demoRows();
    const ref = (row: number, excerpt: string) => ({ file: filename, row, ...(sheet ? { sheet } : {}), excerpt });
    const eczIds = h.meetings.filter((m) => m.course_code === r1.course).map((m) => m.id);
    const hemIds = h.meetings.filter((m) => m.course_code === r2.course).map((m) => m.id);
    const ex1 = `Ders Kodu=${r1.course} | Şube=${r1.section} | Program=${r1.program} | Öğrenci Sayısı=${r1.enrolment} | Derslik Talebi=${r1.room}`;
    const ex2 = `Ders Kodu=${r2.course} | Şube=${r2.section} | Program=${r2.program} | Derslik Talebi=${r2.room}`;
    const proposals: ProposedConstraint[] = [
      { kind: "room_preference", params: { room_ids: [9], event_ids: eczIds }, hardness: "soft", weight: 5, nl_text: ex1, rationale: "requested room", confidence: 0.92, title: null, status: "ok", issues: [], entities: [{ type: "room", text: "A 206", resolved_id: 9, resolved_label: "A 206", confidence: 1, candidates: [] }], source: "UPLOAD", source_ref: ref(r1.row, ex1) },
      { kind: "room_preference", params: { event_ids: hemIds }, hardness: "soft", weight: 5, nl_text: ex2, rationale: "requested room (ambiguous)", confidence: 0.55, title: null, status: "needs_review", issues: ["room 'A 20' is ambiguous"], entities: [{ type: "room", text: "A 20", resolved_id: null, resolved_label: null, confidence: 0.6, candidates: [{ id: 8, label: "A 205", score: 0.8 }, { id: 9, label: "A 206", score: 0.8 }] }], source: "UPLOAD", source_ref: ref(r2.row, ex2) },
    ];
    const ecz = h.meetings.find((m) => m.course_code === r1.course);
    const edits: Rec[] = ecz ? [{ op: "set_field", section_ids: [ecz.section_id], changes: { enrolment: 60 }, nl_text: ex1, rationale: "students column", confidence: 0.9, status: "ok", issues: [], entities: [], labels: [`${ecz.course_code} §${ecz.section_label}`], source: "UPLOAD", source_ref: ref(r1.row, ex1) }] : [];
    const unparsed: Rec[] = [{ text: r3.note, reason: "no course code or programme in this row", source_ref: ref(r3.row, `Not=${r3.note}`) }];
    return { proposals, edits, unparsed };
  }

  function createRule(termId: number, p: { kind: string; params: Rec; hardness: "hard" | "soft"; weight: number; nl_text?: string | null; source: string; source_ref?: Rec | null }): number {
    const h = host();
    const id = h.nextId();
    h.constraints.push({ id, term_id: termId, run_id: null, kind: p.kind, params: p.params, hardness: p.hardness, weight: p.weight, source: p.source as Constraint["source"], nl_text: p.nl_text ?? null, enabled: true, source_ref: p.source_ref ?? null });
    return id;
  }

  const sameRule = (a: { kind: string; params: Rec }, b: { kind: string; params: Rec }) => a.kind === b.kind && JSON.stringify(a.params) === JSON.stringify(b.params);

  /* ------------------------------------------------------------------------ routes */
  const NO_KEY = "No Anthropic API key is configured. An admin can add one under Settings > AI (Ayarlar > Yapay zekâ).";
  return [
    http.get(`${base}/studio/meta`, () => json(studioMeta())),

    http.post(`${base}/terms/:id/elicit`, async ({ request }) => {
      if (!host().settings.anthropic_api_key_masked) return err(409, NO_KEY);
      const body = (await request.json()) as { text: string };
      const res = mockElicit(body.text);
      return json({ proposals: res.proposals, section_edits: [], unparsed: res.unparsed, assistant_message: "", usage: { model: host().settings.anthropic_model, input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 } });
    }),
    http.post(`${base}/terms/:id/preferences/upload`, async ({ request }) => {
      const fd = await request.formData();
      const file = fileOf(fd.get("file"));
      const filename = file ? file.name : "upload.txt";
      if (!/\.(xlsx|xlsm|csv|docx|pdf|txt|md)$/i.test(filename)) return err(400, "unsupported file type; use .xlsx, .csv, .docx, .pdf, .txt or .md");
      if (!host().settings.anthropic_api_key_masked) return err(409, NO_KEY);
      const common = { assistant_message: "", usage: { model: host().settings.anthropic_model, input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 }, filename, chunks: 1, truncated: false, warnings: [] as string[] };
      if (/\.(xlsx|xlsm|csv)$/i.test(filename)) {
        const demo = demoProposals(filename, /\.csv$/i.test(filename) ? null : "Sayfa1");
        return json({ ...common, proposals: demo.proposals, section_edits: demo.edits, unparsed: demo.unparsed, file_kind: /\.csv$/i.test(filename) ? "csv" : "xlsx", units: 3, detected_columns: { course: "Ders Kodu", program: "Program", enrolment: "Öğrenci Sayısı", room: "Derslik Talebi", note: "Not" } });
      }
      const text = file && /\.(txt|md)$/i.test(filename) ? await file.text() : "Eczacılık pazartesi C blokta kalsın\nHer hafta aynı derslik";
      const res = mockElicit(text);
      res.proposals.forEach((p, i) => {
        p.source = "UPLOAD";
        p.source_ref = { file: filename, [/\.pdf$/i.test(filename) ? "page" : /\.docx$/i.test(filename) ? "paragraph" : "line"]: i + 1, excerpt: p.nl_text };
      });
      return json({ ...common, proposals: res.proposals, section_edits: [], unparsed: res.unparsed, file_kind: filename.split(".").pop()?.toLowerCase() ?? "txt", units: text.split("\n").length, detected_columns: {} });
    }),

    http.get(`${base}/terms/:id/studio`, ({ params, request }) => {
      const termId = Number(params.id);
      if (!terms.some((x) => x.id === termId)) return err(404, "term not found");
      return json(draftOut(draftFor(termId, kindOf(new URL(request.url)))));
    }),
    http.put(`${base}/terms/:id/studio`, async ({ params, request }) => {
      const body = (await request.json()) as Rec & { version?: number; kind?: "COURSE" | "EXAM" };
      const d = draftFor(Number(params.id), body.kind === "EXAM" ? "EXAM" : "COURSE");
      const expected = body.version ?? Number((request.headers.get("if-match") ?? "").replace(/"/g, ""));
      if (!expected) return err(428, "version (or If-Match) is required");
      if (expected !== d.version) return json({ detail: { message: "the draft changed since you loaded it", current: draftOut(d) } }, { status: 409 });
      const before = JSON.stringify(draftOut(d));
      const keys = ["horizon", "horizon_params", "excluded_event_ids", "pins", "disabled_builtin_kinds", "disabled_rule_ids", "rule_overrides", "preset_id", "last_step", "params"] as const;
      if (Array.isArray(body.disabled_builtin_kinds)) {
        const bad = (body.disabled_builtin_kinds as string[]).filter((k) => !BUILTINS[k]);
        if (bad.length) return err(422, `built-in rule(s) ${JSON.stringify(bad)} cannot be switched off`);
      }
      const rec = d as unknown as Rec;
      for (const k of keys) if (body[k] !== undefined && body[k] !== null) rec[k] = structuredClone(body[k]);
      if (JSON.stringify(draftOut(d)) !== before) bump(d);
      return json(draftOut(d));
    }),
    http.get(`${base}/terms/:id/studio/summary`, ({ params, request }) => json(summary(draftFor(Number(params.id), kindOf(new URL(request.url)))))),

    http.get(`${base}/terms/:id/studio/classes`, ({ params, request }) => {
      const url = new URL(request.url);
      const d = draftFor(Number(params.id), kindOf(url));
      let list = rows(d);
      const num = (k: string) => (url.searchParams.get(k) ? Number(url.searchParams.get(k)) : null);
      const fac = num("faculty_id");
      const prog = num("program_id");
      const day = num("day");
      const rule = num("rule_id");
      if (fac !== null) list = list.filter((r) => r.faculty_id === fac);
      if (prog !== null) list = list.filter((r) => r.program_id === prog);
      if (day !== null) list = list.filter((r) => r.day === day);
      if (rule !== null) list = list.filter((r) => r.rule_ids.includes(rule));
      if (url.searchParams.get("changed") === "true") list = list.filter((r) => r.changed_fields.length > 0);
      const all = rows(d);
      const counts = { total: all.length, in_plan: all.filter((r) => r.included && r.schedulable).length, left_out: all.filter((r) => !r.included).length, changed: all.filter((r) => r.changed_fields.length).length, pinned: all.filter((r) => r.pinned).length, locked: all.filter((r) => r.locked).length, needs_review: all.filter((r) => r.status === "NEEDS_REVIEW").length, needs_room: all.filter((r) => r.needs_room).length, no_day_time: all.filter((r) => r.needs_room && !r.schedulable).length, evening: all.filter((r) => r.is_evening).length };
      const limit = Number(url.searchParams.get("limit") ?? 200);
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return json({ items: list.slice(offset, offset + limit), total: list.length, limit, offset, counts });
    }),
    http.put(`${base}/studio/meetings/bulk`, async ({ request }) => {
      const h = host();
      const body = (await request.json()) as { ids?: number[]; patch?: Rec; items?: { id: number; patch: Rec }[]; dry_run?: boolean };
      const items = body.items?.length ? body.items : (body.ids ?? []).map((id) => ({ id, patch: body.patch ?? {} }));
      const d = draftFor(1, "COURSE");
      const results = items.map(({ id, patch }) => {
        const m = h.meetings.find((x) => x.id === id);
        if (!m) return { id, ok: false, errors: ["class not found"], changed: [], warnings: [] };
        if (body.dry_run) return { id, ok: true, errors: [], changed: Object.keys(patch), warnings: [] };
        const r = editMeeting(m, patch);
        return { id, ok: r.errors.length === 0, ...r };
      });
      const touched = h.meetings.filter((m) => items.some((i) => i.id === m.id));
      return json({ results, updated: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length, rows: touched.map((m) => meetingRow(m, d)) });
    }),
    http.post(`${base}/studio/meetings/revert`, async ({ request }) => {
      const h = host();
      const body = (await request.json()) as { ids: number[]; fields?: string[] | null };
      const d = draftFor(1, "COURSE");
      const out = body.ids.map((id) => h.meetings.find((m) => m.id === id)).filter((m): m is MeetingRequest => !!m).map((m) => {
        const snap = h.studio.snapshots.get(m.id);
        if (snap) for (const f of (body.fields ?? MEETING_FIELDS) as MeetingField[]) if (f in snap) (m as unknown as Rec)[f] = structuredClone(snap[f]);
        return meetingRow(m, d);
      });
      return json(out);
    }),
    http.post(`${base}/studio/meetings/:id/revert`, async ({ params, request }) => {
      const h = host();
      const m = h.meetings.find((x) => x.id === Number(params.id));
      if (!m) return err(404, "class not found");
      const body = (await request.json().catch(() => ({}))) as { fields?: string[] | null };
      const snap = h.studio.snapshots.get(m.id);
      if (snap) for (const f of (body.fields ?? MEETING_FIELDS) as MeetingField[]) if (f in snap) (m as unknown as Rec)[f] = structuredClone(snap[f]);
      if (m.start_period) m.start_time = PERIODS[m.start_period - 1].start;
      if (m.end_period) m.end_time = PERIODS[m.end_period - 1].end;
      return json(meetingRow(m, draftFor(1, "COURSE")));
    }),

    http.post(`${base}/terms/:id/studio/precheck`, ({ params, request }) => json(precheck(draftFor(Number(params.id), kindOf(new URL(request.url)))))),
    http.post(`${base}/terms/:id/studio/precheck/fix`, async ({ params, request }) => {
      const h = host();
      const d = draftFor(Number(params.id), kindOf(new URL(request.url)));
      const body = (await request.json()) as { item_id: string; option: string };
      const item = h.studio.lastPrecheck.get(`${d.term_id}:${d.kind}`)?.find((i) => i.id === body.item_id);
      if (!item) return err(409, "the pre-check changed; run it again");
      const fix = item.fixes.find((x) => x.option === body.option);
      if (!fix) return err(404, `option ${body.option} not found`);
      const p = fix.action.payload;
      switch (fix.action.type) {
        case "exclude":
          d.excluded_event_ids = [...new Set([...d.excluded_event_ids, ...asNums(p.request_ids)])];
          break;
        case "meeting_update":
          for (const id of asNums(p.request_ids)) {
            const m = h.meetings.find((x) => x.id === id);
            if (m) editMeeting(m, (p.patch ?? {}) as Rec);
          }
          break;
        case "rule_override":
          d.rule_overrides = { ...d.rule_overrides, [String(p.constraint_id)]: { hardness: p.hardness as "soft" } };
          break;
        case "rule_off":
          d.disabled_rule_ids = [...new Set([...d.disabled_rule_ids, Number(p.constraint_id)])];
          break;
        case "builtin_off":
          d.disabled_builtin_kinds = [...new Set([...d.disabled_builtin_kinds, String(p.kind)])];
          break;
      }
      bump(d);
      return json({ applied: { item_id: item.id, option: fix.option, type: fix.action.type, payload: p, label: fix.label }, draft: draftOut(d), precheck: precheck(d) });
    }),

    http.get(`${base}/terms/:id/studio/rules`, ({ params, request }) => {
      const d = draftFor(Number(params.id), kindOf(new URL(request.url)));
      const off = new Set(d.disabled_rule_ids);
      const list = termRules(d.term_id).map((c) => ({ id: c.id, kind: c.kind, params: c.params, hardness: c.hardness, weight: c.weight, source: c.source, source_ref: c.source_ref ?? null, nl_text: c.nl_text, enabled: c.enabled, in_play: c.enabled && !off.has(c.id), override: d.rule_overrides[String(c.id)] ?? null, title: catalogTitle(c.kind), affected_count: affected(c, d) }));
      const play = list.filter((r) => r.in_play);
      const hard = (r: (typeof list)[number]) => (r.override?.hardness ?? r.hardness) === "hard";
      return json({
        rules: list,
        builtins: Object.entries(BUILTINS).map(([kind, disableable]) => ({ kind, title: BUILTIN_TEXT[kind], enabled: !d.disabled_builtin_kinds.includes(kind), disableable })),
        counts: { must: play.filter(hard).length, try: play.filter((r) => !hard(r)).length, turned_off: list.length - play.length, builtin: 4, builtin_off: d.disabled_builtin_kinds.length, matches_none: play.filter((r) => r.affected_count === 0).length },
      });
    }),
    http.post(`${base}/studio/constraints/preview`, async ({ request }) => {
      const body = (await request.json()) as { term_id: number; kind: string; params: Rec; hardness: "hard" | "soft"; draft_kind?: "COURSE" | "EXAM"; sample?: number };
      const d = draftFor(body.term_id, body.draft_kind ?? "COURSE");
      const s = select(body.kind, body.params, d);
      const total = rows(d).filter((r) => r.included && r.schedulable).length;
      const n = affected(body, d);
      const pct = total ? Math.round((1000 * n) / total) / 10 : 0;
      const notes = [...(s.targeted && n === 0 ? ["matches_none"] : []), ...(body.hardness === "hard" && pct > 50 ? ["affects_most"] : [])];
      const issues = body.hardness === "soft" && !allowedHardness(body.kind).includes("soft") ? [`${body.kind} is always a Must`] : [];
      const sample = host().meetings.filter((m) => s.ids.has(m.id)).slice(0, body.sample ?? 8).map((m) => ({ event_id: m.id, label: `${m.course_code} §${m.section_label}`, request_ids: [m.id], size: m.enrolment }));
      return json({ affected_count: n, total, percent: pct, targeted: s.targeted, sample, issues, notes });
    }),
    http.post(`${base}/studio/constraints/copy`, async ({ request }) => {
      const h = host();
      const body = (await request.json()) as { to_term_id: number; from_run_id?: number | null; from_term_id?: number | null; constraint_ids?: number[] | null; dry_run?: boolean };
      if ((body.from_run_id == null) === (body.from_term_id == null)) return err(422, "give exactly one of from_run_id / from_term_id");
      const srcTerm = body.from_run_id != null ? h.runs.find((r) => r.id === body.from_run_id)?.term_id : body.from_term_id;
      if (srcTerm == null) return err(404, "run not found");
      let src = h.constraints.filter((c) => c.term_id === srcTerm && c.source !== "BUILTIN");
      src = body.constraint_ids ? src.filter((c) => body.constraint_ids?.includes(c.id)) : src.filter((c) => c.enabled);
      const target = termRules(body.to_term_id);
      const out = { will_match: [] as Rec[], needs_review: [] as Rec[], cannot_match: [] as Rec[] };
      const created: number[] = [];
      const d = draftFor(body.to_term_id, "COURSE");
      for (const c of src) {
        const reasons: string[] = [];
        let fatal = false;
        const params = { ...c.params };
        const gone = asNums(params.room_ids).filter((r) => !rooms.some((x) => x.id === r && x.is_bookable));
        if (gone.length) {
          reasons.push(`${gone.map(roomCode).join(", ")} doesn't exist in this term`);
          fatal = true;
        }
        if (asNums(params.event_ids).length && srcTerm !== body.to_term_id) {
          const mapped = asNums(params.event_ids).filter((id) => h.meetings.some((m) => m.id === id));
          if (!mapped.length) {
            reasons.push("none of its classes exist in this term");
            fatal = true;
          }
          params.event_ids = mapped;
        }
        if (target.some((x) => sameRule(x, { kind: c.kind, params }) && x.hardness === c.hardness)) {
          reasons.push("an identical rule already exists in this term");
          fatal = true;
        }
        const n = fatal ? 0 : affected({ kind: c.kind, params }, d);
        if (!fatal && select(c.kind, params, d).targeted && n === 0) reasons.push("matches no classes in this term");
        const bucket = fatal ? "cannot_match" : reasons.length ? "needs_review" : "will_match";
        const item: Rec = { source_id: c.id, kind: c.kind, hardness: c.hardness, weight: c.weight, nl_text: c.nl_text, params, affected_count: n, reasons, created_id: null };
        if (bucket !== "cannot_match" && !body.dry_run) {
          item.created_id = createRule(body.to_term_id, { kind: c.kind, params, hardness: c.hardness, weight: c.weight, nl_text: c.nl_text, source: c.source, source_ref: { copied_from: { term_id: srcTerm, run_id: body.from_run_id ?? null, constraint_id: c.id } } });
          created.push(item.created_id as number);
        }
        out[bucket].push(item);
      }
      return json({ ...out, created, dry_run: Boolean(body.dry_run) });
    }),
    http.post(`${base}/terms/:id/studio/proposals/accept`, async ({ params, request }) => {
      const h = host();
      const termId = Number(params.id);
      const body = (await request.json()) as { proposals?: ProposedConstraint[]; section_edits?: Rec[] };
      const created: number[] = [];
      const rejected: Rec[] = [];
      for (const p of body.proposals ?? []) {
        if (p.status === "rejected") {
          rejected.push({ kind: p.kind, reason: "rejected proposal" });
          continue;
        }
        const source = p.source_ref && (p.source === "AI" || p.source === "UPLOAD") && (p.source_ref as Rec).file ? "UPLOAD" : p.source || "AI";
        created.push(createRule(termId, { kind: p.kind, params: p.params, hardness: p.hardness, weight: p.weight, nl_text: p.nl_text, source, source_ref: (p.source_ref as Rec | null | undefined) ?? null }));
      }
      const applied: Rec[] = [];
      for (const e of body.section_edits ?? []) {
        const sections = asNums(e.section_ids);
        const changes = (e.changes ?? {}) as Rec;
        for (const m of h.meetings.filter((x) => sections.includes(x.section_id))) {
          editMeeting(m, Object.fromEntries(Object.entries(changes).filter(([, v]) => v !== null && v !== undefined)));
          applied.push({ meeting_id: m.id, changes });
        }
      }
      return json({ created, rejected, section_edits_applied: applied });
    }),
    http.post(`${base}/terms/:id/studio/preferences/mapping`, async ({ request }) => {
      const fd = await request.formData();
      const file = fileOf(fd.get("file"));
      const filename = file ? file.name : "upload.xlsx";
      if (!/\.(xlsx|xlsm|csv)$/i.test(filename)) return err(400, "column mapping reads .xlsx or .csv files");
      const mappingRaw = fd.get("mapping");
      const rowsDemo = demoRows();
      if (!mappingRaw) {
        const header = ["Ders Kodu", "Şube", "Program", "Öğrenci Sayısı", "Derslik Talebi", "Not"];
        const keys = ["course", "section", "program", "enrolment", "room", "note"] as const;
        return json({ mode: "columns", filename, sheets: ["Sayfa1"], sheet: "Sayfa1", header_row: 1, row_count: rowsDemo.length, columns: header.map((hd, i) => ({ index: i, header: hd, samples: rowsDemo.map((r) => r[keys[i]]).filter(Boolean).slice(0, 3) })), suggested_mapping: { columns: { course: 0, section: 1, program: 2, enrolment: 3, room: 4 }, room_rule: "prefer", hardness: "soft", weight: 5 }, roles: MAPPING_ROLES });
      }
      const mapping = JSON.parse(String(mappingRaw)) as { columns?: Record<string, number>; room_rule?: string; hardness?: "hard" | "soft"; weight?: number };
      if (!mapping.columns || (mapping.columns.course === undefined && mapping.columns.program === undefined)) return err(422, "map at least the course (or programme) column");
      const demo = demoProposals(filename, null);
      const kind = mapping.room_rule === "pin" ? "room_pin" : mapping.room_rule === "forbid" ? "room_forbid" : "room_preference";
      const hardness = mapping.hardness ?? (kind === "room_preference" ? "soft" : "hard");
      const proposals = mapping.columns.room === undefined ? [] : demo.proposals.map((p) => ({ ...p, kind, hardness, weight: mapping.weight ?? 5, rationale: "column mapping (no AI)" }));
      const edits = mapping.columns.enrolment === undefined ? [] : demo.edits;
      const ready = proposals.filter((p) => p.status === "ok").length + edits.length;
      return json({ mode: "proposals", filename, proposals, section_edits: edits, unparsed: demo.unparsed, counts: { ready, needs_look: proposals.length + edits.length - ready, couldnt_read: demo.unparsed.length } });
    }),
    http.post(`${base}/terms/:id/studio/generate`, async ({ params, request }) => {
      const h = host();
      const url = new URL(request.url);
      const d = draftFor(Number(params.id), kindOf(url));
      const body = (await request.json()) as { label?: string | null; params?: Rec; parent_run_id?: number | null; stability?: boolean | null };
      const term = terms.find((x) => x.id === d.term_id) ?? terms[0];
      const parent = body.parent_run_id ?? (d.params.parent_run_id as number | null | undefined) ?? null;
      const stability = body.stability ?? (d.params.stability as boolean | undefined) ?? true;
      if (parent !== null && !h.runs.some((r) => r.id === parent && r.term_id === term.id && r.kind === d.kind)) return err(422, "parent_run_id must be a run of the same term and kind");
      const events = rows(d).filter((r) => r.included && r.schedulable).length;
      const play = inPlay(d);
      const must = play.filter((c) => effHard(d, c)).length;
      const wk = resolveWeeks(d);
      const prompt = `Studio draft #${d.draft_id} v${d.version}: ${events} events (${events} classes), ${d.excluded_event_ids.length} left out, ${must} must / ${play.length - must} try rules, weeks ${wk.length ? `${wk[0]}-${wk[wk.length - 1]}` : "-"}`;
      const id = Math.max(...h.runs.map((r) => r.id)) + 1;
      const run: ScheduleRun = {
        id, term_id: term.id, term_code: term.code, kind: d.kind, horizon: d.horizon, horizon_params: { weeks: wk, dates: [] }, status: "QUEUED", progress: 0,
        params: { time_limit_s: Number(body.params?.time_limit_s ?? d.params.time_limit_s ?? 120), seed: Number(body.params?.seed ?? d.params.seed ?? 0), workers: 8, stability, weights: {} },
        objective_value: null, soft_score: null, hard_score: null, stats: {}, objective_breakdown: {}, diagnosis: [], parent_run_id: stability ? parent : null, prompt_text: prompt, created_at: now(), finished_at: null,
      };
      h.startRun(run);
      return json({ run_id: id, status: "QUEUED", draft_id: d.draft_id, draft_version: d.version, events, excluded: d.excluded_event_ids.length, prompt_text: prompt }, { status: 202 });
    }),

    /* -------------------------------------------------------------------- presets */
    http.get(`${base}/presets`, ({ request }) => {
      const kind = new URL(request.url).searchParams.get("kind");
      return json(host().studio.presets.filter((p) => !kind || p.kind === kind));
    }),
    http.post(`${base}/presets`, async ({ request }) => {
      const h = host();
      const body = (await request.json()) as { name: string; description?: string | null; kind?: string; from_term_id?: number | null; rules?: Rec[] };
      if (!body.name?.trim()) return err(422, [{ msg: "String should have at least 1 character", loc: ["body", "name"] }]);
      const d = body.from_term_id ? draftFor(body.from_term_id, body.kind === "EXAM" ? "EXAM" : "COURSE") : null;
      const rules = body.rules ?? (d ? inPlay(d).map((c) => ({ kind: c.kind, params: c.params, hardness: d.rule_overrides[String(c.id)]?.hardness ?? c.hardness, weight: d.rule_overrides[String(c.id)]?.weight ?? c.weight, enabled: true, nl_text: c.nl_text })) : []);
      const p: MockPreset = { id: h.nextId(), name: body.name.trim(), description: body.description ?? null, kind: body.kind ?? "COURSE", rules, scope: d ? { horizon: d.horizon, horizon_params: d.horizon_params } : {}, filters: {}, disabled_builtin_kinds: d?.disabled_builtin_kinds ?? [], created_by: 1, author: "Fatih Demir", created_at: now(), updated_at: now() };
      h.studio.presets.push(p);
      return json(p, { status: 201 });
    }),
    http.put(`${base}/presets/:id`, async ({ params, request }) => {
      const p = host().studio.presets.find((x) => x.id === Number(params.id));
      if (!p) return err(404, "preset not found");
      Object.assign(p, (await request.json()) as Partial<MockPreset>, { updated_at: now() });
      return json(p);
    }),
    http.delete(`${base}/presets/:id`, ({ params }) => {
      const h = host();
      const i = h.studio.presets.findIndex((x) => x.id === Number(params.id));
      if (i < 0) return err(404, "preset not found");
      h.studio.presets.splice(i, 1);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${base}/presets/:id/apply`, async ({ params, request }) => {
      const h = host();
      const p = h.studio.presets.find((x) => x.id === Number(params.id));
      if (!p) return err(404, "preset not found");
      const body = (await request.json()) as { term_id: number; dry_run?: boolean };
      const d = draftFor(body.term_id, p.kind === "EXAM" ? "EXAM" : "COURSE");
      const existing = termRules(body.term_id);
      const add: Rec[] = [];
      const change: Rec[] = [];
      for (const r of p.rules) {
        const same = existing.find((c) => sameRule(c, { kind: String(r.kind), params: (r.params ?? {}) as Rec }));
        if (!same) add.push(r);
        else if (same.hardness !== r.hardness || same.weight !== r.weight) change.push({ ...r, constraint_id: same.id, from: { hardness: same.hardness, weight: same.weight } });
      }
      const turnOff: Rec[] = inPlay(d).filter((c) => !p.rules.some((r) => r.kind === c.kind)).filter((c) => c.source === "ADMIN" && c.kind === "same_room_across_weeks").map((c) => ({ constraint_id: c.id, kind: c.kind, nl_text: c.nl_text }));
      const created: number[] = [];
      if (!body.dry_run) {
        for (const r of add) created.push(createRule(body.term_id, { kind: String(r.kind), params: (r.params ?? {}) as Rec, hardness: r.hardness as "hard" | "soft", weight: Number(r.weight ?? 5), nl_text: (r.nl_text as string | undefined) ?? null, source: "ADMIN" }));
        for (const c of change) d.rule_overrides = { ...d.rule_overrides, [String(c.constraint_id)]: { hardness: c.hardness as "hard" | "soft", weight: Number(c.weight) } };
        d.disabled_rule_ids = [...new Set([...d.disabled_rule_ids, ...turnOff.map((x) => Number(x.constraint_id))])];
        d.preset_id = p.id;
        bump(d);
      }
      return json({ add, change, turn_off: turnOff, unresolved: [], scope: p.scope, excluded_count: 0, dry_run: Boolean(body.dry_run), created, draft: body.dry_run ? null : draftOut(d) });
    }),
  ];
}

/** Mock of the AI readers (NL elicit + preference-file upload), resolving names like the backend. */
export function mockElicit(text: string): { proposals: ProposedConstraint[]; unparsed: Rec[] } {
  const proposals: ProposedConstraint[] = [];
  const unparsed: Rec[] = [];
  const lower = (s: string) => s.toLocaleLowerCase("tr-TR");
  const progMatch = (s: string) => programs.find((p) => lower(s).includes(lower(p.name.replace(/ \(İÖ\)$/, "")).split(" ")[0]) || (/pharmacy/i.test(s) && p.name === "Eczacılık") || (/nursing/i.test(s) && p.name === "Hemşirelik") || (/medicine/i.test(s) && p.name === "Tıp"));
  const base = { rationale: "", title: null, issues: [] as string[], entities: [] as Rec[], source: "AI", source_ref: null };
  for (const raw of text.split(/[.;\n]/).map((p) => p.trim()).filter(Boolean)) {
    const prog = progMatch(raw);
    if (/\btip\b|tıp derslik/i.test(raw) && /sadece|only/i.test(raw)) {
      proposals.push({ ...base, kind: "room_tags", params: { forbidden_tags: ["TIP"], programs: programs.filter((p) => p.name !== "Tıp").map((p) => p.name) }, hardness: "hard", weight: 5, nl_text: raw, confidence: 0.93, status: "ok" });
    } else if (/blok|block/i.test(raw)) {
      const letter = /\b([A-D])\s*(?:blok|block)/i.exec(raw)?.[1]?.toUpperCase() ?? "C";
      const day = /pazartesi|monday/i.test(raw) ? [1] : /salı|tuesday/i.test(raw) ? [2] : undefined;
      const params: Rec = { building: letter, ...(day ? { days: day } : {}), ...(prog ? { programs: [prog.name] } : {}) };
      proposals.push({ ...base, kind: /ikinci öğretim|evening|İÖ/i.test(raw) ? "evening_programs_in_buildings" : "building_preference", params: /ikinci öğretim|evening|İÖ/i.test(raw) ? { buildings: ["B", "C"] } : params, hardness: "soft", weight: 5, nl_text: raw, confidence: 0.86, status: "ok" });
    } else if (/17[:.]30|after|sonra/i.test(raw)) {
      const year = /\b([1-4])\.\s*sınıf|first-year|first year/i.exec(raw);
      const y = year ? Number(year[1] ?? 1) : null;
      proposals.push({ ...base, kind: "day_window", params: { latest: 11, ...(prog ? (y ? { cohorts: [`PROG:${prog.name}:Y${y}`] } : { programs: [prog.name] }) : {}) }, hardness: "hard", weight: 5, nl_text: raw, confidence: 0.88, status: "ok" });
    } else if (/aynı derslik|same room/i.test(raw)) {
      proposals.push({ ...base, kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 5, nl_text: raw, confidence: 0.9, status: "ok" });
    } else if (/\bA\s?20\b/i.test(raw)) {
      proposals.push({ ...base, kind: "room_preference", params: prog ? { programs: [prog.name] } : {}, hardness: "soft", weight: 5, nl_text: raw, confidence: 0.5, status: "needs_review", issues: ["room 'A 20' is ambiguous"], entities: [{ type: "room", text: "A 20", resolved_id: null, resolved_label: null, confidence: 0.6, candidates: [{ id: 8, label: "A 205", score: 0.8 }, { id: 9, label: "A 206", score: 0.8 }] }] });
    } else if (/hafta|week/i.test(raw)) {
      unparsed.push({ text: raw, reason: "this is a week pattern; edit the class's weeks in the class list", source_ref: null });
    } else {
      proposals.push({ ...base, kind: "room_preference", params: prog ? { programs: [prog.name] } : {}, hardness: "soft", weight: 5, nl_text: raw, confidence: 0.6, status: "needs_review", issues: ["no room named; pick one"] });
    }
  }
  return { proposals, unparsed };
}
