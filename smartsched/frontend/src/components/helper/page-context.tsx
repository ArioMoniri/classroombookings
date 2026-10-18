"use client";
/**
 * HX-16 (helper.md §2.4 footer, §17.1 #7; API.md HB-D §2): the "Bu sayfa: …" chip of the helper sheet.
 *
 * - The page is the feature index's entry for `pathname + hash` (a `#section` picks its tab, a detail view such as
 *   `/rooms/12` falls back to `/rooms`), and only one the person may open (the nav's rule). No entry, no chip.
 * - A detail view adds its entity: a room (`/rooms/12`, `/bookings?display=room&room=12`) or an approval request
 *   (`?request=41` on Onaylar / Taleplerim / Rezervasyonlarım). Never page text.
 * - While the chip is on, `POST /helper/turn` carries `context: {route, entity_kind?, entity_id?}` (the server's own
 *   zod rules, {@link TurnContext}); one tap on its ✕ removes it for this page, and the next page brings it back.
 *   The server still drops a page or an entity the person may not see; the context never adds a tool or a right.
 */
import { X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { IconButton } from "@/components/ui/button";
import { TurnContext } from "@/lib/api/helper";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { canOpenFeature, type FeatureEntry } from "./feature-links";
import { FEATURE_INDEX } from "./feature-index.gen";

type Can = (perm: string | readonly string[] | undefined) => boolean;

export interface PageContext {
  /** what is sent: `pathname + hash` */
  route: string;
  featureId: string;
  title: { tr: string; en: string };
  entity?: { kind: "room" | "booking" | "approval_request"; id: number };
}

const NAMED: readonly FeatureEntry[] = FEATURE_INDEX.filter((e) => e.kind !== "control");

function byRoute(route: string, can: Can): FeatureEntry | undefined {
  const hits = NAMED.filter((e) => e.route === route && canOpenFeature(e, can));
  return hits.find((e) => e.kind === "page") ?? hits[0];
}

const positive = (raw: string | null | undefined): number | null => {
  const n = Number(raw);
  return raw && Number.isInteger(n) && n >= 1 ? n : null;
};

const REQUEST_PAGES = new Set(["/approvals", "/moderation/me", "/my-bookings"]);

function entityFor(path: string, search: string): PageContext["entity"] {
  const room = /^\/rooms\/(\d+)$/.exec(path);
  if (room) {
    const id = positive(room[1]);
    return id ? { kind: "room", id } : undefined;
  }
  const q = new URLSearchParams(search);
  if (path === "/bookings") {
    const id = positive(q.get("room"));
    if (id) return { kind: "room", id };
  }
  if (REQUEST_PAGES.has(path)) {
    const id = positive(q.get("request"));
    if (id) return { kind: "approval_request", id };
  }
  return undefined;
}

/** The chip's page for a location, or null (unknown page, not the person's, or a route the server would refuse). */
export function pageContextFor(loc: { pathname: string; hash: string; search: string }, can: Can): PageContext | null {
  const route = `${loc.pathname}${loc.hash}`;
  if (!loc.pathname.startsWith("/") || route.length > 200) return null;
  const path = loc.pathname.replace(/\/+$/, "") || "/";
  let entry = loc.hash ? byRoute(`${path}${loc.hash}`, can) : undefined;
  for (let p = path; !entry && p.length > 1; p = p.slice(0, Math.max(p.lastIndexOf("/"), 0))) entry = byRoute(p, can);
  if (!entry) return null;
  const entity = entityFor(path, loc.search);
  return { route, featureId: entry.id, title: entry.title, ...(entity ? { entity } : {}) };
}

/** The wire shape of `POST /helper/turn` `context` (null when it would not pass the server's rules). */
export function toTurnContext(page: PageContext): TurnContext | null {
  const r = TurnContext.safeParse({ route: page.route, ...(page.entity ? { entity_kind: page.entity.kind, entity_id: page.entity.id } : {}) });
  return r.success ? r.data : null;
}

const subscribe = (fn: () => void) => {
  window.addEventListener("hashchange", fn);
  window.addEventListener("popstate", fn);
  return () => {
    window.removeEventListener("hashchange", fn);
    window.removeEventListener("popstate", fn);
  };
};
const SEP = "\u0000";
const snapshot = () => `${window.location.hash}${SEP}${window.location.search}`;
const serverSnapshot = () => SEP;

/** The page the person is on now (re-read on a route change and on `hashchange` / back / forward). */
export function usePageContext(): PageContext | null {
  const pathname = usePathname();
  const { can } = usePermissions();
  const [hash = "", search = ""] = useSyncExternalStore(subscribe, snapshot, serverSnapshot).split(SEP);
  return pathname ? pageContextFor({ pathname, hash, search }, can) : null;
}

export function PageContextChip({ page, onRemove }: { page: PageContext; onRemove: () => void }) {
  const { t, locale } = useI18n();
  const title = page.title[locale] || page.title.tr;
  return (
    <div data-testid="helper-context-chip" className="inline-flex max-w-full items-center gap-0.5 self-start rounded-full bg-fill-2 pl-3 edge-hairline">
      <span className="min-w-0 truncate type-footnote text-label-1">{t("helper.context.chip", { page: title })}</span>
      <IconButton size="sm" label={t("helper.context.remove", { page: title })} onClick={onRemove} className="shrink-0 rounded-full text-label-3" data-testid="helper-context-remove">
        <X aria-hidden />
      </IconButton>
    </div>
  );
}
