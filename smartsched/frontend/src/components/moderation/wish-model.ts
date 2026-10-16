/**
 * "Tercih ekle" as data (P19-T2; backend app/services/teacher_preferences.py): the form state of the sheet, the
 * request body it sends (also the body of the server's `?dry_run=1` preview), the client-side checks that mirror
 * the server's (the server stays the final word), the room picker's search and building groups, the fallback
 * sentence shown only while the server's preview loads, the error codes, and the coordinator's review order
 * (pending first, one card per submission). Pure functions, unit-tested.
 */
import type { Matching, PrefStatus } from "@/lib/api/moderation";
import type { TeacherPref, WishIn, WishKind, WishRoom } from "@/lib/api/teacher-preferences";
import { PERIODS_PER_DAY } from "@/lib/time";

export type Lang = "tr" | "en";

/* ------------------------------------------------------------------ the form */

export interface WishForm {
  kind: WishKind;
  requestIds: number[];
  roomIds: number[];
  /** rooms typed as the lists write them ("C 404"), for a user who cannot list the rooms; the server reads them */
  roomCodes: string[];
  buildings: string[];
  earliest: number | null;
  latest: number | null;
  days: number[];
  note: string;
}

export const MAX_ROOMS = 5;
export const NOTE_MAX = 500;
export const REASON_MIN = 3;
export const REASON_MAX = 1000;

export function emptyWish(requestIds: readonly number[] = []): WishForm {
  return { kind: "room_preference", requestIds: [...requestIds], roomIds: [], roomCodes: [], buildings: [], earliest: null, latest: null, days: [], note: "" };
}

/** the building of a room as the server reads it: the first letter of the code ("C 404" → "C") */
export function buildingOf(code: string | null | undefined): string {
  return (code ?? "").trim().slice(0, 1).toLocaleUpperCase("tr");
}

/** "c404", "C-404", "c\u00a0404" → "C 404"; null when it does not look like a room code (the server is the judge) */
export function roomCode(raw: string): string | null {
  const v = raw.normalize("NFKC").replace(/[\s\u00a0-]+/g, " ").trim().toLocaleUpperCase("tr");
  const m = /^([A-ZÇĞİÖŞÜ]{1,4}) ?(\d{1,4}[A-Z]?)$/.exec(v);
  return m ? `${m[1]} ${m[2]}` : null;
}

/** a building letter as typed ("c", "C Blok") → "C"; null otherwise */
export function buildingCode(raw: string): string | null {
  const v = raw.normalize("NFKC").trim().toLocaleUpperCase("tr").replace(/\s*-?\s*(BLOK|BLOĞU|BLOKU)$/, "");
  return /^[A-ZÇĞİÖŞÜ]$/.test(v) ? v : null;
}

/* ------------------------------------------------------------------ the room picker */

/** a room code for matching: "C 301", "c301", "C-301" → "C301" (the room list writes "C301", people write "C 301") */
export const roomKey = (code: string): string => code.normalize("NFKC").replace(/[\s\u00a0-]+/g, "").toLocaleUpperCase("tr");

/** the listed room a typed code names, if any */
export function listedRoom<R extends Pick<WishRoom, "code">>(rooms: readonly R[], typed: string | null): R | undefined {
  if (!typed) return undefined;
  const k = roomKey(typed);
  return rooms.find((r) => roomKey(r.code) === k);
}

const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i").replace(/[\s\u00a0-]+/g, "");

export interface RoomGroup<R> {
  building: string;
  name: string;
  rooms: R[];
}

/**
 * The picker's rooms matching the search (code, name, block name or a tag; spaces and accents ignored), grouped
 * by building A → Z, rooms in code order; at most `limit` rooms (the rest are counted).
 */
export function groupRooms<R extends WishRoom>(rooms: readonly R[], query: string, limit = 80): { groups: RoomGroup<R>[]; total: number; hidden: number } {
  const q = fold(query.trim());
  const hits = rooms
    .filter((r) => !q || fold([r.code, r.name ?? "", r.building_name ?? "", ...r.tags].join(" ")).includes(q))
    .sort((a, b) => (a.building ?? buildingOf(a.code)).localeCompare(b.building ?? buildingOf(b.code), "tr") || a.code.localeCompare(b.code, "tr", { numeric: true }));
  const shown = hits.slice(0, limit);
  const m = new Map<string, RoomGroup<R>>();
  for (const r of shown) {
    const b = r.building || buildingOf(r.code) || "?";
    const g = m.get(b) ?? { building: b, name: r.building_name || "", rooms: [] };
    g.rooms.push(r);
    m.set(b, g);
  }
  return { groups: [...m.values()], total: hits.length, hidden: hits.length - shown.length };
}

/** the buildings the rooms span, A → Z */
export function buildingsOf(rooms: readonly { code: string }[]): string[] {
  return [...new Set(rooms.map((r) => buildingOf(r.code)).filter((b) => /^[A-ZÇĞİÖŞÜ]$/.test(b)))].sort((a, b) => a.localeCompare(b, "tr"));
}

/** the selected classes whose day and time the department form fixed (a time wish cannot move them) */
export function fixedClasses(rows: readonly Pick<Matching, "request_id" | "requested" | "label">[], ids: readonly number[]): Pick<Matching, "request_id" | "label">[] {
  const want = new Set(ids);
  return rows.filter((m) => want.has(m.request_id) && m.requested.start_period !== null);
}

export type FormIssue = "noClasses" | "noRoom" | "tooManyRooms" | "noBuilding" | "noWindow" | "badWindow" | "noteLong";

/** what the sheet refuses before sending (the server checks the same and more) */
export function formIssues(f: WishForm): FormIssue[] {
  const out: FormIssue[] = [];
  if (!f.requestIds.length) out.push("noClasses");
  if (f.kind === "room_preference") {
    const rooms = f.roomIds.length + f.roomCodes.length;
    if (!rooms) out.push("noRoom");
    if (rooms > MAX_ROOMS) out.push("tooManyRooms");
  } else if (f.kind === "building_preference") {
    if (!f.buildings.length) out.push("noBuilding");
  } else if (f.earliest === null && f.latest === null) {
    out.push("noWindow");
  } else if ((f.earliest ?? 1) > (f.latest ?? PERIODS_PER_DAY)) {
    out.push("badWindow");
  }
  if (f.note.trim().length > NOTE_MAX) out.push("noteLong");
  return out;
}

/** the request body: only the fields of the chosen kind (the server refuses `hardness` / `weight` anyway) */
export function wishBody(f: WishForm): WishIn {
  const body: WishIn = { kind: f.kind, request_ids: [...new Set(f.requestIds)] };
  if (f.kind === "room_preference") {
    if (f.roomIds.length) body.room_ids = [...new Set(f.roomIds)];
    if (f.roomCodes.length) body.rooms = [...new Set(f.roomCodes)];
  }
  else if (f.kind === "building_preference") body.buildings = [...new Set(f.buildings)];
  else {
    if (f.earliest !== null) body.earliest = f.earliest;
    if (f.latest !== null) body.latest = f.latest;
    if (f.days.length) body.days = [...new Set(f.days)].sort((a, b) => a - b);
  }
  const note = f.note.trim();
  if (note) body.note = note;
  return body;
}

/** the body the server previews (`?dry_run=1`): only a form the sheet would send, with at least one class */
export function previewBody(f: WishForm): WishIn | null {
  return formIssues(f).length ? null : wishBody(f);
}

/**
 * The fallback of the server's sentence (`teacher_preferences._texts`): "PSY 277 §1: oda tercihi C 404", shown only
 * while the `?dry_run=1` preview is on its way; the preview's `items[].text` replaces it.
 */
export function wishSentence(f: WishForm, labels: readonly string[], roomNames: readonly string[], lang: Lang): string {
  const what = labels.slice(0, 3).join(", ") + (labels.length > 3 ? " …" : "");
  if (f.kind === "room_preference") {
    const names = roomNames.join(", ") || "…";
    return lang === "tr" ? `${what}: oda tercihi ${names}` : `${what}: room preference ${names}`;
  }
  if (f.kind === "building_preference") {
    const names = f.buildings.join(", ") || "…";
    return lang === "tr" ? `${what}: ${names} blok tercihi` : `${what}: building ${names} preferred`;
  }
  const span = `P${f.earliest ?? 1}–P${f.latest ?? PERIODS_PER_DAY}`;
  return lang === "tr" ? `${what}: ders saatleri ${span} arasında` : `${what}: classes within ${span}`;
}

/* ------------------------------------------------------------------ class labels */

/** "FZT 3002 §" (a section without a label) → "FZT 3002" (T-R1-16, R1-S-32) */
export function classLabel(label: string): string {
  return label.replace(/\s*§\s*$/, "");
}

/** one order for every list of a wish's classes, each once, Turkish collation (the server's sentences agree) */
export function classOrder(labels: Iterable<string>): string[] {
  return [...new Set(labels)].sort((a, b) => a.localeCompare(b, "tr"));
}

/* ------------------------------------------------------------------ errors */

/** the server's refusal codes the sheet and the review explain in their own words (messages moderation.wish.err.*) */
export const KNOWN_ERRORS = [
  "not_linked",
  "not_yours",
  "hard",
  "weight",
  "kind",
  "no_classes",
  "not_found",
  "too_many",
  "several_terms",
  "fixed_by_department",
  "already_requested",
  "unknown_room",
  "no_room",
  "too_many_rooms",
  "room_closed",
  "unknown_building",
  "no_building",
  "time",
  "window",
  "days",
  "note",
  "invalid_rule",
  "too_many_pending",
  "duplicate_pending",
  "decided",
  "reason_required",
  "decision",
] as const;
export type KnownError = (typeof KNOWN_ERRORS)[number];
export const isKnownError = (code: string): code is KnownError => (KNOWN_ERRORS as readonly string[]).includes(code);

/* ------------------------------------------------------------------ the academician's list */

const STATUS_ORDER: Record<PrefStatus, number> = { pending: 0, rejected: 1, accepted: 2 };

/** one card per submission (a wish over classes with different department asks is stored as several rules) */
export interface WishGroup {
  key: string;
  status: PrefStatus;
  items: TeacherPref[];
  labels: string[];
  requestIds: number[];
  submittedAt: string | null;
}

export function groupWishes(items: readonly TeacherPref[]): WishGroup[] {
  const map = new Map<string, TeacherPref[]>();
  for (const it of items) {
    const key = it.submission ?? `#${it.id}`;
    map.set(key, [...(map.get(key) ?? []), it]);
  }
  const out: WishGroup[] = [...map.entries()].map(([key, rows]) => {
    const pending = rows.some((r) => r.status === "pending");
    const status: PrefStatus = pending ? "pending" : rows.every((r) => r.status === "accepted") ? "accepted" : "rejected";
    return {
      key,
      status,
      items: [...rows].sort((a, b) => a.id - b.id),
      labels: classOrder(rows.flatMap((r) => r.labels.map(classLabel))),
      requestIds: [...new Set(rows.flatMap((r) => r.request_ids))],
      submittedAt: rows.map((r) => r.submitted_at).filter((x): x is string => !!x).sort()[0] ?? null,
    };
  });
  // pending first (what needs a look), then rejected (the academician wants the reason), then accepted; newest first
  return out.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || (b.submittedAt ?? "").localeCompare(a.submittedAt ?? "") || b.items[0]!.id - a.items[0]!.id);
}

/** the coordinator's filter over the review list */
export type ReviewFilter = "pending" | "accepted" | "rejected" | "all";
export function filterGroups(groups: readonly WishGroup[], f: ReviewFilter, q: string): WishGroup[] {
  const needle = q.trim().toLocaleLowerCase("tr");
  return groups.filter((g) => {
    if (f !== "all" && g.status !== f) return false;
    if (!needle) return true;
    const hay = [...g.labels, g.items[0]?.instructor?.name ?? "", g.items[0]?.text.tr ?? "", g.items[0]?.text.en ?? ""].join(" ").toLocaleLowerCase("tr");
    return hay.includes(needle);
  });
}

/** "bölüm odasından sonra": what the department asked first, as the rule lists it */
export function departmentAsk(p: Pick<TeacherPref, "kind" | "department">): string[] {
  if (p.kind === "room_preference") return p.department.rooms ?? [];
  if (p.kind === "building_preference") return p.department.buildings ?? [];
  return [];
}

/** the reason codes a coordinator may attach to a rejection (stored as `reason_code`, ≤ 32 chars) */
export const REJECT_CODES = ["room_unavailable", "conflicts_department", "capacity", "planning_policy", "other"] as const;
export type RejectCode = (typeof REJECT_CODES)[number];
export const isRejectCode = (v: string | null | undefined): v is RejectCode => !!v && (REJECT_CODES as readonly string[]).includes(v);
