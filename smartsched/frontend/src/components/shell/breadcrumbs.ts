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

/**
 * Parent paths without their own navigation entry: `/analytics` and `/exams` only redirect to their one page
 * (the heatmap, the invigilator assignment), so their crumb names the area, not the raw segment.
 */
const PARENT_LABELS: ReadonlyMap<string, MessageKey> = new Map([
  ["/analytics", "nav.analytics"],
  ["/exams", "nav.exams"],
  // wave 2 (P2): the resolver lives under the bookings, without its own navigation entry
  ["/bookings/conflicts", "resolver.title"],
  // T-R1-08 (R1-A-11): the moderation console's sub-pages read like their page titles, never the route word
  ["/moderation/people", "glass.shell.crumbPeople"],
  ["/moderation/learning", "learning.memory.title"],
  ["/moderation/recreate", "glass.shell.crumbRecreate"],
]);

/** Parents that are only a path prefix (`/programs/new` is the page): no crumb of their own. */
const SILENT_PARENTS: ReadonlySet<string> = new Set(["/programs"]);

/** Segments that are pages without their own navigation entry. */
const SEGMENT_LABELS: Readonly<Record<string, MessageKey>> = {
  classes: "glass.shell.classes",
};

/**
 * A record id after one of these parents gets a name of its own (the page's title, with the number only where
 * the UI shows it everywhere, such as "Çalıştırma #12"). Any other id is folded into its parent crumb: the trail
 * never prints a bare `#157` (T-R1-08).
 */
const DETAIL_LABELS: Readonly<Record<string, { key: MessageKey; withId?: boolean }>> = {
  "/runs": { key: "glass.shell.runShort", withId: true },
  "/rooms": { key: "titles.room" },
  "/moderation/people": { key: "glass.shell.crumbPerson" },
};

/** A path segment that is a record id or a wizard draft key, not a page name. */
const isId = (seg: string) => /^\d+$/.test(seg) || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(seg);

export type Crumb = { href: string; label: string; current: boolean };

export interface CrumbContext {
  /** the signed-in academician's own instructor id (GET /moderation/me): their person page is "Geçmişim" */
  ownPersonId?: number | null;
}

export function breadcrumbs(pathname: string, t: (key: MessageKey, vars?: Record<string, string | number>) => string, ctx: CrumbContext = {}): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  // the academician's own history: "Taleplerim / Geçmişim", not the planners' console trail (T-R1-08)
  if (parts[0] === "moderation" && parts[1] === "people" && parts.length === 3 && ctx.ownPersonId != null && String(ctx.ownPersonId) === parts[2]) {
    return [
      { href: "/moderation/me", label: t("crbs.nav.myRequests"), current: false },
      { href: pathname, label: t("glass.shell.crumbMyHistory"), current: true },
    ];
  }
  const out: Crumb[] = [];
  parts.forEach((seg, i) => {
    const href = `/${parts.slice(0, i + 1).join("/")}`;
    const current = i === parts.length - 1;
    if (SILENT_PARENTS.has(href) && !current) return;
    const key = PATH_LABELS.get(href) ?? PARENT_LABELS.get(href) ?? SEGMENT_LABELS[seg];
    if (key) return out.push({ href, label: t(key), current });
    const parent = out.at(-1);
    if (isId(seg) && parent) {
      const detail = DETAIL_LABELS[parent.href];
      if (detail) return out.push({ href, label: detail.withId ? t(detail.key, { id: seg }) : t(detail.key), current });
      // an id with no page title of its own: the parent crumb stands for the page (no raw "#157")
      parent.href = href;
      parent.current = current;
      return;
    }
    // a route word nobody labelled (lower-case letters and hyphens) folds into its parent too; a code or a 404
    // path (no parent) is shown as typed
    if (parent && /^[a-z][a-z-]*$/.test(seg)) {
      parent.href = href;
      parent.current = current;
      return;
    }
    out.push({ href, label: decodeSegment(seg), current });
  });
  return out;
}

function decodeSegment(seg: string): string {
  try {
    return decodeURIComponent(seg);
  } catch {
    return seg;
  }
}
