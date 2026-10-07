"use client";

import { CalendarRange, ChevronsLeft, ChevronsRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useMeetings, useRuns } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { useHydrated } from "@/lib/use-hydrated";
import { LocaleToggle } from "./locale-toggle";
import { NAV_GROUPS, type NavItem } from "./nav-config";
import { TermSwitcher } from "./term-switcher";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

export function useNavBadges(): Record<NonNullable<NavItem["badge"]>, number> {
  const meetings = useMeetings({ status: "NEEDS_REVIEW", page_size: 1 });
  const runs = useRuns();
  return {
    needsReview: meetings.data?.total ?? 0,
    running: runs.data?.filter((r) => r.status === "RUNNING" || r.status === "QUEUED").length ?? 0,
  };
}

export function isActive(pathname: string, search: string, href: string): boolean {
  const [path, query] = href.split("?");
  if (query) return pathname === path && search.includes(query);
  if (path === "/settings") return pathname.startsWith(path) && !search.includes("tab=users");
  return pathname === path || pathname.startsWith(`${path}/`);
}

export function NavList({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const { t } = useI18n();
  const liveBadges = useNavBadges();
  const hydrated = useHydrated();
  const badges = hydrated ? liveBadges : { needsReview: 0, running: 0 };
  const reduce = useReducedMotion();
  return (
    <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 py-2">
      {NAV_GROUPS.map((group) => (
        <div key={group.labelKey} className="mb-3">
          {!collapsed ? <p className="mb-1 px-2 text-[11px] font-medium uppercase tracking-[0.02em] text-muted-foreground">{t(group.labelKey)}</p> : <div className="mx-2 mb-2 border-t" />}
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const active = isActive(pathname, search, item.href);
              const count = item.badge ? badges[item.badge] : 0;
              const label = t(item.labelKey);
              const aria = item.badge && count > 0 ? `${label}, ${t(item.badge === "needsReview" ? "nav.needsReview" : "nav.running", { count })}` : label;
              const link = (
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  aria-label={aria}
                  data-testid={`nav-${item.href.replace(/[/?=]/g, "-").replace(/^-/, "")}`}
                  className={cn(
                    "relative flex h-9 items-center gap-2.5 rounded-md px-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active ? (
                    <motion.span layoutId={reduce ? undefined : "nav-indicator"} transition={{ type: "spring", stiffness: 500, damping: 40 }} className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" aria-hidden />
                  ) : null}
                  <item.icon className="size-4 shrink-0" aria-hidden />
                  {!collapsed ? <span className="flex-1 truncate">{label}</span> : null}
                  {!collapsed && count > 0 ? (
                    <span className={cn("ml-auto inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold", item.badge === "running" ? "bg-primary-tint text-primary" : "bg-status-warning text-status-warning-fg")}>
                      {item.badge === "running" ? <span className="mr-1 size-1.5 animate-pulse rounded-full bg-primary" aria-hidden /> : null}
                      {count}
                    </span>
                  ) : null}
                  {collapsed && count > 0 ? <span className="absolute top-1 right-1 size-1.5 rounded-full bg-primary" aria-hidden /> : null}
                </Link>
              );
              return (
                <li key={item.href}>
                  {collapsed ? (
                    <Tooltip>
                      <TooltipTrigger render={link} />
                      <TooltipContent side="right">{aria}</TooltipContent>
                    </Tooltip>
                  ) : (
                    link
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);
  const { t } = useI18n();
  const reduce = useReducedMotion();
  return (
    <motion.aside
      aria-label="Sidebar"
      initial={false}
      animate={{ width: collapsed ? 56 : 240 }}
      transition={reduce ? { duration: 0 } : { duration: 0.2, ease: "easeOut" }}
      className="sticky top-0 hidden h-dvh shrink-0 flex-col border-r bg-sidebar lg:flex"
      data-collapsed={collapsed}
    >
      <div className={cn("flex h-14 items-center gap-2 border-b px-3", collapsed && "justify-center px-0")}>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <CalendarRange className="size-4" aria-hidden />
        </span>
        {!collapsed ? <span className="truncate font-semibold">{t("app.name")}</span> : null}
      </div>
      <div className="px-2 pt-2">
        <TermSwitcher collapsed={collapsed} />
      </div>
      <NavList collapsed={collapsed} />
      <div className={cn("border-t p-2", collapsed ? "flex flex-col items-center gap-1" : "space-y-2")}>
        <UserMenu collapsed={collapsed} />
        <div className={cn("flex items-center gap-1", collapsed ? "flex-col" : "justify-between")}>
          {!collapsed ? <LocaleToggle /> : null}
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <Tooltip>
              <TooltipTrigger
                render={
                  <button type="button" onClick={toggle} aria-label={collapsed ? t("nav.expand") : t("nav.collapse")} className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground" data-testid="sidebar-toggle">
                    {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
                  </button>
                }
              />
              <TooltipContent side="right">{collapsed ? t("nav.expand") : t("nav.collapse")} · ⌘B</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>
    </motion.aside>
  );
}
