"use client";

import { CalendarDays, Inbox, LayoutDashboard, MoreHorizontal, PlayCircle, Search } from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { BareButton } from "./bare-button";
import { useUiStore } from "@/stores/ui";
import { ADMIN_NAV_ITEMS } from "@/components/admin/nav-items";
import { QUICK_RESERVE_ITEM } from "./nav-config";
import { usePermissions } from "@/lib/api/shell-extra";
import { isActive, navTestId, useNavBadges } from "./sidebar";
import { tourAnchorFor } from "@/components/welcome";

type Tab = { href: string; labelKey: MessageKey; icon: typeof LayoutDashboard; badge?: "needsReview"; permission?: string | string[] };

const TABS: Tab[] = [
  { href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, permission: "planning.view" },
  { href: "/requests", labelKey: "nav.requests", icon: Inbox, badge: "needsReview", permission: "planning.view" },
  { href: "/generate", labelKey: "nav.generate", icon: PlayCircle, permission: "planning.edit" },
  // the timetable reads GET /terms and /runs (planning.view): room.view alone answers 403 there (wave1 crawler)
  { href: "/timetable", labelKey: "nav.timetable", icon: CalendarDays, permission: "planning.view" },
];

const PILL = "pointer-events-none absolute inset-0 -z-10 rounded-full bg-(--mat-thick) glass-edge";
/** one equal column per tab; 48 px tall (≥ 44 px target) with the label always shown (review §3 "Mobile tab bar") */
/** mobile-a fix 14: below 360 px the items lose their side padding (and the search circle moves to the top bar). The
 * threshold is in rem (22.5rem = 360 px at the default text size), so at 125–200 % text a phone gets the same room.
 * mobile-a fix 4: on a short landscape screen (≤ 500 px tall) an item is one 44 px row, label beside the icon. */
/* F-MA-2 / F-MB-3 (fix-b-2026-10-18): no side padding at any width (the label gets the whole column: 58 px at 390), and
 * the 44 px minimum stays 44 px at a 32 px root (min(2.75rem, 44px)), so five items never push the bar sideways. */
const ITEM = "relative isolate flex min-h-12 w-full min-w-[min(2.75rem,44px)] flex-col items-center justify-center gap-0.5 rounded-full px-0 [@media(max-height:500px)]:min-h-11 [@media(max-height:500px)]:flex-row [@media(max-height:500px)]:gap-1.5";
/** T-R2-04 (R2-A-01, R2-S-07): the label never runs into its neighbour. F-MA-2 (fix-b-2026-10-18): it is never cut
 *  off either (MOBILE.md M-09: no ellipsis at 320 or 390): a two-word label takes two centred lines, a long word breaks
 *  (hyphenated where the browser can) instead of ending in "…"; the tab-only words are ≤ 8 letters. */
const LABEL = "type-caption min-w-0 max-w-full text-center line-clamp-2 [overflow-wrap:anywhere] hyphens-auto";
/** the glyph box: 20 px icons (tokens §A3) on one line for every tab, the detached search included */
const ICON = "relative flex [&_svg]:size-5 [&_svg]:stroke-[1.75]";
/**
 * Tab-bar-only labels (nav.tab.*): a 390 px phone gives each of four or five columns 59–74 px, so the sidebar words
 * ("Rezervasyonlar", "Rezervasyonlarım") overlapped (T-R2-04). The sidebar, ⌘K and the crumbs keep the full words.
 */
const TAB_LABELS: Readonly<Record<string, MessageKey>> = {
  "/bookings": "nav.tab.bookings",
  "/my-bookings": "nav.tab.myBookings",
  "/find-room": "nav.tab.findRoom",
  "/approvals": "nav.tab.approvals",
  "/moderation/me": "nav.tab.myRequests",
  "/reserve": "nav.tab.reserve",
  // F-MA-2: the planner's bar; Turkish keeps "Özet" / "Çizelge", English gets 8-letter words for 58 px columns
  "/dashboard": "nav.tab.dashboard",
  "/timetable": "nav.tab.timetable",
};

/** routes whose screen carries its own bottom bar (studio-bottom-bar, the wizard's step capsule) */
const OWN_BOTTOM_BAR = ["/generate", "/programs/new"] as const;
export const hasOwnBottomBar = (pathname: string | null) => !!pathname && OWN_BOTTOM_BAR.some((p) => pathname === p || pathname.startsWith(`${p}/`));

export function TabBar() {
  const { t } = useI18n();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const reduce = useReduce();
  const badges = useNavBadges();
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const setDrawerOpen = useUiStore((s) => s.setDrawerOpen);
  const hydrated = useHydrated();
  const morph = reduce ? { duration: 0 } : springs.glassMorph;
  const { can } = usePermissions();
  // a teacher has no planning tabs: the bookings entries (admin/nav-items) take their place; a linked academician
  // (Taleplerim, /moderation/me: hidden from planners) gets it as a tab too (T-R1-06, R1-A-31)
  const planning = TABS.filter((tab) => can(tab.permission)).map((tab) => ({ ...tab, labelKey: TAB_LABELS[tab.href] ?? tab.labelKey }));
  // W3-SLOT: "Rezerve et" (/reserve, the quick reservation) is the first bookings tab for anyone who may book
  const bookings: Tab[] = [QUICK_RESERVE_ITEM, ...ADMIN_NAV_ITEMS.filter((i) => i.href.startsWith("/bookings") || i.href.startsWith("/my-bookings") || i.bookings)]
    .filter((i) => can(i.permission) && !("hideWith" in i && i.hideWith && can(i.hideWith)))
    .map((i) => ({ href: i.href, labelKey: TAB_LABELS[i.href] ?? i.labelKey, icon: i.icon }));
  const tabs = (planning.length >= 3 ? planning : [...bookings, ...planning]).slice(0, 4);
  const activeHref = tabs.find((tab) => isActive(pathname, search, tab.href))?.href;
  // on a page that is not a tab (Profil, Boş derslik bul, Kurulum…) "Diğer" is the current item (MOBILE.md M-09)
  const moreActive = !activeHref;

  const item = (key: string, label: string, icon: ReactNode, active: boolean, extra: { href?: string; onClick?: () => void; count?: number; testId?: string }) => {
    // the badge comes after the label in the DOM (MOBILE.md M-09: innerText starts with the label, T-R1-06);
    // it is drawn on the icon's top-right corner, anchored to the item's end so it never leaves the item's box
    // (T-R2-04, R2-M-13: "99+" ran past a 59 px column when it hung off the icon's centre)
    const content = (
      <>
        {active ? <motion.span layoutId="tab-pill" aria-hidden className={PILL} style={{ borderRadius: 999 }} transition={morph} /> : null}
        <span aria-hidden className={cn(ICON, active ? "text-tint-text" : "text-label-2")}>
          {icon}
        </span>
        <span aria-hidden data-slot="tab-label" className={cn(LABEL, active ? "font-semibold text-tint-text" : "text-label-2")}>
          {label}
        </span>
        {extra.count ? (
          <span aria-hidden className="absolute top-1 right-[max(0.125rem,calc(50%-1.75rem))] h-4 min-w-5 max-w-[calc(100%-0.25rem)] truncate rounded-full bg-status-warning px-1 text-center type-caption leading-4 font-semibold text-status-warning-fg tnum" data-testid="tab-badge">
            {extra.count > 99 ? "99+" : extra.count}
          </span>
        ) : null}
      </>
    );
    const cls = cn(ITEM, "outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-(--focus)");
    // the same box as the links (BareButton: no control height), so the More label sits on the other labels' baseline
    const buttonCls = cn(cls, "font-normal");
    const aria = extra.count ? `${label}, ${t("nav.needsReview", { count: extra.count })}` : label;
    return (
      <li key={key} className="flex min-w-0 list-none">
        {extra.href ? (
          <Link href={extra.href} aria-label={aria} aria-current={active ? "page" : undefined} className={cls} data-testid={extra.testId} data-tour={tourAnchorFor(extra.href)}>
            {content}
          </Link>
        ) : (
          <BareButton aria-label={aria} aria-current={active ? "page" : undefined} onClick={extra.onClick} className={buttonCls} data-testid={extra.testId}>
            {content}
          </BareButton>
        )}
      </li>
    );
  };

  // tabs depend on permissions and counts from queries: render after hydration only (no #418 mismatch)
  if (!hydrated) return null;
  // mobile audit B (2026-10-17): the Studio and the programme wizard have their own bottom step bar; with the tab bar
  // too, the two bars took about 200 px of a phone. The top bar carries the menu (drawer) and search there.
  if (hasOwnBottomBar(pathname)) return null;
  return (
    <div data-slot="tab-bar" className="pointer-events-none fixed inset-x-0 bottom-[max(0.75rem,env(safe-area-inset-bottom))] [@media(max-height:500px)]:bottom-[max(0.5rem,env(safe-area-inset-bottom))] z-40 flex items-center justify-center gap-2 pr-[max(0.75rem,env(safe-area-inset-right))] pl-[max(0.75rem,env(safe-area-inset-left))] lg:hidden">
      <LayoutGroup id="tab-bar">
        <nav aria-label={t("glass.shell.tabs")} data-glass="chrome" className="glass-chrome pointer-events-auto min-w-0 flex-1 rounded-full p-1 sm:max-w-md sm:flex-none [@media(max-height:500px)]:p-0">
          <ul className="grid grid-flow-col auto-cols-[minmax(0,1fr)] items-center gap-0.5">
            {tabs.map((tab) => item(tab.href, t(tab.labelKey), <tab.icon />, tab.href === activeHref, { href: tab.href, count: tab.badge ? badges[tab.badge] : undefined, testId: `tab-${navTestId(tab.href)}` }))}
            {item("more", t("glass.shell.more"), <MoreHorizontal />, moreActive, { onClick: () => setDrawerOpen(true), testId: "open-drawer" })}
          </ul>
        </nav>
      </LayoutGroup>
      {/* ui-alignment 2026-10-18: the detached search is a tab of its own (same capsule padding, ITEM box, 20 px icon and
          label), so its glyph sits on the tabs' icon line; the 48 px circle centred a 16 px glyph 12 px below them */}
      <BareButton aria-label={t("helper.trigger.name")} onClick={() => setPaletteOpen(true)} data-glass="chrome" className="glass-chrome pointer-events-auto shrink-0 rounded-full p-1 font-normal max-[22.5rem]:hidden [@media(max-height:500px)]:p-0" data-testid="open-palette-mobile">
        <span className={cn(ITEM, "px-3")}>
          <span aria-hidden className={cn(ICON, "text-label-2")}>
            <Search />
          </span>
          <span aria-hidden data-slot="tab-label" className={cn(LABEL, "text-label-2")}>
            {t("common.search")}
          </span>
        </span>
      </BareButton>
    </div>
  );
}
