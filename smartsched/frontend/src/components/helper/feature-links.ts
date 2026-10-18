/**
 * HX-01 (helper.md §3.1): `feature_id` → href, anchor, kind and permission. The server never sends a URL; every
 * place the helper opens comes from this table (generated from the server's own index, features.yaml) or from the
 * palette's existing data-hit routes. An id the table does not know opens nothing.
 */
import type { Locale } from "@/lib/i18n";
import { FEATURE_INDEX, type FeatureEntry } from "./feature-index.gen";

export type { FeatureEntry, FeatureKind } from "./feature-index.gen";

const BY_ID: ReadonlyMap<string, FeatureEntry> = new Map(FEATURE_INDEX.map((e) => [e.id, e]));

export function featureById(id: string | null | undefined): FeatureEntry | undefined {
  return id ? BY_ID.get(id) : undefined;
}

/** The in-app route of a feature (`/profile#ai-usage`), or null for an id the client does not know. */
export function featureHref(id: string | null | undefined): string | null {
  const e = featureById(id);
  return e && e.route.startsWith("/") && !e.route.startsWith("//") ? e.route : null;
}

type Can = (perm: string | readonly string[] | undefined) => boolean;

/** The nav's rule: any-of permission (empty = everyone), and hidden for holders of `hideWith`. */
export function canOpenFeature(e: FeatureEntry, can: Can): boolean {
  if (e.hideWith && can(e.hideWith)) return false;
  return e.permission.length === 0 || can(e.permission);
}

export function featureTitle(id: string | null | undefined, locale: Locale): string | null {
  const e = featureById(id);
  return e ? e.title[locale] ?? e.title.tr : null;
}

/** "Yönetim › Kullanıcılar › Davet et" */
export function pathLine(path: { tr?: readonly string[]; en?: readonly string[] } | null | undefined, locale: Locale): string {
  const parts = (locale === "en" ? path?.en : path?.tr) ?? path?.tr ?? [];
  return parts.join(" › ");
}

export interface DataHit {
  kind: string;
  id: number;
  label: string;
}

/** Search data hits (`GET /helper/search` → `data`) open where the palette already opens them. */
export function dataHitHref(hit: DataHit): string | null {
  switch (hit.kind) {
    case "room":
      return `/bookings?display=room&room=${hit.id}`;
    case "course":
      return `/requests?q=${encodeURIComponent(hit.label)}`;
    case "instructor":
      return `/timetable?subject=instructor:${hit.id}`;
    case "program":
      return `/requests?program_id=${hit.id}`;
    case "section":
      return `/timetable`;
    default:
      return null;
  }
}
