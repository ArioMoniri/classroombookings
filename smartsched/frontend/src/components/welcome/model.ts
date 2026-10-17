/**
 * Pure rules of the welcome guide (spec §5.9, §4.3): which cards the sheet shows, which tour steps run, which
 * checklist items are listed, and how admin overrides and placeholders render. No React here, so vitest covers it.
 */
import type { LucideIcon } from "lucide-react";
import type { ChecklistItem, SheetCard, TourStep, WelcomeState } from "@/lib/api/welcome";
import { type Audience, isAudience } from "@/lib/api/welcome";
import { CARDS, ITEMS, STEPS, cardDef, itemDef, orderAudiences, primaryOf } from "./content";

export const MAX_CARDS = 5;
export const MAX_STEPS = 7;
export const MAX_ITEMS = 6;

export interface ResolvedCard {
  key: string;
  audience: Audience;
  href: string;
  icon: LucideIcon;
  /** an "Ayrıca" card of a secondary audience */
  also: boolean;
  overrides: Record<string, string>;
}

export interface SheetModel {
  primary: Audience;
  kind: "sheet" | "delta";
  updated: boolean;
  cards: ResolvedCard[];
  overrides: Record<string, string>;
}

/** Audiences that only add to the primary ("Ayrıca" card, extra steps). */
const SECONDARY_ONLY: readonly Audience[] = ["approver", "dept_admin"];

function resolveCard(c: SheetCard, audiences: Audience[], primary: Audience): ResolvedCard | null {
  const pool = isAudience(c.audience) ? [c.audience] : [primary, ...audiences.filter((a) => a !== primary)];
  for (const a of pool) {
    const def = cardDef(a, c.key);
    if (def) return { key: c.key, audience: a, href: c.href || def.href, icon: def.icon, also: a !== primary, overrides: c.overrides ?? {} };
  }
  return null;
}

/** The catalog's cards: the primary's (max 4 when there are secondaries), then one "Ayrıca" card per secondary. */
export function catalogCards(primary: Audience, audiences: readonly Audience[]): ResolvedCard[] {
  const also: ResolvedCard[] = audiences
    .filter((a) => a !== primary)
    .flatMap((a) => CARDS[a].slice(0, 1).map((d) => ({ key: d.key, audience: a, href: d.href, icon: d.icon, also: true, overrides: {} })));
  // the primary keeps at most 4 cards next to "Ayrıca" cards (5 alone), and always at least one
  const ownMax = also.length ? Math.max(1, Math.min(4, MAX_CARDS - also.length)) : MAX_CARDS;
  const own: ResolvedCard[] = CARDS[primary].slice(0, ownMax).map((d) => ({ key: d.key, audience: primary, href: d.href, icon: d.icon, also: false, overrides: {} }));
  return [...own, ...also].slice(0, MAX_CARDS);
}

/**
 * The sheet for a payload. `kind="delta"` (role change, T3): only the new audiences' cards, titled
 * "Yeni yetkileriniz var". `previewAudience` (admin "Önce kendinizde deneyin") renders that audience alone.
 */
export function buildSheet(state: WelcomeState | undefined, opts: { kind?: "sheet" | "delta"; deltaAudiences?: readonly string[]; previewAudience?: Audience; previewOverrides?: Record<string, string> } = {}): SheetModel | null {
  if (opts.previewAudience) {
    const a = opts.previewAudience;
    const ov = opts.previewOverrides ?? {};
    const cards = catalogCards(a, [a]).map((c) => ({ ...c, overrides: pick(ov, `cards.${c.key}.`) }));
    return { primary: a, kind: "sheet", updated: false, cards, overrides: { title: ov.title ?? "", lead: ov.lead ?? "" } };
  }
  if (!state) return null;
  const audiences = orderAudiences(state.audiences);
  const primary = primaryOf(state.primary, audiences);
  if (!primary) return null;
  const kind = opts.kind ?? (state.show?.kind === "delta" ? "delta" : "sheet");
  const overrides = state.sheet.overrides ?? {};
  if (kind === "delta") {
    const fresh = orderAudiences(opts.deltaAudiences ?? state.show?.audiences ?? []);
    const cards: ResolvedCard[] = [];
    for (const a of fresh) for (const d of CARDS[a]) cards.push({ key: d.key, audience: a, href: d.href, icon: d.icon, also: a !== primary, overrides: {} });
    // the server's cards (with overrides) win for the same key
    const server = state.sheet.cards.map((c) => resolveCard(c, audiences, primary)).filter((c): c is ResolvedCard => !!c && fresh.includes(c.audience));
    const merged = cards.map((c) => server.find((s) => s.key === c.key && s.audience === c.audience) ?? c);
    return { primary, kind, updated: false, cards: merged.slice(0, MAX_CARDS), overrides };
  }
  const fromServer = state.sheet.cards.map((c) => resolveCard(c, audiences, primary)).filter((c): c is ResolvedCard => !!c);
  const cards = fromServer.length ? fromServer.slice(0, MAX_CARDS) : catalogCards(primary, audiences.length ? audiences : [primary]);
  return { primary, kind, updated: state.sheet.updated, cards, overrides };
}

function pick(map: Record<string, string>, prefix: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(map)) if (k.startsWith(prefix)) out[k.slice(prefix.length)] = v;
  return out;
}

/* ------------------------------------------------------------------------------------------ tour */

export interface ResolvedStep {
  anchor: string;
  route?: string;
  interactive: boolean;
  audience: Audience;
}

/** The primary's steps plus the secondaries' extra steps (approver, department admin), max 7, no repeated anchor. */
export function buildSteps(state: WelcomeState | undefined, opts: { previewAudience?: Audience } = {}): ResolvedStep[] {
  if (opts.previewAudience) return STEPS[opts.previewAudience].map((s) => ({ anchor: s.anchor, route: s.route, interactive: !!s.interactive, audience: opts.previewAudience! }));
  if (!state) return [];
  const audiences = orderAudiences(state.audiences);
  const primary = primaryOf(state.primary, audiences);
  if (!primary) return [];
  const fromServer: TourStep[] = state.tour.steps;
  const raw: ResolvedStep[] = fromServer.length
    ? fromServer.map((s) => ({ anchor: s.anchor, route: s.route ?? undefined, interactive: !!s.interactive, audience: isAudience(s.audience) ? s.audience : primary }))
    : [
        ...STEPS[primary].map((s) => ({ anchor: s.anchor, route: s.route, interactive: !!s.interactive, audience: primary })),
        ...audiences
          .filter((a) => a !== primary && SECONDARY_ONLY.includes(a))
          .flatMap((a) => STEPS[a].map((s) => ({ anchor: s.anchor, route: s.route, interactive: !!s.interactive, audience: a }))),
      ];
  const seen = new Set<string>();
  return raw.filter((s) => (seen.has(s.anchor) ? false : (seen.add(s.anchor), true))).slice(0, MAX_STEPS);
}

/* ------------------------------------------------------------------------------------------ checklist */

export interface ResolvedItem {
  key: string;
  href: string;
  done: boolean;
  manual: boolean;
}
export interface ChecklistModel {
  items: ResolvedItem[];
  done: number;
  total: number;
  hidden: boolean;
  next: ResolvedItem | null;
  allDone: boolean;
}

/** The server's items (its `done` always wins), max 6; the catalog only fills in a missing href / manual flag. */
export function buildChecklist(state: WelcomeState | undefined, localDone: ReadonlySet<string> = new Set()): ChecklistModel | null {
  if (!state) return null;
  const audiences = orderAudiences(state.audiences);
  const primary = primaryOf(state.primary, audiences);
  let source: ChecklistItem[] = state.checklist.items;
  if (!source.length && primary) {
    const keys = [...ITEMS[primary], ...audiences.filter((a) => a !== primary).flatMap((a) => ITEMS[a])];
    const seen = new Set<string>();
    source = keys.filter((i) => (seen.has(i.key) ? false : (seen.add(i.key), true))).map((i) => ({ key: i.key, href: i.href, done: false, manual: !!i.manual }));
  }
  const items = source
    .map((i) => {
      const def = itemDef(i.key);
      return { key: i.key, href: i.href || def?.href || "/", done: i.done || localDone.has(i.key), manual: i.manual || !!def?.manual };
    })
    .slice(0, MAX_ITEMS);
  const done = items.filter((i) => i.done).length;
  const total = items.length;
  return { items, done, total, hidden: state.checklist.hidden, next: items.find((i) => !i.done) ?? null, allDone: total > 0 && done === total };
}

/* ------------------------------------------------------------------------------------------ text */

/**
 * An admin override (non-empty) or the product text. Placeholders `{ad}` / `{name}` and `{bölüm}` / `{department}`
 * are filled in both, so a Turkish override may use the English names and the reverse.
 */
export function fillPlaceholders(text: string, vars: { name: string; department: string }): string {
  return text.replace(/\{(ad|name)\}/gu, vars.name).replace(/\{(bölüm|department)\}/gu, vars.department);
}

/** Placeholders an admin text may use (spec §4.6). */
export const PLACEHOLDER_RE = /\{([^{}]*)\}/gu;
export const ALLOWED_PLACEHOLDERS = ["ad", "name", "bölüm", "department"];
export function badPlaceholders(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER_RE)].map((m) => m[1] ?? "").filter((p) => !ALLOWED_PLACEHOLDERS.includes(p));
}

/** The person's first name for `{ad}` (the server's `first_name`, else the first word of the full name). */
export function firstNameOf(state: WelcomeState | undefined, fullName: string | null | undefined): string {
  const fromServer = state?.first_name?.trim();
  if (fromServer) return fromServer;
  const words = (fullName ?? "").trim().split(/\s+/).filter(Boolean);
  // "Dr. A. Tekin": skip titles and initials, keep the first real word
  const real = words.find((w) => w.replace(/\./g, "").length > 1 && !/^(dr|doç|prof|öğr|arş|gör|uzm)\.?$/iu.test(w));
  return real ?? words[0] ?? "";
}
