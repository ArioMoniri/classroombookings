"use client";
/**
 * CRBS-parity API (classroombookings feature set): bookings, booking admin, rooms admin, roles, users,
 * departments, holidays, organisation settings, setup and password reset.
 *
 * Shapes follow the FastAPI routers `app/api/v1/{bookings,booking_admin,room_admin,roles,users,departments,
 * holidays,org,auth}.py` and `app/schemas/crbs.py` (docs/CRBS_PARITY.md §4). Every request is `silent`: the
 * global toast would show "409 Conflict" for the structured booking errors (`detail: {code, message, …}`),
 * so callers translate them with `crbsError()` + `components/bookings/booking-errors.ts`.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request, type Query } from "./client";

/* ------------------------------------------------------------------------------------------ errors */

export const Held = z.object({
  kind: z.enum(["timetable", "block", "booking"]),
  room_id: z.number(),
  date: z.string(),
  start_period: z.number(),
  end_period: z.number(),
  label: z.string().nullish(),
  id: z.number(),
  run_id: z.number().nullish(),
  series_id: z.number().nullish(),
});
export type Held = z.infer<typeof Held>;

export interface CrbsError {
  status: number;
  /** stable machine reason from `BookingError.code` (`conflict`, `holiday`, `max_active_bookings`, …) */
  code: string | null;
  /** the backend's English message (fallback only; the UI translates by code) */
  message: string;
  conflict: Held | null;
  data: Record<string, unknown>;
}

/** Normalise any thrown value into the backend's `{detail: {code, message, …}}` contract. */
export function crbsError(err: unknown): CrbsError {
  if (!(err instanceof HttpError)) {
    return { status: 0, code: null, message: err instanceof Error ? err.message : String(err), conflict: null, data: {} };
  }
  let detail: unknown = err.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "detail" in detail) detail = (detail as { detail: unknown }).detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    const held = Held.safeParse(d.conflict);
    return {
      status: err.status,
      code: typeof d.code === "string" ? d.code : null,
      message: typeof d.message === "string" ? d.message : err.message,
      conflict: held.success ? held.data : null,
      data: d,
    };
  }
  if (Array.isArray(detail)) {
    const msg = detail.map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : String(x))).join("; ");
    return { status: err.status, code: "validation", message: msg || err.message, conflict: null, data: {} };
  }
  return { status: err.status, code: err.status === 503 ? "maintenance" : null, message: typeof detail === "string" ? detail : err.message, conflict: null, data: {} };
}

/* ------------------------------------------------------------------------------------- shared bits */

const Limits = z.object({
  max_active_bookings: z.number().nullish(),
  range_min: z.number().nullish(),
  range_max: z.number().nullish(),
  recur_max_instances: z.number().nullish(),
});
export type Limits = z.infer<typeof Limits>;

export const BookingOut = z.object({
  id: z.number(),
  type: z.enum(["single", "recurring"]),
  series_id: z.number().nullish(),
  term_id: z.number().nullish(),
  status: z.string(),
  date: z.string(),
  weekday: z.number(),
  period_id: z.number(),
  period_name: z.string().nullish(),
  time_start: z.string().nullish(),
  time_end: z.string().nullish(),
  start_period: z.number(),
  end_period: z.number(),
  room_id: z.number(),
  room_name: z.string(),
  user_id: z.number().nullish(),
  user_name: z.string().nullish(),
  user_hidden: z.boolean().default(false),
  department_id: z.number().nullish(),
  department_name: z.string().nullish(),
  notes: z.string().nullish(),
  notes_hidden: z.boolean().default(false),
  is_owner: z.boolean().default(false),
  cancel_reason: z.string().nullish(),
  cancelled_at: z.string().nullish(),
  created_at: z.string().nullish(),
});
export type BookingOut = z.infer<typeof BookingOut>;

const EditFeatures = z.object({
  date: z.boolean(),
  period: z.boolean(),
  room: z.boolean(),
  view_notes: z.boolean(),
  edit_notes: z.boolean(),
  department: z.boolean(),
  view_user: z.boolean(),
  edit_user: z.boolean(),
});
export type EditFeatures = z.infer<typeof EditFeatures>;
export type Scope = "one" | "future" | "all";

export const RoomInfo = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  capacity: z.number().nullish(),
  tags: z.array(z.string()).default([]),
  room_group_id: z.number().nullish(),
  group: z.string().nullish(),
  location: z.string().nullish(),
  owner_user_id: z.number().nullish(),
  owner: z.string().nullish(),
  notes: z.string().nullish(),
  icon: z.string().nullish(),
  photo_url: z.string().nullish(),
  fields: z.array(z.object({ field_id: z.number(), name: z.string(), type: z.string(), value: z.unknown() })).default([]),
});
export type RoomInfo = z.infer<typeof RoomInfo>;

export const BookingDetail = BookingOut.extend({
  can_edit: z.boolean().default(false),
  can_cancel: z.boolean().default(false),
  edit_features: z.object({ one: EditFeatures, future: EditFeatures, all: EditFeatures }),
  series: z.object({ id: z.number(), weekday: z.number(), timetable_week_id: z.number().nullish(), status: z.string() }).nullish(),
  room: RoomInfo.nullish(),
});
export type BookingDetail = z.infer<typeof BookingDetail>;

/* ------------------------------------------------------------------------------- context and grid */

export const BookingContext = z.object({
  sessions: z.array(
    z.object({ id: z.number(), code: z.string(), name: z.string(), start: z.string(), end: z.string(), is_current: z.boolean(), is_selectable: z.boolean() }),
  ),
  current_term_id: z.number().nullish(),
  room_groups: z.array(z.object({ id: z.number(), name: z.string(), description: z.string().nullish() })),
  display: z.object({ type: z.enum(["day", "room"]), columns: z.enum(["periods", "rooms", "days"]), use_room_groups: z.boolean() }),
  date_patterns: z.object({ pattern_long: z.string().nullish(), pattern_weekday: z.string().nullish(), pattern_time: z.string().nullish() }),
  permissions: z.array(z.string()),
  limits: Limits,
  active_bookings: z.number(),
  remaining_bookings: z.number().nullish(),
});
export type BookingContext = z.infer<typeof BookingContext>;

export const DateInfo = z.object({
  date: z.string(),
  weekday: z.number(),
  term_week: z.number().nullish(),
  timetable_week_id: z.number().nullish(),
  holiday: z.string().nullish(),
  open: z.boolean(),
  reason: z.string().nullish(),
});
export type DateInfo = z.infer<typeof DateInfo>;

export const TimetableWeek = z.object({ id: z.number(), name: z.string(), bgcol: z.string(), fgcol: z.string(), icon: z.string().nullish() });
export type TimetableWeek = z.infer<typeof TimetableWeek>;

export const DatesOut = z.object({ term_id: z.number(), today: z.string(), weeks: z.array(TimetableWeek), dates: z.array(DateInfo) });
export type DatesOut = z.infer<typeof DatesOut>;

export const SlotStatus = z.enum(["available", "booked", "timetable", "unavailable"]);
export type SlotStatus = z.infer<typeof SlotStatus>;

export const GridSlot = z.object({
  date: z.string(),
  period_id: z.number(),
  room_id: z.number(),
  status: SlotStatus,
  reason: z.string().nullish(),
  label: z.string().nullish(),
  allow_single: z.boolean().optional(),
  allow_recur: z.boolean().optional(),
  booking: BookingOut.optional(),
});
export type GridSlot = z.infer<typeof GridSlot>;

export const GridPeriod = z.object({
  id: z.number(),
  name: z.string(),
  time_start: z.string(),
  time_end: z.string(),
  start_period: z.number(),
  end_period: z.number(),
  days: z.array(z.number()).nullish(),
});
export type GridPeriod = z.infer<typeof GridPeriod>;

export const GridRoom = z.object({ id: z.number(), name: z.string(), code: z.string(), room_group_id: z.number().nullish(), capacity: z.number().nullish() });
export type GridRoom = z.infer<typeof GridRoom>;

export const Grid = z.object({
  display: z.enum(["day", "room"]),
  term: z.object({ id: z.number(), code: z.string(), name: z.string(), start: z.string(), end: z.string() }),
  date: z.string(),
  room_group_id: z.number().nullish(),
  schedule: z.object({ id: z.number(), name: z.string() }).nullish(),
  dates: z.array(DateInfo),
  periods: z.array(GridPeriod),
  rooms: z.array(GridRoom),
  slots: z.array(GridSlot),
  nav: z.object({ prev: z.string().nullish(), next: z.string().nullish() }),
  limits: Limits,
  remaining_bookings: z.number().nullish(),
  problems: z.array(z.string()).default([]),
});
export type Grid = z.infer<typeof Grid>;

export interface GridQuery {
  display?: "day" | "room";
  date?: string;
  term_id?: number;
  room_group_id?: number;
  room_id?: number;
}

/* --------------------------------------------------------------------------------------- creating */

export interface SingleBookingIn {
  room_id: number;
  date: string;
  period_id: number;
  notes?: string | null;
  user_id?: number | null;
  department_id?: number | null;
  term_id?: number | null;
}

export type InstanceAction = "book" | "do_not_book" | "replace";

export const RecurInstance = z.object({
  date: z.string(),
  term_week: z.number().nullish(),
  status: z.string(),
  held: Held.optional(),
  booking: BookingOut.optional(),
  actions: z.array(z.enum(["book", "do_not_book", "replace"])),
});
export type RecurInstance = z.infer<typeof RecurInstance>;

export const RecurPlan = z.object({
  term_id: z.number(),
  room_id: z.number(),
  period_id: z.number(),
  weekday: z.number(),
  timetable_week_id: z.number().nullish(),
  instances: z.array(RecurInstance),
  bookable_count: z.number(),
  max_instances: z.number().nullish(),
  exceeds_by: z.number().default(0),
});
export type RecurPlan = z.infer<typeof RecurPlan>;

export interface RecurringIn {
  room_id: number;
  period_id: number;
  date: string;
  start?: string | "session" | null;
  end?: string | "session" | null;
  notes?: string | null;
  user_id?: number | null;
  department_id?: number | null;
  term_id?: number | null;
  instances?: { date: string; action: InstanceAction }[];
}

export const RecurCreated = z.object({
  series_id: z.number(),
  created: z.array(BookingOut),
  skipped: z.array(z.object({ date: z.string(), reason: z.string(), status: z.string().nullish() })),
});
export type RecurCreated = z.infer<typeof RecurCreated>;

export const SelectionSlot = z.object({
  mbs_id: z.number(),
  date: z.string(),
  period_id: z.number(),
  period_name: z.string().nullish(),
  room_id: z.number(),
  room_name: z.string(),
  single: z.boolean(),
  recur: z.boolean(),
  status: z.string(),
  held: Held.nullish(),
  recurring_dates: z.array(z.string()).default([]),
});
export type SelectionSlot = z.infer<typeof SelectionSlot>;

export const Selection = z.object({
  id: z.number(),
  term_id: z.number(),
  timetable_week_id: z.number().nullish(),
  can_book_single: z.boolean(),
  can_book_recur: z.boolean(),
  remaining_bookings: z.number().nullish(),
  slots: z.array(SelectionSlot),
});
export type Selection = z.infer<typeof Selection>;

export interface MultiSlotChoice {
  mbs_id: number;
  create?: boolean;
  notes?: string | null;
  user_id?: number | null;
  department_id?: number | null;
  recurring_start?: string | null;
  recurring_end?: string | null;
}

export const MultiProblem = z.object({ mbs_id: z.number(), code: z.string(), message: z.string(), conflict: Held.optional() });
export const MultiDryRun = z.object({ dry_run: z.literal(true), problems: z.array(MultiProblem).default([]), would_create: z.number().default(0) });
export const MultiCreated = z.object({ created: z.array(BookingOut), skipped: z.array(z.unknown()).default([]) });
export type MultiDryRun = z.infer<typeof MultiDryRun>;

/* ------------------------------------------------------------------------------------ lists, feeds */

export const Dashboard = z.object({
  user_bookings: z.array(BookingOut),
  room_bookings: z.array(BookingOut),
  owned_room_ids: z.array(z.number()),
  totals: z.object({ all: z.number(), session: z.number(), active: z.number() }),
  limits: Limits,
});
export type Dashboard = z.infer<typeof Dashboard>;

export const OwnedRoom = RoomInfo.extend({ upcoming: z.array(BookingOut).default([]) });
export type OwnedRoom = z.infer<typeof OwnedRoom>;

export const FeedToken = z.object({ token: z.string(), user_feed: z.string(), room_feed: z.string() });
export type FeedToken = z.infer<typeof FeedToken>;

export const CancelOut = z.object({ cancelled: z.array(z.number()) });
export const CancelManyOut = z.object({ cancelled: z.array(z.number()), skipped: z.array(z.object({ id: z.number(), reason: z.string() })).default([]) });
export type CancelManyOut = z.infer<typeof CancelManyOut>;

/* ------------------------------------------------------------------------------- roles and users */

export const PermissionItem = z.object({ id: z.number(), name: z.string(), description: z.string().nullish() });
export const PermissionCatalogue = z.object({
  system: z.record(z.string(), z.array(PermissionItem)).default({}),
  bookings: z.record(z.string(), z.array(PermissionItem)).default({}),
});
export type PermissionCatalogue = z.infer<typeof PermissionCatalogue>;

export const Role = z.object({
  id: z.number(),
  code: z.string().nullish(),
  name: z.string(),
  description: z.string().nullish(),
  max_active_bookings: z.number().nullish(),
  range_min: z.number().nullish(),
  range_max: z.number().nullish(),
  recur_max_instances: z.number().nullish(),
  permissions: z.array(z.string()),
  user_count: z.number().default(0),
  users: z.array(z.object({ id: z.number(), username: z.string().nullish(), email: z.string().nullish(), displayname: z.string().nullish() })).nullish(),
});
export type Role = z.infer<typeof Role>;
export interface RoleIn {
  name?: string;
  description?: string | null;
  max_active_bookings?: number | null;
  range_min?: number | null;
  range_max?: number | null;
  recur_max_instances?: number | null;
  permissions?: string[];
}

export const AdminUser = z.object({
  id: z.number(),
  email: z.string().nullish(),
  full_name: z.string().nullish(),
  role: z.string(),
  is_active: z.boolean(),
  created_at: z.string().nullish(),
  has_password: z.boolean().default(false),
  username: z.string().nullish(),
  firstname: z.string().nullish(),
  lastname: z.string().nullish(),
  displayname: z.string().nullish(),
  ext: z.string().nullish(),
  role_id: z.number().nullish(),
  role_name: z.string().nullish(),
  department_id: z.number().nullish(),
  department_name: z.string().nullish(),
  last_login_at: z.string().nullish(),
  force_password_reset: z.boolean().default(false),
  auth_source: z.string().default("local"),
});
export type AdminUser = z.infer<typeof AdminUser>;
export const UserPage = z.object({ total: z.number(), limit: z.number(), offset: z.number(), items: z.array(AdminUser) });
export type UserPage = z.infer<typeof UserPage>;

export interface UserIn {
  email?: string | null;
  username?: string | null;
  firstname?: string | null;
  lastname?: string | null;
  displayname?: string | null;
  ext?: string | null;
  role_id?: number | null;
  department_id?: number | null;
  force_password_reset?: boolean;
  password?: string | null;
  is_active?: boolean;
}

export type ConstraintType = "R" | "U" | "X";
const ConstraintValue = z.object({ type: z.enum(["R", "U", "X"]), value: z.number().nullish() });
export const Constraints = z.object({
  max_active_bookings: ConstraintValue,
  range_min: ConstraintValue,
  range_max: ConstraintValue,
  recur_max_instances: ConstraintValue,
});
export type Constraints = z.infer<typeof Constraints>;
export const LIMIT_KEYS = ["max_active_bookings", "range_min", "range_max", "recur_max_instances"] as const;
export type LimitKey = (typeof LIMIT_KEYS)[number];

export const ImportResult = z.object({
  created: z.number(),
  results: z.array(z.object({ line: z.number(), username: z.string().nullish(), status: z.string(), error: z.string().nullish() })),
});
export type ImportResult = z.infer<typeof ImportResult>;
export interface ImportDefaults {
  password?: string;
  role_id?: number | null;
  department_id?: number | null;
  enabled?: boolean;
  force_password_reset?: boolean;
}

export const ResetToken = z.object({ user_id: z.number(), expires_at: z.string().nullish(), emailed: z.boolean(), token: z.string().nullish() });
export type ResetToken = z.infer<typeof ResetToken>;

export const Department = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullish(),
  icon: z.string().nullish(),
  faculty_id: z.number().nullish(),
  is_evening: z.boolean().default(false),
  user_count: z.number().default(0),
});
export type Department = z.infer<typeof Department>;

export const Holiday = z.object({ id: z.number(), term_id: z.number(), name: z.string(), date_start: z.string(), date_end: z.string() });
export type Holiday = z.infer<typeof Holiday>;

/* ------------------------------------------------------------------------------------- room admin */

export const RoomGroup = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullish(),
  pos: z.number(),
  room_count: z.number(),
  room_ids: z.array(z.number()),
});
export type RoomGroup = z.infer<typeof RoomGroup>;

export const AdminRoom = z.object({
  id: z.number(),
  code: z.string(),
  display_name: z.string(),
  capacity: z.number(),
  is_bookable: z.boolean(),
  room_group_id: z.number().nullish(),
  room_group: z.string().nullish(),
  owner_user_id: z.number().nullish(),
  owner_name: z.string().nullish(),
  location: z.string().nullish(),
  icon: z.string().nullish(),
  notes: z.string().nullish(),
  photo_url: z.string().nullish(),
  pos: z.number(),
  fields: z.record(z.string(), z.unknown()).default({}),
});
export type AdminRoom = z.infer<typeof AdminRoom>;
export interface AdminRoomIn {
  room_group_id?: number | null;
  owner_user_id?: number | null;
  location?: string | null;
  icon?: string | null;
  notes?: string | null;
  is_bookable?: boolean;
  display_name?: string | null;
}

export const CustomField = z.object({
  id: z.number(),
  name: z.string(),
  type: z.enum(["TEXT", "CHECKBOX", "SELECT"]),
  options: z.array(z.object({ id: z.number(), value: z.string() })),
});
export type CustomField = z.infer<typeof CustomField>;
export interface CustomFieldIn {
  name: string;
  type: "TEXT" | "CHECKBOX" | "SELECT";
  options: string[];
}

export const Acl = z.object({
  id: z.number(),
  entity_type: z.enum(["room", "room_group"]),
  entity_id: z.number(),
  entity_label: z.string().nullish(),
  context_type: z.enum(["user", "role", "department"]),
  context_id: z.number(),
  context_label: z.string().nullish(),
  permissions: z.array(z.string()),
});
export type Acl = z.infer<typeof Acl>;
export interface AclIn {
  entity_type: "room" | "room_group";
  entity_id: number;
  context_type: "user" | "role" | "department";
  context_id: number;
  permissions: string[];
}

export const AccessCheck = z.object({
  user_id: z.number(),
  room_id: z.number(),
  role: z.string().nullish(),
  from_role: z.array(z.string()),
  from_acl: z.array(z.string()),
  effective: z.record(z.string(), z.record(z.string(), z.boolean())),
  room_bookable: z.boolean(),
});
export type AccessCheck = z.infer<typeof AccessCheck>;

/* ---------------------------------------------------------------------------------- booking admin */

export const Session = z.object({
  term_id: z.number(),
  code: z.string(),
  name: z.string(),
  kind: z.string(),
  date_start: z.string().nullish(),
  date_end: z.string().nullish(),
  is_current: z.boolean(),
  is_selectable: z.boolean(),
  default_schedule_id: z.number().nullish(),
  mapped_dates: z.number(),
  holidays: z.number(),
});
export type Session = z.infer<typeof Session>;

export const TermSchedule = z.object({ room_group_id: z.number(), room_group: z.string(), schedule_id: z.number().nullish() });
export type TermSchedule = z.infer<typeof TermSchedule>;

export const SessionDates = z.object({
  term_id: z.number(),
  start: z.string(),
  end: z.string(),
  dates: z.array(DateInfo.omit({ reason: true }).extend({ reason: z.string().nullish() })),
});
export type SessionDates = z.infer<typeof SessionDates>;

export const Period = z.object({
  id: z.number(),
  schedule_id: z.number(),
  name: z.string(),
  time_start: z.string(),
  time_end: z.string(),
  bookable: z.boolean(),
  days: z.array(z.number()),
  start_period: z.number(),
  end_period: z.number(),
});
export type Period = z.infer<typeof Period>;
export interface PeriodIn {
  name?: string;
  time_start?: string;
  time_end?: string;
  bookable?: boolean;
  days?: number[];
}

export const Schedule = z.object({ id: z.number(), name: z.string(), description: z.string().nullish(), type: z.string(), periods: z.array(Period) });
export type Schedule = z.infer<typeof Schedule>;

export const Outbox = z.object({
  id: z.number(),
  kind: z.string(),
  to_email: z.string().nullish(),
  user_id: z.number().nullish(),
  booking_id: z.number().nullish(),
  subject: z.string().nullish(),
  body: z.string().nullish(),
  status: z.string(),
  error: z.string().nullish(),
  attempts: z.number().default(0),
  created_at: z.string().nullish(),
  sent_at: z.string().nullish(),
});
export type Outbox = z.infer<typeof Outbox>;

/* ------------------------------------------------------------------------------------------- org */

export const OrgPublic = z.object({
  name: z.string().nullish(),
  website: z.string().nullish(),
  logo_url: z.string().nullish(),
  login_message: z.string().nullish(),
  maintenance_mode: z.boolean().default(false),
  maintenance_message: z.string().nullish(),
  ldap_enabled: z.boolean().default(false),
  setup_required: z.boolean().default(false),
  default_language: z.string().nullish(),
  languages: z.array(z.string()).nullish(),
});
export type OrgPublic = z.infer<typeof OrgPublic>;

export const SetupStatus = z.object({
  setup_required: z.boolean(),
  checks: z.object({
    organisation_name: z.boolean(),
    admin: z.boolean(),
    terms: z.number(),
    rooms: z.number(),
    bookable_rooms: z.number(),
    room_groups: z.number(),
    schedules: z.number(),
    timetable_weeks: z.number(),
    mapped_dates: z.number(),
    holidays: z.number(),
    departments: z.number(),
    roles: z.number(),
    smtp_configured: z.boolean(),
  }),
});
export type SetupStatus = z.infer<typeof SetupStatus>;
export interface SetupIn {
  org_name: string;
  timezone: string;
  admin_email: string;
  admin_username?: string | null;
  admin_password: string;
  admin_displayname?: string | null;
}

export const OrgSettings = z.object({
  name: z.string().nullish(),
  website: z.string().nullish(),
  logo_url: z.string().nullish(),
  displaytype: z.enum(["day", "room"]).default("day"),
  d_columns: z.enum(["periods", "rooms", "days"]).default("periods"),
  timezone: z.string().nullish(),
  login_message_enabled: z.boolean().default(false),
  login_message_text: z.string().nullish(),
  maintenance_mode: z.boolean().default(false),
  maintenance_mode_message: z.string().nullish(),
  use_room_groups: z.boolean().default(true),
  pattern_long: z.string().nullish(),
  pattern_weekday: z.string().nullish(),
  pattern_time: z.string().nullish(),
  default_language: z.string().nullish(),
  languages: z.array(z.string()).nullish(),
  bookings_show_name: z.boolean().default(false),
  max_active_bookings: z.number().nullish(),
  /** CRBS hides rooms without a room group from the grid; true shows them in an ungrouped tab */
  show_ungrouped_rooms: z.boolean().default(false),
});
export type OrgSettings = z.infer<typeof OrgSettings>;
export type OrgSettingsIn = Partial<Omit<OrgSettings, "logo_url">> & { max_active_bookings_unlimited?: boolean };

export const LdapSettings = z.object({
  enabled: z.boolean().default(false),
  create_users: z.boolean().default(false),
  server: z.string().nullish(),
  port: z.number().nullish(),
  version: z.number().nullish(),
  use_tls: z.boolean().default(false),
  ignore_cert: z.boolean().default(false),
  bind_dn_format: z.string().nullish(),
  base_dn: z.string().nullish(),
  search_filter: z.string().nullish(),
  attr_firstname: z.string().nullish(),
  attr_lastname: z.string().nullish(),
  attr_displayname: z.string().nullish(),
  attr_email: z.string().nullish(),
  default_role_id: z.number().nullish(),
  default_department_id: z.number().nullish(),
});
export type LdapSettings = z.infer<typeof LdapSettings>;
export const LdapTestOut = z.object({
  ok: z.boolean(),
  errors: z.array(z.string()).default([]),
  connection_error: z.boolean().nullish(),
  attributes: z.record(z.string(), z.unknown()).nullish(),
  mapped: z.record(z.string(), z.unknown()).nullish(),
});
export type LdapTestOut = z.infer<typeof LdapTestOut>;

export const SmtpSettings = z.object({
  host: z.string().nullish(),
  port: z.number().nullish(),
  security: z.enum(["starttls", "ssl", "none"]).nullish(),
  username: z.string().nullish(),
  password: z.string().nullish(),
  from_address: z.string().nullish(),
  from_name: z.string().nullish(),
  timeout_s: z.number().nullish(),
  configured: z.boolean().default(false),
});
export type SmtpSettings = z.infer<typeof SmtpSettings>;
export const SmtpTestOut = z.object({ status: z.string(), error: z.string().nullish(), outbox_id: z.number().nullish() });

export const Translation = z.object({ id: z.number(), language: z.string(), set: z.string(), key: z.string(), text: z.string() });
export type Translation = z.infer<typeof Translation>;

export const Changelog = z.object({
  entries: z.array(z.object({ version: z.string(), date: z.string().nullish(), sections: z.record(z.string(), z.array(z.string())) })),
  latest: z.string().nullish(),
  viewed_at: z.string().nullish(),
  unread: z.boolean(),
});
export type Changelog = z.infer<typeof Changelog>;

/* --------------------------------------------------------------------------------------- requests */

const s = { silent: true } as const;
const json = <T>(path: string, schema: z.ZodType<T>, query?: Query) => request(path, { ...s, query, schema });
const send = <T>(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown, schema?: z.ZodType<T>, query?: Query) =>
  request<T>(path, { ...s, method, body, schema, query });

export const crbs = {
  bookings: {
    context: () => json("/bookings/context", BookingContext),
    dates: (q: { term_id?: number; from?: string; to?: string }) => json("/bookings/dates", DatesOut, { ...q }),
    rooms: (roomGroupId?: number) => json("/bookings/rooms", z.array(RoomInfo), { room_group_id: roomGroupId }),
    room: (id: number) => json(`/bookings/rooms/${id}`, RoomInfo),
    grid: (q: GridQuery) => json("/bookings/grid", Grid, { ...q }),
    create: (body: SingleBookingIn) => send("POST", "/bookings", body, BookingOut),
    previewRecurring: (body: RecurringIn) => send("POST", "/bookings/recurring/preview", body, RecurPlan),
    createRecurring: (body: RecurringIn) => send("POST", "/bookings/recurring", body, RecurCreated),
    select: (slots: { date: string; period_id: number; room_id: number }[], termId?: number) =>
      send("POST", "/bookings/multi", { slots, term_id: termId ?? null }, Selection),
    selection: (id: number) => json(`/bookings/multi/${id}`, Selection),
    dropSelection: (id: number) => send("DELETE", `/bookings/multi/${id}`),
    multiDryRun: (id: number, type: "single" | "recurring", slots: MultiSlotChoice[]) =>
      send("POST", `/bookings/multi/${id}/create`, { type, slots, dry_run: true }, z.record(z.string(), z.unknown())),
    multiCreate: (id: number, type: "single" | "recurring", slots: MultiSlotChoice[]) =>
      send("POST", `/bookings/multi/${id}/create`, { type, slots, dry_run: false }, z.record(z.string(), z.unknown())),
    get: (id: number) => json(`/bookings/${id}`, BookingDetail),
    series: (id: number) => json(`/bookings/${id}/series`, z.array(BookingOut)),
    update: (id: number, scope: Scope, body: Partial<Pick<SingleBookingIn, "date" | "period_id" | "room_id" | "notes" | "user_id" | "department_id">>) =>
      send("PUT", `/bookings/${id}`, body, z.array(BookingOut), { scope }),
    cancel: (id: number, scope: Scope, reason: string | null) => send("POST", `/bookings/${id}/cancel`, { scope, reason }, CancelOut),
    cancelMany: (ids: number[], reason: string | null) => send("POST", "/bookings/cancel-multi", { booking_ids: ids, reason }, CancelManyOut),
    mine: (q: { from?: string; to?: string; status?: "BOOKED" | "CANCELLED" | "ALL" }) => json("/bookings/mine", z.array(BookingOut), { ...q }),
    dashboard: () => json("/bookings/dashboard", Dashboard),
    ownedRooms: () => json("/bookings/owned-rooms", z.array(OwnedRoom)),
    feedToken: () => send("POST", "/bookings/feed/token", undefined, FeedToken),
  },
  roles: {
    permissions: () => json("/permissions", PermissionCatalogue),
    list: () => json("/roles", z.array(Role)),
    get: (id: number) => json(`/roles/${id}`, Role),
    create: (body: RoleIn) => send("POST", "/roles", body, Role),
    update: (id: number, body: RoleIn) => send("PUT", `/roles/${id}`, body, Role),
    remove: (id: number) => send("DELETE", `/roles/${id}`),
  },
  users: {
    search: (q: { q?: string; role_id?: number; department_id?: number; enabled?: boolean; sort?: string; limit?: number; offset?: number }) =>
      json("/users/search", UserPage, { ...q }),
    list: () => json("/users", z.array(AdminUser)),
    get: (id: number) => json(`/users/${id}`, AdminUser),
    create: (body: UserIn) => send("POST", "/users", body, AdminUser),
    update: (id: number, body: UserIn) => send("PUT", `/users/${id}`, body, AdminUser),
    remove: (id: number) => send("DELETE", `/users/${id}`),
    constraints: (id: number) => json(`/users/${id}/constraints`, Constraints),
    putConstraints: (id: number, body: Partial<Constraints>) => send("PUT", `/users/${id}/constraints`, body, Constraints),
    resetToken: (id: number) => send("POST", `/users/${id}/reset-token`, undefined, ResetToken),
    import: (file: File, d: ImportDefaults) => {
      const fd = new FormData();
      fd.append("file", file);
      if (d.password) fd.append("password", d.password);
      if (d.role_id != null) fd.append("role_id", String(d.role_id));
      if (d.department_id != null) fd.append("department_id", String(d.department_id));
      fd.append("enabled", String(d.enabled ?? true));
      fd.append("force_password_reset", String(d.force_password_reset ?? false));
      return request("/users/import", { ...s, method: "POST", formData: fd, schema: ImportResult });
    },
  },
  departments: {
    list: (q?: string) => json("/departments", z.array(Department), { q }),
    create: (body: { name: string; description?: string | null; icon?: string | null }) => send("POST", "/departments", body, Department),
    update: (id: number, body: { name?: string; description?: string | null; icon?: string | null }) => send("PUT", `/departments/${id}`, body, Department),
    remove: (id: number) => send("DELETE", `/departments/${id}`),
  },
  holidays: {
    list: (termId?: number) => json("/holidays", z.array(Holiday), { term_id: termId }),
    create: (body: Omit<Holiday, "id">) => send("POST", "/holidays", body, Holiday),
    update: (id: number, body: Partial<Omit<Holiday, "id" | "term_id">>) => send("PUT", `/holidays/${id}`, body, Holiday),
    remove: (id: number) => send("DELETE", `/holidays/${id}`),
  },
  roomAdmin: {
    groups: () => json("/room-admin/groups", z.array(RoomGroup)),
    createGroup: (body: { name: string; description?: string | null; room_ids?: number[] }) => send("POST", "/room-admin/groups", body, RoomGroup),
    updateGroup: (id: number, body: { name?: string; description?: string | null; room_ids?: number[] }) => send("PUT", `/room-admin/groups/${id}`, body, RoomGroup),
    deleteGroup: (id: number) => send("DELETE", `/room-admin/groups/${id}`),
    orderGroups: (ids: number[]) => send("PUT", "/room-admin/groups/order", { ids }, z.array(RoomGroup)),
    groupsFromBuildings: () => send("POST", "/room-admin/groups/from-buildings", undefined, z.array(RoomGroup)),
    rooms: (roomGroupId?: number) => json("/room-admin/rooms", z.array(AdminRoom), { room_group_id: roomGroupId }),
    updateRoom: (id: number, body: AdminRoomIn) => send("PUT", `/room-admin/rooms/${id}`, body, AdminRoom),
    orderRooms: (ids: number[]) => send("PUT", "/room-admin/rooms/order", { ids }, z.array(AdminRoom)),
    uploadPhoto: (id: number, file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request(`/room-admin/rooms/${id}/photo`, { ...s, method: "POST", formData: fd, schema: AdminRoom });
    },
    deletePhoto: (id: number) => send("DELETE", `/room-admin/rooms/${id}/photo`, undefined, AdminRoom),
    fields: () => json("/room-admin/fields", z.array(CustomField)),
    createField: (body: CustomFieldIn) => send("POST", "/room-admin/fields", body, CustomField),
    updateField: (id: number, body: CustomFieldIn) => send("PUT", `/room-admin/fields/${id}`, body, CustomField),
    deleteField: (id: number) => send("DELETE", `/room-admin/fields/${id}`),
    roomFields: (id: number) => json(`/room-admin/rooms/${id}/fields`, z.record(z.string(), z.unknown())),
    putRoomFields: (id: number, body: Record<string, unknown>) => send("PUT", `/room-admin/rooms/${id}/fields`, body, z.record(z.string(), z.unknown())),
    acl: (q?: { entity_type?: string; entity_id?: number }) => json("/room-admin/acl", z.array(Acl), { ...q }),
    createAcl: (body: AclIn) => send("POST", "/room-admin/acl", body, Acl),
    updateAcl: (id: number, permissions: string[]) => send("PUT", `/room-admin/acl/${id}`, { permissions }, Acl),
    deleteAcl: (id: number) => send("DELETE", `/room-admin/acl/${id}`),
  },
  bookingAdmin: {
    sessions: () => json("/booking-admin/sessions", z.array(Session)),
    updateSession: (termId: number, body: { is_selectable?: boolean; default_schedule_id?: number | null }) =>
      send("PUT", `/booking-admin/sessions/${termId}`, body, Session),
    termSchedules: (termId: number) => json(`/booking-admin/sessions/${termId}/schedules`, z.array(TermSchedule)),
    putTermSchedules: (termId: number, body: { room_group_id: number; schedule_id: number }[]) =>
      send("PUT", `/booking-admin/sessions/${termId}/schedules`, body, z.array(TermSchedule)),
    dates: (termId: number) => json(`/booking-admin/sessions/${termId}/dates`, SessionDates),
    putDates: (termId: number, dates: Record<string, number | null>) => send("PUT", `/booking-admin/sessions/${termId}/dates`, { dates }, SessionDates),
    applyWeek: (termId: number, weekId: number | null) => send("POST", `/booking-admin/sessions/${termId}/apply-week`, { timetable_week_id: weekId }, SessionDates),
    schedules: () => json("/booking-admin/schedules", z.array(Schedule)),
    createSchedule: (body: { name: string; description?: string | null }) => send("POST", "/booking-admin/schedules", body, Schedule),
    updateSchedule: (id: number, body: { name?: string; description?: string | null }) => send("PUT", `/booking-admin/schedules/${id}`, body, Schedule),
    deleteSchedule: (id: number) => send("DELETE", `/booking-admin/schedules/${id}`),
    createPeriod: (scheduleId: number, body: PeriodIn) => send("POST", `/booking-admin/schedules/${scheduleId}/periods`, body, Period),
    periodsFromGrid: (scheduleId: number, days: number[]) =>
      send("POST", `/booking-admin/schedules/${scheduleId}/periods/from-grid`, undefined, Schedule, { days: days.join(",") }),
    updatePeriod: (id: number, body: PeriodIn) => send("PUT", `/booking-admin/periods/${id}`, body, Period),
    deletePeriod: (id: number) => send("DELETE", `/booking-admin/periods/${id}`),
    weeks: () => json("/booking-admin/weeks", z.array(TimetableWeek)),
    createWeek: (body: { name: string; bgcol: string }) => send("POST", "/booking-admin/weeks", body, TimetableWeek),
    updateWeek: (id: number, body: { name?: string; bgcol?: string }) => send("PUT", `/booking-admin/weeks/${id}`, body, TimetableWeek),
    deleteWeek: (id: number) => send("DELETE", `/booking-admin/weeks/${id}`),
    accessCheck: (userId: number, roomId: number) => json("/booking-admin/access-check", AccessCheck, { user_id: userId, room_id: roomId }),
    outbox: (status?: string) => json("/booking-admin/outbox", z.array(Outbox), { status }),
    retryOutbox: (id: number) => send("POST", `/booking-admin/outbox/${id}/retry`, undefined, Outbox),
  },
  org: {
    public: () => json("/org/public", OrgPublic),
    setupStatus: () => json("/org/setup-status", SetupStatus),
    setup: (body: SetupIn) => send("POST", "/org/setup", body, z.object({ user_id: z.number(), email: z.string().nullish(), username: z.string().nullish() })),
    settings: () => json("/org/settings", OrgSettings),
    putSettings: (body: OrgSettingsIn) => send("PUT", "/org/settings", body, OrgSettings),
    uploadLogo: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request("/org/logo", { ...s, method: "POST", formData: fd, schema: z.object({ logo_url: z.string().nullish() }) });
    },
    deleteLogo: () => send("DELETE", "/org/logo", undefined, z.object({ logo_url: z.string().nullish() })),
    ldap: () => json("/org/auth/ldap", LdapSettings),
    putLdap: (body: Partial<LdapSettings>) => send("PUT", "/org/auth/ldap", body, LdapSettings),
    testLdap: (body: { username: string; password: string; settings?: Partial<LdapSettings> }) => send("POST", "/org/auth/ldap/test", body, LdapTestOut),
    smtp: () => json("/org/smtp", SmtpSettings),
    putSmtp: (body: Partial<Omit<SmtpSettings, "configured">>) => send("PUT", "/org/smtp", body, SmtpSettings),
    testSmtp: (to: string) => send("POST", "/org/smtp/test", { to }, SmtpTestOut),
    translations: (language?: string) => json("/org/translations", z.array(Translation), { language }),
    putTranslations: (items: Omit<Translation, "id">[]) => send("PUT", "/org/translations", items, z.array(Translation)),
    deleteTranslation: (id: number) => send("DELETE", `/org/translations/${id}`),
    changelog: () => json("/org/changelog", Changelog),
    changelogSeen: () => send("POST", "/org/changelog/seen", undefined, z.object({ viewed_at: z.string() })),
  },
  auth: {
    me: () => json("/auth/me", Me),
    requestReset: (email: string) => send("POST", "/auth/password-reset/request", { email }),
    confirmReset: (token: string, password: string) => send("POST", "/auth/password-reset/confirm", { token, password }, z.object({ ok: z.boolean() })),
  },
};

export const Me = z.object({
  id: z.number(),
  email: z.string().nullish(),
  username: z.string().nullish(),
  full_name: z.string().nullish(),
  role: z.string().default("NONE"),
  role_id: z.number().nullish(),
  department_id: z.number().nullish(),
  is_active: z.boolean().default(true),
  force_password_reset: z.boolean().default(false),
  permissions: z.array(z.string()).default([]),
});
export type Me = z.infer<typeof Me>;

/** Same-origin URL for the CSV export (the Next proxy attaches the JWT from the cookie). */
export function exportCsvUrl(q: { term_id?: number; room_group_id?: number; include_cancelled?: boolean }): string {
  const p = new URLSearchParams();
  if (q.term_id) p.set("term_id", String(q.term_id));
  if (q.room_group_id != null) p.set("room_group_id", String(q.room_group_id));
  if (q.include_cancelled) p.set("include_cancelled", "true");
  const qs = p.toString();
  return `/api/v1/bookings/export.csv${qs ? `?${qs}` : ""}`;
}

/* ------------------------------------------------------------------------------------------ hooks */

export const crbsKeys = {
  me: ["crbs", "me"] as const,
  context: ["crbs", "context"] as const,
  grid: (q: GridQuery) => ["crbs", "grid", q] as const,
  dates: (q: object) => ["crbs", "dates", q] as const,
  booking: (id: number) => ["crbs", "booking", id] as const,
  series: (id: number) => ["crbs", "series", id] as const,
  mine: (q: object) => ["crbs", "mine", q] as const,
  dashboard: ["crbs", "dashboard"] as const,
  ownedRooms: ["crbs", "owned-rooms"] as const,
  roles: ["crbs", "roles"] as const,
  permissions: ["crbs", "permissions"] as const,
  users: (q: object) => ["crbs", "users", q] as const,
  constraints: (id: number) => ["crbs", "constraints", id] as const,
  departments: ["crbs", "departments"] as const,
  holidays: (termId?: number) => ["crbs", "holidays", termId ?? null] as const,
  groups: ["crbs", "room-groups"] as const,
  adminRooms: ["crbs", "admin-rooms"] as const,
  fields: ["crbs", "fields"] as const,
  roomFields: (id: number) => ["crbs", "room-fields", id] as const,
  acl: (q: object) => ["crbs", "acl", q] as const,
  sessions: ["crbs", "sessions"] as const,
  termSchedules: (id: number) => ["crbs", "term-schedules", id] as const,
  sessionDates: (id: number) => ["crbs", "session-dates", id] as const,
  schedules: ["crbs", "schedules"] as const,
  weeks: ["crbs", "weeks"] as const,
  outbox: (status?: string) => ["crbs", "outbox", status ?? null] as const,
  orgPublic: ["crbs", "org-public"] as const,
  setupStatus: ["crbs", "setup-status"] as const,
  orgSettings: ["crbs", "org-settings"] as const,
  ldap: ["crbs", "ldap"] as const,
  smtp: ["crbs", "smtp"] as const,
  translations: (lang?: string) => ["crbs", "translations", lang ?? null] as const,
  changelog: ["crbs", "changelog"] as const,
};

export const useCrbsMe = () => useQuery({ queryKey: crbsKeys.me, queryFn: crbs.auth.me, staleTime: 60_000, retry: false });
export const useBookingContext = () => useQuery({ queryKey: crbsKeys.context, queryFn: crbs.bookings.context, staleTime: 30_000, retry: false });
export const useBookingGrid = (q: GridQuery, enabled = true) =>
  useQuery({ queryKey: crbsKeys.grid(q), queryFn: () => crbs.bookings.grid(q), enabled, placeholderData: keepPreviousData, staleTime: 10_000, retry: false });
export const useBookingDates = (q: { term_id?: number; from?: string; to?: string }, enabled = true) =>
  useQuery({ queryKey: crbsKeys.dates(q), queryFn: () => crbs.bookings.dates(q), enabled, staleTime: 60_000, placeholderData: keepPreviousData, retry: false });
export const useBooking = (id: number | null) =>
  useQuery({ queryKey: crbsKeys.booking(id ?? 0), queryFn: () => crbs.bookings.get(id ?? 0), enabled: id !== null, retry: false });
export const useSeries = (id: number | null, enabled: boolean) =>
  useQuery({ queryKey: crbsKeys.series(id ?? 0), queryFn: () => crbs.bookings.series(id ?? 0), enabled: id !== null && enabled, retry: false });
export const useMyBookings = (q: { from?: string; to?: string; status?: "BOOKED" | "CANCELLED" | "ALL" }) =>
  useQuery({ queryKey: crbsKeys.mine(q), queryFn: () => crbs.bookings.mine(q), retry: false });
export const useBookingDashboard = () => useQuery({ queryKey: crbsKeys.dashboard, queryFn: crbs.bookings.dashboard, retry: false });
export const useOwnedRooms = () => useQuery({ queryKey: crbsKeys.ownedRooms, queryFn: crbs.bookings.ownedRooms, retry: false });
export const useRoles = (enabled = true) => useQuery({ queryKey: crbsKeys.roles, queryFn: crbs.roles.list, enabled, staleTime: 30_000, retry: false });
export const usePermissionCatalogue = () => useQuery({ queryKey: crbsKeys.permissions, queryFn: crbs.roles.permissions, staleTime: 10 * 60_000, retry: false });
export const useUserSearch = (q: Parameters<typeof crbs.users.search>[0], enabled = true) =>
  useQuery({ queryKey: crbsKeys.users(q), queryFn: () => crbs.users.search(q), enabled, placeholderData: keepPreviousData, retry: false });
export const useUserConstraints = (id: number | null) =>
  useQuery({ queryKey: crbsKeys.constraints(id ?? 0), queryFn: () => crbs.users.constraints(id ?? 0), enabled: id !== null, retry: false });
export const useDepartments = (enabled = true) => useQuery({ queryKey: crbsKeys.departments, queryFn: () => crbs.departments.list(), enabled, staleTime: 5 * 60_000, retry: false });
export const useHolidays = (termId?: number) => useQuery({ queryKey: crbsKeys.holidays(termId), queryFn: () => crbs.holidays.list(termId), retry: false });
export const useRoomGroups = (enabled = true) => useQuery({ queryKey: crbsKeys.groups, queryFn: crbs.roomAdmin.groups, enabled, retry: false });
export const useAdminRooms = (enabled = true) => useQuery({ queryKey: crbsKeys.adminRooms, queryFn: () => crbs.roomAdmin.rooms(), enabled, retry: false });
export const useCustomFields = (enabled = true) => useQuery({ queryKey: crbsKeys.fields, queryFn: crbs.roomAdmin.fields, enabled, retry: false });
export const useRoomFieldValues = (id: number | null) =>
  useQuery({ queryKey: crbsKeys.roomFields(id ?? 0), queryFn: () => crbs.roomAdmin.roomFields(id ?? 0), enabled: id !== null, retry: false });
export const useAcl = (q: { entity_type?: string; entity_id?: number }) => useQuery({ queryKey: crbsKeys.acl(q), queryFn: () => crbs.roomAdmin.acl(q), retry: false });
export const useSessions = (enabled = true) => useQuery({ queryKey: crbsKeys.sessions, queryFn: crbs.bookingAdmin.sessions, enabled, retry: false });
export const useTermSchedules = (termId: number | null) =>
  useQuery({ queryKey: crbsKeys.termSchedules(termId ?? 0), queryFn: () => crbs.bookingAdmin.termSchedules(termId ?? 0), enabled: termId !== null, retry: false });
export const useSessionDates = (termId: number | null) =>
  useQuery({ queryKey: crbsKeys.sessionDates(termId ?? 0), queryFn: () => crbs.bookingAdmin.dates(termId ?? 0), enabled: termId !== null, retry: false });
export const useSchedules = (enabled = true) => useQuery({ queryKey: crbsKeys.schedules, queryFn: crbs.bookingAdmin.schedules, enabled, retry: false });
export const useTimetableWeeks = (enabled = true) => useQuery({ queryKey: crbsKeys.weeks, queryFn: crbs.bookingAdmin.weeks, enabled, retry: false });
export const useOutbox = (status?: string) => useQuery({ queryKey: crbsKeys.outbox(status), queryFn: () => crbs.bookingAdmin.outbox(status), retry: false });
export const useOrgPublic = () => useQuery({ queryKey: crbsKeys.orgPublic, queryFn: crbs.org.public, staleTime: 60_000, retry: false });
export const useSetupStatus = () => useQuery({ queryKey: crbsKeys.setupStatus, queryFn: crbs.org.setupStatus, retry: false });
export const useOrgSettings = (enabled = true) => useQuery({ queryKey: crbsKeys.orgSettings, queryFn: crbs.org.settings, enabled, retry: false });
export const useLdapSettings = () => useQuery({ queryKey: crbsKeys.ldap, queryFn: crbs.org.ldap, retry: false });
export const useSmtpSettings = () => useQuery({ queryKey: crbsKeys.smtp, queryFn: crbs.org.smtp, retry: false });
export const useTranslations = (lang?: string) => useQuery({ queryKey: crbsKeys.translations(lang), queryFn: () => crbs.org.translations(lang), retry: false });
export const useChangelog = () => useQuery({ queryKey: crbsKeys.changelog, queryFn: crbs.org.changelog, retry: false });

/**
 * Mutation that invalidates the given keys on success. Errors are left to the caller (`onError` +
 * `crbsError`), so every failure can be explained in the user's language.
 */
export function useCrbsMutation<TVars, TOut>(fn: (vars: TVars) => Promise<TOut>, invalidate: QueryKey[] = []) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((key) => qc.invalidateQueries({ queryKey: key })));
    },
  });
}

/** Everything a booking can change: the grid, the lists, the context counters. */
export const BOOKING_KEYS: QueryKey[] = [["crbs", "grid"], ["crbs", "mine"], ["crbs", "dashboard"], ["crbs", "owned-rooms"], crbsKeys.context, ["crbs", "booking"], ["crbs", "series"]];
