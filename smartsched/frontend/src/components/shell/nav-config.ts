import { CalendarDays, FileUp, Inbox, LayoutDashboard, ListChecks, type LucideIcon, PlayCircle, Settings, Users, Warehouse } from "lucide-react";
import type { MessageKey } from "@/lib/i18n";

export interface NavItem {
  href: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** vim-style "g <key>" shortcut */
  key?: string;
  badge?: "needsReview" | "running";
}
export interface NavGroup {
  labelKey: MessageKey;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.plan",
    items: [
      { href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, key: "d" },
      { href: "/import", labelKey: "nav.import", icon: FileUp, key: "i" },
      { href: "/requests", labelKey: "nav.requests", icon: Inbox, key: "r", badge: "needsReview" },
      { href: "/generate", labelKey: "nav.generate", icon: PlayCircle, key: "g" },
    ],
  },
  {
    labelKey: "nav.results",
    items: [
      { href: "/timetable", labelKey: "nav.timetable", icon: CalendarDays, key: "t" },
      { href: "/runs", labelKey: "nav.runs", icon: ListChecks, badge: "running" },
    ],
  },
  {
    labelKey: "nav.master",
    items: [{ href: "/rooms", labelKey: "nav.rooms", icon: Warehouse }],
  },
  {
    labelKey: "nav.admin",
    items: [
      { href: "/settings", labelKey: "nav.settings", icon: Settings, key: "s" },
      { href: "/settings?tab=users", labelKey: "nav.users", icon: Users },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items);
