import { CalendarDays, FileUp, FolderInput, Inbox, LayoutDashboard, ListChecks, type LucideIcon, PlayCircle, Settings, Users, Warehouse } from "lucide-react";
import { ClipboardCheck, FolderPlus } from "lucide-react";
import { GitCompareArrows, Grid3x3, UserCheck, Zap } from "lucide-react";
import { Activity } from "lucide-react";
import { Cpu } from "lucide-react";
import { Plug } from "lucide-react";
import { ADMIN_NAV_ITEMS } from "@/components/admin/nav-items";
import type { MessageKey } from "@/lib/i18n";

export interface NavItem {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** vim-style "g <key>" shortcut */
  key?: string;
  badge?: "needsReview" | "running" | "approvals";
  /** shown only with any of these permissions (GET /auth/me permissions[]) */
  permission?: string | string[];
  /** hidden for users who hold this permission */
  hideWith?: string;
}
export interface NavGroup {
  labelKey: MessageKey;
  items: NavItem[];
}

/* Planning pages need planning.*; a teacher (book_single.create + room.view) sees only the bookings entries
   from components/admin/nav-items.ts (the timetable needs planning data the backend keeps behind planning.view). */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.plan",
    items: [
      { href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, key: "d", permission: "planning.view" },
      // UI/UX review §3: "Dosyalardan kur" with a folder icon (it read "Kurulum" next to Setup, with an AI sparkle)
      { href: "/onboarding", labelKey: "nav.onboarding", icon: FolderInput, key: "o", permission: "planning.edit" },
      { href: "/import", labelKey: "nav.import", icon: FileUp, key: "i", permission: "planning.edit" },
      { href: "/requests", labelKey: "nav.requests", icon: Inbox, key: "r", badge: "needsReview", permission: "planning.view" },
      { href: "/generate", labelKey: "nav.generate", icon: PlayCircle, key: "g", permission: "planning.edit" },
      // Phase 19 F1-F4 (p19-frontend): the moderation console and the program-from-scratch wizard
      { href: "/moderation", labelKey: "moderation.title", icon: ClipboardCheck, permission: "planning.view" },
      { href: "/programs/new", labelKey: "programWizard.nav", icon: FolderPlus, permission: "planning.edit" },
    ],
  },
  {
    labelKey: "nav.results",
    items: [
      // the timetable reads GET /terms and /runs (planning.view): room.view alone answers 403 there (wave1 crawler)
      { href: "/timetable", labelKey: "nav.timetable", icon: CalendarDays, key: "t", permission: "planning.view" },
      { href: "/runs", labelKey: "nav.runs", icon: ListChecks, badge: "running", permission: "planning.view" },
      // planning analytics UI (analytics-ui-2026-10-16): scenario comparison, utilisation heatmaps, invigilators
      { href: "/runs/compare", labelKey: "compare.title", icon: GitCompareArrows, permission: "planning.view" },
      { href: "/analytics/heatmap", labelKey: "analytics.title", icon: Grid3x3, permission: "planning.view" },
      { href: "/exams/invigilation", labelKey: "invigilation.title", icon: UserCheck, permission: "planning.view" },
    ],
  },
  {
    labelKey: "nav.master",
    items: [{ href: "/rooms", labelKey: "nav.rooms", icon: Warehouse, permission: ["planning.view", "setup.rooms"] }],
  },
  {
    labelKey: "nav.admin",
    items: [
      { href: "/settings", labelKey: "nav.settings", icon: Settings, key: "s", permission: ["planning.admin", "setup.settings"] },
      // the full CRBS user screen (username, role, department, limits, import); the old 4-field tab redirects here
      { href: "/admin/users", labelKey: "nav.users", icon: Users, permission: "setup.users" },
      // wave 3 W3-OPS: service status, error groups, Grafana, log tail
      { href: "/admin/ops", labelKey: "ops.nav", icon: Activity, permission: ["setup.settings", "planning.admin"] },
      // wave 3 W3-AI: AI providers, models per feature, usage, limits, guardrails
      { href: "/admin/ai", labelKey: "aiAdmin.nav", icon: Cpu, permission: ["setup.settings", "planning.admin"] },
      // wave 3b W3-HUB: integrations gallery (identity, e-mail, calendar, channels, webhooks / automation, AI)
      { href: "/admin/integrations", labelKey: "integrations.nav", icon: Plug, permission: ["setup.settings", "planning.admin"] },
    ],
  },
];

/** W3-SLOT (wave 3, one entry): "Hızlı rezervasyon" is the first bookings entry for anyone who may book. */
export const QUICK_RESERVE_ITEM: NavItem = { href: "/reserve", labelKey: "quickReserve.title", icon: Zap, permission: "book_single.create" };

const BOOKING_PREFIXES = ["/bookings", "/my-bookings", "/find-room", "/approvals"];

/** The planning groups plus the CRBS-parity entries: bookings first, admin/setup/profile under "Admin". */
export function allNavGroups(): NavGroup[] {
  // T-R1-06: "g t" opens Taleplerim for an academician (the timetable's "g t" is a planner's; hideWith keeps the
  // two apart, so only one of them is ever listed for a user)
  const extra = ADMIN_NAV_ITEMS.map((i): NavItem & { bookings?: boolean } => ({ href: i.href, labelKey: i.labelKey, icon: i.icon, permission: i.permission, badge: i.badge, key: i.key ?? (i.href === "/moderation/me" ? "t" : undefined), hideWith: i.hideWith, bookings: i.bookings }));
  const bookings = extra.filter((i) => i.bookings || BOOKING_PREFIXES.some((p) => i.href.startsWith(p)));
  const admin = extra.filter((i) => !bookings.includes(i));
  const groups = NAV_GROUPS.map((g) => (g.labelKey === "nav.admin" ? { ...g, items: [...g.items, ...admin.filter((a) => !g.items.some((x) => x.href === a.href))] } : g));
  return bookings.length ? [{ labelKey: "glass.shell.bookings", items: [QUICK_RESERVE_ITEM, ...bookings] }, ...groups] : groups;
}

/** Groups and items the user may open (`can` from usePermissions). Empty groups disappear. */
export function visibleNavGroups(can: (perm: string | readonly string[] | undefined) => boolean): NavGroup[] {
  return allNavGroups()
    .map((g) => ({ ...g, items: g.items.filter((i) => can(i.permission) && !(i.hideWith && can(i.hideWith))) }))
    .filter((g) => g.items.length > 0);
}

export const ALL_NAV_ITEMS = [...NAV_GROUPS.flatMap((g) => g.items), QUICK_RESERVE_ITEM];

/**
 * Planning pages and the permission each needs (the backend answers 403 without it). The shell renders the
 * no-access page on them instead of mounting the page (no fake empty states, no stack of 403 toasts);
 * /dashboard sends people without planning.view to their bookings. /settings (appearance) and /admin/*
 * (AdminGate) are not listed.
 */
export const PLANNING_ROUTES: readonly { prefix: string; permission: string | string[] }[] = [
  { prefix: "/dashboard", permission: "planning.view" },
  { prefix: "/onboarding", permission: "planning.edit" },
  { prefix: "/import", permission: "planning.edit" },
  { prefix: "/requests", permission: "planning.view" },
  { prefix: "/generate", permission: "planning.edit" },
  { prefix: "/timetable", permission: "planning.view" },
  { prefix: "/runs", permission: "planning.view" },
  { prefix: "/analytics", permission: "planning.view" },
  { prefix: "/exams", permission: "planning.view" },
  { prefix: "/rooms", permission: ["planning.view", "setup.rooms"] },
  { prefix: "/classes", permission: "planning.view" },
];

export function planningRequirement(pathname: string): string | string[] | undefined {
  return PLANNING_ROUTES.find((r) => pathname === r.prefix || pathname.startsWith(`${r.prefix}/`))?.permission;
}
