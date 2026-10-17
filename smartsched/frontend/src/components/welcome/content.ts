/**
 * The product-fixed part of the welcome guide (docs/design/v3/welcome-guide.md §5): per audience the card keys and
 * their links, the tour anchors, the checklist items and the hints. Order, links and icons are product decisions tied
 * to permissions (admins edit texts only, spec §4.6); the copy lives in `welcome.*` message keys.
 *
 * The server sends the cards / steps / items it decided (`GET /welcome`); this catalog is the fallback when a field is
 * missing (an older backend) and the source of the message keys for each entry.
 */
import {
  BookMarked,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  CalendarSearch,
  ClipboardList,
  FolderInput,
  GitCompareArrows,
  Grid3x3,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  Map as MapIcon,
  PlayCircle,
  Plug,
  Repeat,
  Send,
  Stamp,
  UserPlus,
  Users,
  Warehouse,
  Zap,
} from "lucide-react";
import type { MessageKey } from "@/lib/i18n";
import { AUDIENCES, type Audience, isAudience } from "@/lib/api/welcome";

export interface CardDef {
  key: string;
  href: string;
  icon: LucideIcon;
}
export interface StepDef {
  anchor: string;
  route?: string;
  interactive?: boolean;
}
export interface ItemDef {
  key: string;
  href: string;
  /** view-only: "Bitti olarak işaretle" and a client `item_done` when the page opens */
  manual?: boolean;
}

export const CARDS: Record<Audience, CardDef[]> = {
  academician: [
    { key: "quick_reserve", href: "/reserve", icon: Zap },
    { key: "my_requests", href: "/moderation/me", icon: ClipboardList },
    { key: "my_bookings", href: "/my-bookings", icon: BookMarked },
    { key: "calendar", href: "/profile#calendar", icon: CalendarPlus },
  ],
  staff: [
    { key: "quick_reserve", href: "/reserve", icon: Zap },
    { key: "find_room", href: "/find-room", icon: CalendarSearch },
    { key: "approval_rooms", href: "/find-room", icon: Stamp },
    { key: "my_bookings", href: "/my-bookings", icon: BookMarked },
  ],
  approver: [{ key: "approvals", href: "/approvals", icon: Stamp }],
  dept_admin: [
    { key: "book_for_other", href: "/bookings", icon: UserPlus },
    { key: "recurring", href: "/bookings", icon: Repeat },
    { key: "dept_calendar", href: "/profile#calendar", icon: CalendarRange },
  ],
  viewer: [
    { key: "dashboard", href: "/dashboard", icon: LayoutDashboard },
    { key: "timetable", href: "/timetable", icon: CalendarDays },
    { key: "runs", href: "/runs", icon: GitCompareArrows },
    { key: "heatmap", href: "/analytics/heatmap", icon: Grid3x3 },
  ],
  planner: [
    { key: "intake", href: "/onboarding", icon: FolderInput },
    { key: "requests", href: "/requests", icon: Inbox },
    { key: "generate", href: "/generate", icon: PlayCircle },
    { key: "timetable", href: "/timetable", icon: CalendarDays },
    { key: "publish", href: "/runs", icon: Send },
  ],
  admin: [
    { key: "users", href: "/admin/users", icon: Users },
    { key: "rooms", href: "/admin/rooms", icon: Warehouse },
    { key: "terms", href: "/admin/sessions", icon: CalendarRange },
    { key: "rules", href: "/admin/integrations", icon: Plug },
    { key: "welcome", href: "/admin/welcome", icon: MapIcon },
  ],
};

/** 5 steps or fewer per audience (owner principle 2026-10-17; the spec's 6-step planner and admin tours were trimmed). */
export const STEPS: Record<Audience, StepDef[]> = {
  academician: [
    { anchor: "nav-reserve" },
    { anchor: "reserve-when", route: "/reserve", interactive: true },
    { anchor: "nav-my-bookings" },
    { anchor: "nav-my-requests" },
    { anchor: "user-menu" },
  ],
  staff: [{ anchor: "nav-reserve" }, { anchor: "nav-find-room" }, { anchor: "nav-my-bookings" }, { anchor: "user-menu" }],
  approver: [{ anchor: "nav-approvals" }, { anchor: "approvals-row-actions", route: "/approvals" }],
  dept_admin: [{ anchor: "nav-bookings" }],
  viewer: [{ anchor: "nav-dashboard" }, { anchor: "nav-timetable" }, { anchor: "nav-runs" }, { anchor: "nav-heatmap" }],
  planner: [{ anchor: "nav-onboarding" }, { anchor: "nav-requests" }, { anchor: "nav-generate" }, { anchor: "nav-timetable" }, { anchor: "nav-runs" }],
  admin: [
    { anchor: "nav-admin", route: "/admin" },
    { anchor: "admin-group-users", route: "/admin" },
    { anchor: "admin-group-resources", route: "/admin" },
    { anchor: "admin-group-timetable", route: "/admin" },
    { anchor: "nav-welcome-admin" },
  ],
};

export const ITEMS: Record<Audience, ItemDef[]> = {
  academician: [
    { key: "profile", href: "/profile" },
    { key: "first_booking", href: "/reserve" },
    { key: "channel", href: "/profile#channels" },
    { key: "calendar", href: "/profile#calendar" },
    { key: "requests_seen", href: "/moderation/me", manual: true },
  ],
  staff: [
    { key: "profile", href: "/profile" },
    { key: "first_booking", href: "/reserve" },
    { key: "find_room_filter", href: "/find-room", manual: true },
    { key: "channel", href: "/profile#channels" },
    { key: "calendar_bookings", href: "/my-bookings" },
  ],
  approver: [
    { key: "first_decision", href: "/approvals" },
    { key: "approver_channel", href: "/profile#channels" },
  ],
  dept_admin: [
    { key: "book_for_other", href: "/bookings" },
    { key: "recurring", href: "/bookings" },
  ],
  viewer: [
    { key: "timetable_seen", href: "/timetable", manual: true },
    { key: "compare_seen", href: "/runs/compare", manual: true },
    { key: "channel", href: "/profile#channels" },
  ],
  planner: [
    { key: "intake_done", href: "/onboarding" },
    { key: "requests_reviewed", href: "/requests" },
    { key: "first_run", href: "/generate" },
    { key: "published", href: "/runs" },
  ],
  admin: [
    { key: "org_ready", href: "/admin/settings" },
    { key: "rooms_added", href: "/admin/rooms" },
    { key: "users_invited", href: "/admin/users" },
    { key: "mail_ready", href: "/admin/email" },
    { key: "welcome_reviewed", href: "/admin/welcome", manual: true },
  ],
};

/** Feature hints (spec §4.5). `page` = an inline strip at the top of that page; `nav` = the desktop popover target. */
export interface HintDef {
  key: string;
  /** the route the hint belongs to ("Dene" goes there) */
  href: string;
  /** an inline strip at the top of these pages */
  pages: string[];
  /** desktop: a small non-modal popover on this nav anchor (phones get the strip on `phonePage`) */
  nav?: string;
  phonePage?: string;
  /** a "Yeni" badge on this nav entry while unseen */
  badge?: string;
}
export const HINTS: HintDef[] = [
  { key: "quick_reserve", href: "/reserve", pages: [], nav: "nav-reserve", phonePage: "/bookings", badge: "/reserve" },
  { key: "calendar_export", href: "/profile#calendar", pages: ["/my-bookings"] },
  { key: "admin_ai", href: "/admin/ai", pages: ["/admin/ai"], badge: "/admin/ai" },
  { key: "admin_ops", href: "/admin/ops", pages: ["/admin/ops"], badge: "/admin/ops" },
  { key: "admin_integrations", href: "/admin/integrations", pages: ["/admin/integrations"], badge: "/admin/integrations" },
];
export const hintKey = (key: string) => key.replace(/^hint\./, "");
export const hintDef = (key: string) => HINTS.find((h) => h.key === hintKey(key));

/** The audience's home pages: the sheet auto-shows only there (a deep link is never interrupted, spec §6.2). */
export const HOME_ROUTES = ["/", "/dashboard", "/reserve", "/bookings", "/my-bookings", "/admin"];
/** The home page that also carries the checklist card (spec §4.3). */
export const CHECKLIST_HOMES = ["/dashboard", "/reserve", "/admin"];

/** Never call the API there (spec §6.2, §15 check 5). */
export function isExcludedRoute(pathname: string, search: URLSearchParams | null | undefined): boolean {
  if (/^\/(setup|login|welcome|reset-password|public|slot-display|display|kiosk)(\/|$)/.test(pathname)) return true;
  if (search && ["kiosk", "embed", "print"].some((k) => search.get(k) === "1")) return true;
  return false;
}

/* ------------------------------------------------------------------------------------------ message keys */

export const audienceKey = (a: string) => `welcome.audience.${isAudience(a) ? a : "staff"}` as MessageKey;
export const sheetKey = (a: string, field: "title" | "lead") => `welcome.sheet.${a}.${field}` as MessageKey;
export const cardKey = (a: string, card: string, field: "title" | "body") => `welcome.sheet.${a}.cards.${card}.${field}` as MessageKey;
export const stepKey = (anchor: string, field: "title" | "body" | "bodyEmpty") => `welcome.tour.step.${anchor}.${field}` as MessageKey;
export const itemKey = (item: string, field: "title" | "sub") => `welcome.check.${item}.${field}` as MessageKey;
export const hintMsg = (key: string, field: "title" | "body") => `welcome.hints.${hintKey(key)}.${field}` as MessageKey;

/* ------------------------------------------------------------------------------------------ helpers */

/** Known audiences in precedence order (unknown codes dropped). */
export function orderAudiences(list: readonly string[] | null | undefined): Audience[] {
  const set = new Set((list ?? []).filter(isAudience));
  return AUDIENCES.filter((a) => set.has(a));
}

/** The primary audience: the server's when it is known, else the first by precedence. */
export function primaryOf(primary: string | null | undefined, audiences: readonly string[]): Audience | null {
  if (isAudience(primary) && (audiences.length === 0 || audiences.includes(primary))) return primary;
  return orderAudiences(audiences)[0] ?? null;
}

export function cardDef(audience: string, key: string): CardDef | undefined {
  return isAudience(audience) ? CARDS[audience].find((c) => c.key === key) : undefined;
}

export function itemDef(key: string): ItemDef | undefined {
  for (const a of AUDIENCES) {
    const hit = ITEMS[a].find((i) => i.key === key);
    if (hit) return hit;
  }
  return undefined;
}
