"use client";

import { Bell, Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useRuns } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { useUiStore } from "@/stores/ui";
import { ALL_NAV_ITEMS } from "./nav-config";
import { UserMenu } from "./user-menu";

const SEGMENT_LABELS: Record<string, MessageKey> = {
  dashboard: "nav.dashboard",
  import: "nav.import",
  requests: "nav.requests",
  generate: "nav.generate",
  timetable: "nav.timetable",
  runs: "nav.runs",
  rooms: "nav.rooms",
  settings: "nav.settings",
};

export function useBreadcrumbs(): { href: string; label: string; current: boolean }[] {
  const pathname = usePathname();
  const { t } = useI18n();
  const parts = pathname.split("/").filter(Boolean);
  return parts.map((seg, i) => {
    const href = `/${parts.slice(0, i + 1).join("/")}`;
    const key = SEGMENT_LABELS[seg];
    const label = key ? t(key) : /^\d+$/.test(seg) ? `#${seg}` : seg;
    return { href, label, current: i === parts.length - 1 };
  });
}

export function TopBar() {
  const { t } = useI18n();
  const setDrawerOpen = useUiStore((s) => s.setDrawerOpen);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const crumbs = useBreadcrumbs();
  const runs = useRuns();
  const recent = runs.data?.slice(0, 5) ?? [];
  const unread = recent.filter((r) => r.status === "RUNNING" || r.status === "QUEUED").length;
  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur-sm sm:px-6 lg:px-8">
      <Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label={t("nav.menu")} onClick={() => setDrawerOpen(true)} data-testid="open-drawer">
        <Menu />
      </Button>
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-1 text-sm">
          {crumbs.map((c, i) => (
            <Fragment key={c.href}>
              {i > 0 ? <li aria-hidden className="text-muted-foreground">›</li> : null}
              <li className={i < crumbs.length - 2 ? "hidden md:block" : ""}>
                {c.current ? (
                  <span aria-current="page" className="font-medium">{c.label}</span>
                ) : (
                  <Link href={c.href} className="text-muted-foreground hover:text-foreground">{c.label}</Link>
                )}
              </li>
            </Fragment>
          ))}
        </ol>
      </nav>
      <Button variant="outline" size="sm" className="hidden gap-2 text-muted-foreground sm:inline-flex" onClick={() => setPaletteOpen(true)} data-testid="open-palette">
        <Search className="size-3.5" /> <span className="pr-4">{t("nav.search")}</span>
        <kbd className="rounded border bg-muted px-1 font-mono text-[10px]">{t("nav.searchHint")}</kbd>
      </Button>
      <Button variant="ghost" size="icon-sm" className="sm:hidden" aria-label={t("nav.search")} onClick={() => setPaletteOpen(true)}>
        <Search />
      </Button>
      <Popover>
        <PopoverTrigger
          render={
            <Button variant="ghost" size="icon-sm" aria-label={t("nav.notifications")} className="relative">
              <Bell />
              {unread > 0 ? <span className="absolute top-1 right-1 size-1.5 rounded-full bg-primary" aria-hidden /> : null}
            </Button>
          }
        />
        <PopoverContent align="end" className="w-80 p-2">
          <p className="px-2 py-1 text-xs font-medium uppercase text-muted-foreground">{t("nav.runs")}</p>
          <ul className="space-y-0.5">
            {recent.length === 0 ? <li className="px-2 py-1.5 text-sm text-muted-foreground">{t("common.noData")}</li> : null}
            {ALL_NAV_ITEMS.length && recent.map((r) => (
              <li key={r.id}>
                <Link href={`/runs/${r.id}`} className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                  <span className="font-mono">#{r.id} · {r.term_code}</span>
                  <span className="text-xs text-muted-foreground">{t(`runs.status.${r.status}`)}{r.status === "RUNNING" ? ` ${r.progress}%` : ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </PopoverContent>
      </Popover>
      <UserMenu compact />
    </header>
  );
}
