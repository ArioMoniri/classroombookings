import { ADMIN_NAV_ITEMS, ADMIN_SECTION_NAV_ITEMS } from "@/components/admin/nav-items";
import type { MessageKey } from "@/lib/i18n";
import { ALL_NAV_ITEMS } from "./nav-config";

/**
 * Breadcrumb labels by full path, taken from the navigation entries so a crumb reads like the sidebar and ⌘K
 * (`/admin` → "Kurulum", `/admin/conflicts` → "Rezervasyon çakışmaları"). A path match wins over the segment
 * name: `/rooms` is the planning rooms page, `/admin/rooms` the CRBS room setup.
 */
const PATH_LABELS: ReadonlyMap<string, MessageKey> = new Map(
  [...ALL_NAV_ITEMS, ...ADMIN_NAV_ITEMS, ...ADMIN_SECTION_NAV_ITEMS]
    .filter((item) => !item.href.includes("?"))
    .map((item) => [item.href, item.labelKey] as const),
);

/** Segments that are pages without their own navigation entry. */
const SEGMENT_LABELS: Readonly<Record<string, MessageKey>> = {
  classes: "glass.shell.classes",
};

export type Crumb = { href: string; label: string; current: boolean };

export function breadcrumbs(pathname: string, t: (key: MessageKey) => string): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  return parts.map((seg, i) => {
    const href = `/${parts.slice(0, i + 1).join("/")}`;
    const key = PATH_LABELS.get(href) ?? SEGMENT_LABELS[seg];
    const label = key ? t(key) : /^\d+$/.test(seg) ? `#${seg}` : decodeSegment(seg);
    return { href, label, current: i === parts.length - 1 };
  });
}

function decodeSegment(seg: string): string {
  try {
    return decodeURIComponent(seg);
  } catch {
    return seg;
  }
}
