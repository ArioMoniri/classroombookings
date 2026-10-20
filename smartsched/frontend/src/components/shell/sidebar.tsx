"use client";

import { ChevronDown, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Logo } from "@/components/brand";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { BareButton, IconButton } from "@/components/ui/button";
import { KbdHint } from "@/components/ui/kbd-hint";
import { SidebarGlass, SidebarGlassContent, SidebarGlassFooter, SidebarGlassHeader, SidebarGlassItem, SidebarGlassSection } from "@/components/ui/sidebar-glass";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useMeetings, useRuns } from "@/lib/api/hooks";
import { useApprovalInbox } from "@/lib/api/wave1";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { TINT_ONLY_OVER_SCENE, useTintOnlyChrome } from "./blur-budget";
import { visibleNavGroups, type NavItem } from "./nav-config";
import { TermSwitcher, useActiveTerm } from "./term-switcher";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";
import { ChecklistPill, NewBadge, tourAnchorFor } from "@/components/welcome";

/** Counts are scoped to the selected term (usability M14: the FINAL term showed Bahar's 231). */
export function useNavBadges(): Record<NonNullable<NavItem["badge"]>, number> {
  // planning counts only for planning.view (teachers would get a 403 toast on every page); the approvals
  // count only for designated approvers (approvals.decide)
  const { can } = usePermissions();
  const planner = can("planning.view");
  const { term } = useActiveTerm({ enabled: planner });
  const meetings = useMeetings(term ? { status: "NEEDS_REVIEW", term_id: term.id, page_size: 1 } : { status: "NEEDS_REVIEW", page_size: 1 }, { enabled: planner });
  const runs = useRuns(undefined, { enabled: planner });
  const inbox = useApprovalInbox("open", can("approvals.decide"));
  return {
    needsReview: meetings.data?.total ?? 0,
    running: runs.data?.filter((r) => r.status === "RUNNING" || r.status === "QUEUED").length ?? 0,
    approvals: inbox.data?.length ?? 0,
  };
}

export function isActive(pathname: string, search: string, href: string): boolean {
  const [path, query] = href.split("?");
  if (query) return pathname === path && search.includes(query);
  if (path === "/settings") return pathname.startsWith(path) && !search.includes("tab=users");
  // Setup is not also active on the screens with their own sidebar entry (UI/UX review: two active items)
  if (path === "/admin") return pathname === path || (pathname.startsWith(`${path}/`) && !pathname.startsWith("/admin/users"));
  return pathname === path || pathname.startsWith(`${path}/`);
}

/** the fewest "rarely used" rows worth a "Daha fazla" disclosure */
export const RARE_MIN = 3;

export const navTestId = (href: string) => `nav-${href.replace(/[/?=]/g, "-").replace(/^-/, "")}`;

/** Grouped navigation (SidebarGlass grammar): quiet sentence-case section labels, plain numerals, g-key hints. */
export function NavList({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const { t } = useI18n();
  const liveBadges = useNavBadges();
  const hydrated = useHydrated();
  const badges = hydrated ? liveBadges : { needsReview: 0, running: 0, approvals: 0 };
  const { can } = usePermissions();
  const groups = hydrated ? visibleNavGroups(can) : [];
  // PER-F07 (fix-h-2026-10-18): rarely used entries wait under each group's "Daha fazla" (open while one is the current
  // page); the icon rail keeps every entry, it has no room for a disclosure
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  return (
    <>
      {groups.map((group) => {
        // a disclosure that hides one or two rows saves nothing ("Daha fazla (1)"): only three or more wait under it
        const tagged = group.items.filter((i) => i.more);
        const rare = collapsed || tagged.length < RARE_MIN ? [] : tagged;
        const rareActive = rare.some((i) => isActive(pathname, search, i.href));
        const showRare = rareActive || !!opened[group.labelKey];
        const shown = rare.length === 0 ? group.items : group.items.filter((i) => !i.more || showRare);
        return (
        <SidebarGlassSection key={group.labelKey} title={collapsed ? undefined : t(group.labelKey)} aria-label={collapsed ? t(group.labelKey) : undefined}>
          {shown.map((item) => {
            const active = isActive(pathname, search, item.href);
            const count = item.badge ? badges[item.badge] : 0;
            const label = t(item.labelKey);
            const aria = item.badge && count > 0 ? `${label}, ${t(item.badge === "needsReview" ? "nav.needsReview" : item.badge === "approvals" ? "wave1.nav.approvalsOpen" : "nav.running", { count })}` : label;
            const props = {
              active,
              icon: collapsed && count > 0 ? (
                // the rail has no room for a number: a dot on the icon (the count is in the name and the tooltip)
                <span className="relative flex">
                  <item.icon aria-hidden />
                  <span aria-hidden data-testid="nav-dot" className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-tint ring-2 ring-(--mat-chrome-solid)" />
                </span>
              ) : (
                <item.icon aria-hidden />
              ),
              count: !collapsed && count > 0 ? count : undefined,
              hint: !collapsed && item.key ? <KbdHint keys={["G", item.key.toUpperCase()]} sequence thenLabel={t("glass.shell.then")} /> : undefined,
              "aria-label": aria,
              "data-testid": navTestId(item.href),
              "data-tour": tourAnchorFor(item.href),
              onClick: onNavigate,
              className: cn(collapsed && "mx-auto size-10 justify-center px-0"),
              children: collapsed ? <span className="sr-only">{label}</span> : (
                <>
                  {label}
                  <NewBadge href={item.href} />
                </>
              ),
            };
            if (!collapsed) return <SidebarGlassItem key={item.href} {...props} render={<Link href={item.href} />} />;
            // collapsed: the tooltip root has no DOM, so the <li> stays a direct child of the list
            return (
              <Tooltip key={item.href}>
                <SidebarGlassItem {...props} render={<TooltipTrigger render={<Link href={item.href} />} />} />
                <TooltipContent side="right">{aria}</TooltipContent>
              </Tooltip>
            );
          })}
          {rare.length && !rareActive ? (
            <li>
              <BareButton
                aria-expanded={showRare}
                onClick={() => setOpened((o) => ({ ...o, [group.labelKey]: !o[group.labelKey] }))}
                className="flex h-8 w-full items-center gap-2.5 rounded-[10px] px-2.5 type-footnote font-medium text-label-2 transition-colors duration-(--dur-fast) hover:bg-fill-3 hover:text-label-1 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus) pointer-coarse:min-h-11"
                data-testid={`nav-more-${group.labelKey.replace(/\./g, "-")}`}
              >
                <ChevronDown aria-hidden className={cn("size-4 shrink-0 transition-transform", showRare && "rotate-180")} />
                {showRare ? t("nav.less") : t("nav.more", { n: rare.length })}
              </BareButton>
            </li>
          ) : null}
        </SidebarGlassSection>
        );
      })}
    </>
  );
}

/** Desktop sidebar: floating chrome glass inset 8 px from the window (liquid-glass.md §16.1). */
const NARROW = "(max-width: 1279.98px)";
function subscribeNarrow(onChange: () => void) {
  if (typeof window === "undefined" || !window.matchMedia) return () => undefined;
  const mql = window.matchMedia(NARROW);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}
/** 1024-1279 px: the sidebar is an icon rail (UI/UX review §3: 264 px left too little room for the grids). */
function useNarrowDesktop(): boolean {
  return useSyncExternalStore(subscribeNarrow, () => window.matchMedia?.(NARROW).matches ?? false, () => false);
}

export function Sidebar() {
  const narrow = useNarrowDesktop();
  const stored = useUiStore((s) => s.sidebarCollapsed);
  const collapsed = stored || narrow;
  const toggle = useUiStore((s) => s.toggleSidebar);
  const { t } = useI18n();
  const toggleLabel = collapsed ? t("nav.expand") : t("nav.collapse");
  const tintOnly = useTintOnlyChrome();
  // the dashboard is planning data: people without planning.view go home to their bookings (no 403)
  const { can, me } = usePermissions();
  const hydrated = useHydrated();
  const home = hydrated && me && !can("planning.view") ? "/bookings" : "/dashboard";
  // the current page's row is always in view (on /admin at 900 px tall it sat below the fold of the nav list);
  // centred, so the checklist card that mounts in the footer afterwards cannot cover it again
  const content = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  useEffect(() => {
    if (!hydrated) return;
    // the nav list scrolls itself (never the page): the row is brought to the list's middle, again when the list
    // changes size in the first two seconds (the checklist card and the "Daha fazla" rows mount after the first frame)
    const list = content.current;
    if (!list) return;
    const centre = () => {
      const row = list.querySelector<HTMLElement>('[aria-current="page"]');
      if (!row) return;
      const top = row.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
      list.scrollTop = Math.max(0, top - (list.clientHeight - row.offsetHeight) / 2);
    };
    const id = window.requestAnimationFrame(centre);
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(centre);
    ro?.observe(list);
    for (const group of list.children) ro?.observe(group);
    const stop = window.setTimeout(() => ro?.disconnect(), 2000);
    return () => {
      window.cancelAnimationFrame(id);
      window.clearTimeout(stop);
      ro?.disconnect();
    };
  }, [pathname, hydrated, collapsed, me]);
  return (
    <aside aria-label={t("glass.shell.sidebar")} data-collapsed={collapsed} data-chrome={tintOnly ? "tint" : "glass"} className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col lg:flex", collapsed ? "w-[72px]" : "w-[264px]", tintOnly && TINT_ONLY_OVER_SCENE)}>
      <SidebarGlass aria-label={t("glass.shell.primary")} className="flex-1">
        <SidebarGlassHeader className={cn(collapsed && "flex-col px-2")}>
          <Link href={home} className="flex min-w-0 flex-1 items-center gap-2 rounded-lg outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" aria-label={t("app.name")}>
            <Logo variant="mark" size={28} decorative />
            {!collapsed ? <span className="type-headline truncate text-label-1">{t("app.name")}</span> : null}
          </Link>
          {/* the rail cannot open below 1280 px, so the toggle only shows where it does something */}
          {narrow ? null : (
            <Tooltip>
              <TooltipTrigger
                render={
                  <IconButton size="sm" label={toggleLabel} title="" onClick={toggle} aria-expanded={!collapsed} className="text-label-2 hover:text-label-1" data-testid="sidebar-toggle">
                    {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
                  </IconButton>
                }
              />
              <TooltipContent side="right">
                {toggleLabel} <KbdHint keys={["mod", "B"]} className="ml-1" />
              </TooltipContent>
            </Tooltip>
          )}
        </SidebarGlassHeader>
        <div className={cn("px-2 pb-2", collapsed && "px-1.5")}>
          <TermSwitcher collapsed={collapsed} />
        </div>
        <SidebarGlassContent ref={content}>
          <NavList collapsed={collapsed} />
        </SidebarGlassContent>
        <SidebarGlassFooter className={cn(collapsed && "items-center gap-2")}>
          <ChecklistPill collapsed={collapsed} />
          {/* the account and its appearance switch are one group; in the rail both are 40 px circles with tooltips */}
          <div role="group" aria-label={t("nav.account")} className={cn("flex items-center gap-1", collapsed && "flex-col rounded-2xl bg-fill-3 p-1")}>
            <div className={cn("min-w-0", !collapsed && "flex-1")}>
              <UserMenu collapsed={collapsed} />
            </div>
            <ThemeToggle tooltipSide={collapsed ? "right" : "top"} className={cn(collapsed && "size-10")} />
          </div>
        </SidebarGlassFooter>
      </SidebarGlass>
    </aside>
  );
}
