// Navigation entries for the CRBS-parity pages (/bookings, /my-bookings, /admin/*, /setup, /profile).
// Created empty by the glass-shell agent so the shell builds before the admin agent lands; that agent
// owns this file and fills the array. The sidebar, tab bar and ⌘K import it and gate every entry on
// `permission` (any of, from GET /auth/me permissions[]).
import type { LucideIcon } from "lucide-react";
import type { MessageKey } from "@/lib/i18n";

export interface AdminNavItem {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** one permission or any-of list, e.g. "book_single.create" or ["setup.rooms", "setup.users"] */
  permission: string | string[];
}

export const ADMIN_NAV_ITEMS: AdminNavItem[] = [];
