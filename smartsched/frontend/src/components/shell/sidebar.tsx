"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Logo } from "@/components/brand";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
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
  return (
    <>
      {groups.map((group) => (
        <SidebarGlassSection key={group.labelKey} title={collapsed ? undefined : t(group.labelKey)} aria-label={collapsed ? t(group.labelKey) : undefined}>
          {group.items.map((item) => {
            const active = isActive(pathname, search, item.href);
            const count = item.badge ? badges[item.badge] : 0;
            const label = t(item.labelKey);
            const aria = item.badge && count > 0 ? `${label}, ${t(item.badge === "needsReview" ? "nav.needsReview" : item.badge === "approvals" ? "wave1.nav.approvalsOpen" : "nav.running", { count })}` : label;
            const props = {
              active,
              icon: <item.icon aria-hidden />,
              count: !collapsed && count > 0 ? count : undefined,
              hint: !collapsed && item.key ? <KbdHint keys={["G", item.key.toUpperCase()]} sequence thenLabel={t("glass.shell.then")} /> : undefined,
              "aria-label": aria,
              "data-testid": navTestId(item.href),
              onClick: onNavigate,
              className: cn(collapsed && "justify-center px-0"),
              children: collapsed ? <span className="sr-only">{label}</span> : label,
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
        </SidebarGlassSection>
      ))}
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
                  <button type="button" onClick={toggle} aria-label={toggleLabel} aria-expanded={!collapsed} className="inline-flex size-7 items-center justify-center rounded-full text-label-2 outline-hidden hover:bg-fill-2 hover:text-label-1 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="sidebar-toggle">
                    {collapsed ? <PanelLeftOpen className="size-4 stroke-[1.75]" /> : <PanelLeftClose className="size-4 stroke-[1.75]" />}
                  </button>
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
        <SidebarGlassContent>
          <NavList collapsed={collapsed} />
        </SidebarGlassContent>
        <SidebarGlassFooter className={cn(collapsed && "items-center")}>
          <div className={cn("flex items-center gap-1", collapsed && "flex-col")}>
            <div className="min-w-0 flex-1">
              <UserMenu collapsed={collapsed} />
            </div>
            <ThemeToggle />
          </div>
        </SidebarGlassFooter>
      </SidebarGlass>
    </aside>
  );
}
