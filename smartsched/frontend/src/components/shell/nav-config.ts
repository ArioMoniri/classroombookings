import { CalendarDays, FileUp, Inbox, LayoutDashboard, ListChecks, type LucideIcon, PlayCircle, Settings, Users, Warehouse } from "lucide-react";
import { ADMIN_NAV_ITEMS } from "@/components/admin/nav-items";
import type { MessageKey } from "@/lib/i18n";

export interface NavItem {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** vim-style "g <key>" shortcut */
  key?: string;
  badge?: "needsReview" | "running";
  /** shown only with any of these permissions (GET /auth/me permissions[]) */
  permission?: string | string[];
}
export interface NavGroup {
  labelKey: MessageKey;
  items: NavItem[];
}

/* Planning pages need planning.*; a teacher (book_single.create + room.view) sees only the timetable here
   plus the bookings entries from components/admin/nav-items.ts. */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.plan",
    items: [
      { href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, key: "d", permission: "planning.view" },
      { href: "/import", labelKey: "nav.import", icon: FileUp, key: "i", permission: "planning.edit" },
      { href: "/requests", labelKey: "nav.requests", icon: Inbox, key: "r", badge: "needsReview", permission: "planning.view" },
      { href: "/generate", labelKey: "nav.generate", icon: PlayCircle, key: "g", permission: "planning.edit" },
    ],
  },
  {
    labelKey: "nav.results",
    items: [
      { href: "/timetable", labelKey: "nav.timetable", icon: CalendarDays, key: "t", permission: ["planning.view", "room.view"] },
      { href: "/runs", labelKey: "nav.runs", icon: ListChecks, badge: "running", permission: "planning.view" },
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
    ],
  },
];

const BOOKING_PREFIXES = ["/bookings", "/my-bookings"];

/** The planning groups plus the CRBS-parity entries: bookings first, admin/setup/profile under "Admin". */
export function allNavGroups(): NavGroup[] {
  const extra = ADMIN_NAV_ITEMS.map((i): NavItem => ({ href: i.href, labelKey: i.labelKey, icon: i.icon, permission: i.permission }));
  const bookings = extra.filter((i) => BOOKING_PREFIXES.some((p) => i.href.startsWith(p)));
  const admin = extra.filter((i) => !bookings.includes(i));
  const groups = NAV_GROUPS.map((g) => (g.labelKey === "nav.admin" ? { ...g, items: [...g.items, ...admin.filter((a) => !g.items.some((x) => x.href === a.href))] } : g));
  return bookings.length ? [{ labelKey: "glass.shell.bookings", items: bookings }, ...groups] : groups;
}

/** Groups and items the user may open (`can` from usePermissions). Empty groups disappear. */
export function visibleNavGroups(can: (perm: string | readonly string[] | undefined) => boolean): NavGroup[] {
  return allNavGroups()
    .map((g) => ({ ...g, items: g.items.filter((i) => can(i.permission)) }))
    .filter((g) => g.items.length > 0);
}

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items);
