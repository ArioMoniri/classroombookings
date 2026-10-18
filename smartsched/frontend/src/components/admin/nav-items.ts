// Navigation entries for the CRBS-parity pages (/bookings, /my-bookings, /profile, /admin/*). The glass-shell
// agent created the stub; the CRBS frontend agent owns this file. The sidebar, tab bar and ⌘K import it and
// gate every entry on `permission` (any of, from GET /auth/me permissions[]); no permission = every signed-in user
// (CRBS shows Bookings to everyone; room-level rights come from ACLs the role list cannot see).
import {
  Activity,
  BookMarked,
  ClipboardList,
  Building2,
  CalendarClock,
  CalendarDays,
  CalendarOff,
  CalendarRange,
  CalendarSearch,
  CalendarX2,
  Clock,
  Cpu,
  DoorOpen,
  History,
  KeyRound,
  Lock,
  Mail,
  Map,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Stamp,
  UserCheck,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { MessageKey } from "@/lib/i18n";
import { ADMIN_SECTIONS, SETUP_PERMISSIONS } from "@/lib/permissions";
import { WAVE1_SECTIONS } from "./wave1-sections";

export interface AdminNavItem {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** one permission or any-of list, e.g. "book_single.create" or ["setup.rooms", "setup.users"]; omitted = any signed-in user */
  permission?: string | string[];
  /** vim-style "g <key>" shortcut, if the shell wants one */
  key?: string;
  /** a live count next to the entry (the shell resolves it; wave 1: open approval requests) */
  badge?: "approvals";
  /** hidden for users who hold this permission (they have a fuller entry for the same page) */
  hideWith?: string;
  /** listed with the bookings entries (sidebar group, tab bar) */
  bookings?: boolean;
}

/** Primary destinations: put these in the sidebar / tab bar. */
export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  { href: "/bookings", labelKey: "crbs.nav.bookings", icon: CalendarRange, key: "b" },
  { href: "/my-bookings", labelKey: "crbs.nav.myBookings", icon: BookMarked, key: "m" },
  // wave 1 (docs/product/wave1-api.md): T1 follows its backend guard — POST /rooms/find takes any signed-in
  // user (CurrentAccess) and searches only the rooms they may view (room.view by role or ACL), so no
  // permission here; the approver inbox needs approvals.decide (GET /approvals/inbox answers [] without it)
  { href: "/find-room", labelKey: "wave1.nav.findRoom", icon: CalendarSearch },
  { href: "/approvals", labelKey: "wave1.nav.approvals", icon: Stamp, permission: "approvals.decide", badge: "approvals" },
  // Phase 19: an academician (can book, no planning.view) sees their own planning requests on /moderation;
  // planners keep the "Moderasyon" entry of the planning group
  { href: "/moderation/me", labelKey: "crbs.nav.myRequests", icon: ClipboardList, permission: ["book_single.create", "book_recur.create"], hideWith: "planning.view", bookings: true },
  // PER-F09 (fix-h-2026-10-18): "Derslerim", the academician's own classes in one week (GET /me/classes/week)
  { href: "/my-classes", labelKey: "myClasses.title", icon: CalendarDays, permission: ["book_single.create", "book_recur.create"], hideWith: "planning.view", bookings: true },
  { href: "/admin", labelKey: "crbs.nav.admin", icon: Settings2, permission: [...SETUP_PERMISSIONS] },
];

/** One icon per setup section (UI/UX review §3: every section had the same gear). */
export const SECTION_ICONS: Record<string, LucideIcon> = {
  "/admin/users": Users,
  "/admin/roles": ShieldCheck,
  "/admin/departments": Building2,
  "/admin/rooms": DoorOpen,
  "/admin/access": UserCheck,
  "/admin/sessions": CalendarDays,
  "/admin/holidays": CalendarOff,
  "/admin/schedules": Clock,
  "/admin/weeks": CalendarRange,
  "/admin/conflicts": CalendarX2,
  "/admin/settings": SlidersHorizontal,
  "/admin/authentication": KeyRound,
  "/admin/email": Mail,
  "/admin/approval-rules": Stamp,
  "/admin/booking-rules": CalendarClock,
  "/admin/audit": History,
  "/admin/kvkk": Lock,
  "/admin/ai": Cpu,
  "/admin/ops": Activity,
  "/admin/welcome": Map,
};

/** Secondary destinations: the profile (user menu) and every setup screen (⌘K, or a collapsible "Setup" group). */
export const ADMIN_SECTION_NAV_ITEMS: AdminNavItem[] = [
  { href: "/profile", labelKey: "crbs.nav.profile", icon: UserRound },
  ...ADMIN_SECTIONS.map((s) => ({ href: s.href, labelKey: s.labelKey, icon: SECTION_ICONS[s.href] ?? Settings2, permission: [...s.permission] })),
  ...WAVE1_SECTIONS.map((s) => ({ href: s.href, labelKey: s.labelKey, icon: SECTION_ICONS[s.href] ?? Settings2, permission: [...s.permission] })),
];
