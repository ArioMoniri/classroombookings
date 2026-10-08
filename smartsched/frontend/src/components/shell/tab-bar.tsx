"use client";

import { CalendarDays, Inbox, LayoutDashboard, MoreHorizontal, PlayCircle, Search } from "lucide-react";
import { AnimatePresence, LayoutGroup, motion, useMotionValueEvent, useScroll } from "motion/react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { ADMIN_NAV_ITEMS } from "@/components/admin/nav-items";
import { usePermissions } from "@/lib/api/shell-extra";
import { isActive, navTestId, useNavBadges } from "./sidebar";

type Tab = { href: string; labelKey: MessageKey; icon: typeof LayoutDashboard; badge?: "needsReview"; permission?: string | string[] };

const TABS: Tab[] = [
  { href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, permission: "planning.view" },
  { href: "/requests", labelKey: "nav.requests", icon: Inbox, badge: "needsReview", permission: "planning.view" },
  { href: "/generate", labelKey: "nav.generate", icon: PlayCircle, permission: "planning.edit" },
  { href: "/timetable", labelKey: "nav.timetable", icon: CalendarDays, permission: ["planning.view", "room.view"] },
];

const PILL = "pointer-events-none absolute inset-0 -z-10 rounded-full bg-(--mat-thick) shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline)]";
const ITEM = "relative isolate flex min-h-11 min-w-11 flex-col items-center justify-center gap-0.5 rounded-full px-3";
const LABEL = "text-[11px] font-medium";
/** search orb (52) + gap-2 (8) */
const BESIDE_BAR = 52 + 8;

/**
 * Does the full bar (every label shown) fit next to the search orb? Measured on an invisible copy so the
 * answer does not depend on the bar's current state (no flip-flop), and re-measured when the labels change
 * (language, permissions, web font load) or the window resizes. English at 360–450 px does not fit.
 */
function useFullBarFits(mounted: boolean): { fits: boolean; ghostRef: React.RefObject<HTMLUListElement | null>; rowRef: React.RefObject<HTMLDivElement | null> } {
  const ghostRef = useRef<HTMLUListElement | null>(null);
  const rowRef = useRef<HTMLDivElement | null>(null);
  const [fits, setFits] = useState(true);
  // before paint: a bar that does not fit is minimised from its first frame (the bar mounts after hydration)
  useLayoutEffect(() => {
    const ghost = ghostRef.current;
    const row = rowRef.current;
    if (!ghost || !row) return;
    // clientWidth includes the row's px-3
    const check = () => setFits(ghost.offsetWidth + BESIDE_BAR <= row.clientWidth - 24);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(ghost);
    ro.observe(row);
    return () => ro.disconnect();
  }, [mounted]);
  return { fits, ghostRef, rowRef };
}

/**
 * Phones and small tablets (< lg): an iOS 26 floating tab bar (motion pattern §3). The bar minimises while
 * the page scrolls down (inactive labels collapse, the bar narrows) and re-expands on scroll up; the active
 * pill morphs between tabs with springs.glassMorph. Search is a separate glass orb (Apple Music, Fey dock).
 * Reduced motion: never minimises, pill jumps. The pill is a fill, not a second glass (rule G2).
 */
export function TabBar() {
  const { t } = useI18n();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const reduce = useReduce();
  const badges = useNavBadges();
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const setDrawerOpen = useUiStore((s) => s.setDrawerOpen);
  const { scrollY } = useScroll();
  const [compact, setCompact] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => {
    if (reduce) return;
    const prev = scrollY.getPrevious() ?? 0;
    if (y < 24) setCompact(false);
    else if (y - prev > 6) setCompact(true);
    else if (prev - y > 6) setCompact(false);
  });
  const hydrated = useHydrated();
  const { fits, ghostRef, rowRef } = useFullBarFits(hydrated);
  // scrolled down, or too narrow for every label: only the active tab keeps its label
  const minimised = compact || !fits;
  const morph = reduce ? { duration: 0 } : springs.glassMorph;
  const { can } = usePermissions();
  // a teacher has no planning tabs: the bookings entries (admin/nav-items) take their place
  const planning = TABS.filter((tab) => can(tab.permission));
  const bookings: Tab[] = ADMIN_NAV_ITEMS.filter((i) => i.href.startsWith("/bookings") || i.href.startsWith("/my-bookings")).filter((i) => can(i.permission)).map((i) => ({ href: i.href, labelKey: i.labelKey, icon: i.icon }));
  const tabs = (planning.length >= 3 ? planning : [...bookings, ...planning]).slice(0, 4);
  const activeHref = tabs.find((tab) => isActive(pathname, search, tab.href))?.href;

  const item = (key: string, label: string, icon: ReactNode, active: boolean, extra: { href?: string; onClick?: () => void; count?: number; testId?: string }) => {
    const content = (
      <>
        {active ? <motion.span layoutId="tab-pill" aria-hidden className={PILL} style={{ borderRadius: 999 }} transition={morph} /> : null}
        <span aria-hidden className={cn("relative flex [&_svg]:size-5 [&_svg]:stroke-[1.75]", active ? "text-tint-text" : "text-label-2")}>
          {icon}
          {extra.count ? <span className="absolute -top-1 -right-2 min-w-4 rounded-full bg-status-warning px-1 text-center text-[10px] leading-4 font-semibold text-status-warning-fg tabular-nums">{extra.count > 99 ? "99+" : extra.count}</span> : null}
        </span>
        <AnimatePresence initial={false} mode="popLayout">
          {!minimised || active ? (
            <motion.span key="label" aria-hidden initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: tween.fadeOut }} transition={tween.fadeIn} className={cn(LABEL, active ? "text-tint-text" : "text-label-2")}>
              {label}
            </motion.span>
          ) : null}
        </AnimatePresence>
      </>
    );
    const cls = cn(ITEM, "outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)");
    const aria = extra.count ? `${label}, ${t("nav.needsReview", { count: extra.count })}` : label;
    return (
      <motion.li key={key} layout="position" transition={morph} className="list-none">
        {extra.href ? (
          <Link href={extra.href} aria-label={aria} aria-current={active ? "page" : undefined} className={cls} data-testid={extra.testId}>
            {content}
          </Link>
        ) : (
          <button type="button" aria-label={aria} onClick={extra.onClick} className={cls} data-testid={extra.testId}>
            {content}
          </button>
        )}
      </motion.li>
    );
  };

  // tabs depend on permissions and counts from queries: render after hydration only (no #418 mismatch)
  if (!hydrated) return null;
  return (
    <div ref={rowRef} className="pointer-events-none fixed inset-x-0 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 flex items-end justify-center gap-2 px-3 lg:hidden">
      {/* invisible full-width copy for useFullBarFits (no glass, not in the accessibility tree) */}
      <ul ref={ghostRef} aria-hidden className="invisible absolute top-0 left-0 flex w-max items-center gap-0.5 p-1">
        {[...tabs.map((tab) => [tab.href, t(tab.labelKey)]), ["more", t("glass.shell.more")]].map(([key, label]) => (
          <li key={key} className={ITEM}>
            <span className="size-5" />
            <span className={LABEL}>{label}</span>
          </li>
        ))}
      </ul>
      <LayoutGroup id="tab-bar">
        <motion.nav aria-label={t("glass.shell.tabs")} layout transition={morph} style={{ borderRadius: 999 }} data-compact={minimised} data-glass="chrome" className="glass-chrome pointer-events-auto p-1">
          <ul className="flex items-center gap-0.5">
            {tabs.map((tab) => item(tab.href, t(tab.labelKey), <tab.icon />, tab.href === activeHref, { href: tab.href, count: tab.badge ? badges[tab.badge] : undefined, testId: `tab-${navTestId(tab.href)}` }))}
            {item("more", t("glass.shell.more"), <MoreHorizontal />, false, { onClick: () => setDrawerOpen(true), testId: "open-drawer" })}
          </ul>
        </motion.nav>
      </LayoutGroup>
      <button type="button" onClick={() => setPaletteOpen(true)} aria-label={t("nav.search")} data-glass="chrome" className="glass-chrome pointer-events-auto flex size-[52px] shrink-0 items-center justify-center rounded-full text-label-1 outline-none focus-visible:outline-2 focus-visible:outline-(--focus) [&_svg]:size-5 [&_svg]:stroke-[1.75]" data-testid="open-palette-mobile">
        <Search aria-hidden />
      </button>
    </div>
  );
}
