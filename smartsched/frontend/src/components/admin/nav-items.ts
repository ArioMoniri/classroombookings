// Navigation entries for the CRBS-parity pages (/bookings, /my-bookings, /profile, /admin/*). The glass-shell
// agent created the stub; the CRBS frontend agent owns this file. The sidebar, tab bar and ⌘K import it and
// gate every entry on `permission` (any of, from GET /auth/me permissions[]); no permission = every signed-in user
// (CRBS shows Bookings to everyone; room-level rights come from ACLs the role list cannot see).
import { BookMarked, CalendarRange, Settings2, UserRound, type LucideIcon } from "lucide-react";
import type { MessageKey } from "@/lib/i18n";
import { ADMIN_SECTIONS, SETUP_PERMISSIONS } from "@/lib/permissions";

export interface AdminNavItem {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** one permission or any-of list, e.g. "book_single.create" or ["setup.rooms", "setup.users"]; omitted = any signed-in user */
  permission?: string | string[];
  /** vim-style "g <key>" shortcut, if the shell wants one */
  key?: string;
}

/** Primary destinations: put these in the sidebar / tab bar. */
export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  { href: "/bookings", labelKey: "crbs.nav.bookings", icon: CalendarRange, key: "b" },
  { href: "/my-bookings", labelKey: "crbs.nav.myBookings", icon: BookMarked, key: "m" },
  { href: "/admin", labelKey: "crbs.nav.admin", icon: Settings2, permission: [...SETUP_PERMISSIONS] },
];

/** Secondary destinations: the profile (user menu) and every setup screen (⌘K, or a collapsible "Setup" group). */
export const ADMIN_SECTION_NAV_ITEMS: AdminNavItem[] = [
  { href: "/profile", labelKey: "crbs.nav.profile", icon: UserRound },
  ...ADMIN_SECTIONS.map((s) => ({ href: s.href, labelKey: s.labelKey, icon: Settings2, permission: [...s.permission] })),
];
