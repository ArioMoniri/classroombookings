"use client";

import { Bell, Search } from "lucide-react";
import { motion, useMotionValueEvent, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useState, type ReactNode } from "react";
import { StatusBadge } from "@/components/common/status-badge";
import { runStatusBadge } from "@/components/runs/runs-list";
import { Button } from "@/components/ui/button";
import { KbdHint } from "@/components/ui/kbd-hint";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { useRuns } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { tween, useReduce, useReducedTransparency } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
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
  classes: "glass.shell.classes",
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

/**
 * Scroll-linked material (motion pattern §15): the backdrop blur is constant (one pass, never animated);
 * a chrome tint layer fades in over the first 48 px so the capsule "thickens" as content slides under it.
 * Reduced motion → a binary state at 8 px with a 180 ms fade. Reduced transparency → opaque at all times.
 */
export function useThickening() {
  const reduce = useReduce();
  const solid = useReducedTransparency();
  const { scrollY } = useScroll();
  const tint = useTransform(scrollY, [0, 48], [0.35, 1]);
  const titleOpacity = useTransform(scrollY, [24, 56], [0, 1]);
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 8));
  return { reduce, solid, tint, titleOpacity, scrolled };
}

/** A floating capsule whose material thickens with scroll. Decorative layers are aria-hidden and inert. */
export function ThickeningCapsule({ children, className, label }: { children: ReactNode; className?: string; label?: string }) {
  const { reduce, solid, tint, scrolled } = useThickening();
  return (
    <div role={label ? "toolbar" : undefined} aria-label={label} data-scrolled={scrolled} className={cn("relative isolate flex items-center gap-0.5 rounded-full p-1", className)}>
      <span aria-hidden className="pointer-events-none absolute inset-0 -z-20 rounded-[inherit] shadow-[var(--glass-edge),var(--ambient-1)] [backdrop-filter:var(--mat-chrome-filter)] [-webkit-backdrop-filter:var(--mat-chrome-filter)]" />
      <motion.span
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] bg-(--mat-chrome)"
        style={{ opacity: solid ? 1 : reduce ? undefined : tint }}
        animate={reduce && !solid ? { opacity: scrolled ? 1 : 0.35 } : undefined}
        transition={tween.fadeIn}
      />
      {children}
    </div>
  );
}

function isActive(r: ScheduleRun) {
  return r.status === "RUNNING" || r.status === "QUEUED";
}

/**
 * Run island (motion pattern §19, simplified to a popover that grows from the pill): appears only while a
 * run is queued or solving anywhere, so the planner can leave the studio and still see it.
 */
function RunIsland({ run }: { run: ScheduleRun }) {
  const { t } = useI18n();
  const label = run.status === "QUEUED" ? t("generate.queued") : t("glass.shell.solving", { pct: run.progress });
  return (
    <Popover>
      <PopoverTrigger
        render={
          <button type="button" className="flex h-8 items-center gap-2 rounded-full bg-tint-soft px-3 text-[12.5px] font-medium text-tint-text outline-none focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid="run-island">
            <span className="relative flex size-2" aria-hidden>
              <span className="absolute inset-0 rounded-full bg-(--accent) opacity-60 motion-safe:animate-ping" />
              <span className="relative size-2 rounded-full bg-(--accent)" />
            </span>
            <span className="tabular-nums">
              {t("glass.shell.runShort", { id: run.id })} · {run.status === "QUEUED" ? t("glass.shell.queuedShort") : `${run.progress}%`}
            </span>
          </button>
        }
      />
      <PopoverContent align="end" className="w-80 p-4">
        <div role="status" aria-live="polite" className="space-y-3">
          <p className="type-headline text-label-1">{t("glass.shell.runTitle", { id: run.id, term: run.term_code })}</p>
          <p className="text-[13px] text-label-2">{label}</p>
          <Progress value={run.progress} aria-label={label}>
            <ProgressTrack>
              <ProgressIndicator />
            </ProgressTrack>
          </Progress>
          <Button size="sm" variant="secondary" nativeButton={false} render={<Link href={`/runs/${run.id}`} />}>
            {t("glass.shell.openRun")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function RecentRuns() {
  const { t, locale } = useI18n();
  const runs = useRuns();
  const hydrated = useHydrated();
  const recent = hydrated ? (runs.data?.slice(0, 5) ?? []) : [];
  const unread = recent.filter(isActive).length;
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="icon" aria-label={t("nav.notifications")} className="relative">
            <Bell />
            {unread > 0 ? <span className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-(--accent)" aria-hidden /> : null}
          </Button>
        }
      />
      <PopoverContent align="end" className="w-[22rem] p-1.5">
        <p className="px-2.5 pt-1 pb-1 text-[11px] font-semibold text-label-3">{t("glass.shell.recentRuns")}</p>
        <ul>
          {recent.length === 0 ? <li className="px-2.5 py-2 text-[13px] text-label-2">{t("glass.shell.noRuns")}</li> : null}
          {recent.map((r) => (
            <li key={r.id}>
              <Link href={`/runs/${r.id}`} className="flex items-center gap-3 rounded-[10px] px-2.5 py-2 outline-none hover:bg-fill-2 focus-visible:bg-fill-2">
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-medium text-label-1">{t("glass.shell.runTitle", { id: r.id, term: r.term_code })}</span>
                  <span className="block text-[12px] text-label-3">{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(r.created_at))}</span>
                </span>
                <StatusBadge {...runStatusBadge(r, t)} />
              </Link>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

/** Desktop and tablet: two floating capsules (where am I · what can I do) that thicken on scroll. */
export function TopBar() {
  const { t } = useI18n();
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const crumbs = useBreadcrumbs();
  const runs = useRuns();
  const hydrated = useHydrated();
  const running = hydrated ? runs.data?.find(isActive) : undefined;
  return (
    <header className="pointer-events-none sticky top-0 z-30 hidden items-center gap-3 px-4 pt-2 pb-1 sm:px-6 lg:flex lg:px-8">
      <ThickeningCapsule className="pointer-events-auto min-w-0 px-3">
        <nav aria-label={t("glass.shell.breadcrumb")} className="min-w-0">
          <ol className="flex h-8 items-center gap-1 text-[13px]">
            {crumbs.map((c, i) => (
              <Fragment key={c.href}>
                {i > 0 ? (
                  <li aria-hidden className="text-label-4">
                    /
                  </li>
                ) : null}
                <li className={cn("truncate", i < crumbs.length - 2 && "hidden xl:block")}>
                  {c.current ? (
                    <span aria-current="page" className="font-semibold text-label-1">
                      {c.label}
                    </span>
                  ) : (
                    <Link href={c.href} className="text-label-2 outline-none hover:text-label-1 focus-visible:underline">
                      {c.label}
                    </Link>
                  )}
                </li>
              </Fragment>
            ))}
          </ol>
        </nav>
      </ThickeningCapsule>
      <div className="flex-1" />
      <ThickeningCapsule className="pointer-events-auto" label={t("glass.shell.toolbar")}>
        {running ? <RunIsland run={running} /> : null}
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          data-testid="open-palette"
          className="flex h-8 items-center gap-2 rounded-full px-3 text-[13px] text-label-2 outline-none transition-colors duration-(--dur-fast) hover:bg-fill-2 hover:text-label-1 focus-visible:outline-2 focus-visible:outline-(--focus)"
        >
          <Search className="size-4 stroke-[1.75]" aria-hidden />
          <span className="pr-6">{t("glass.shell.searchShort")}</span>
          <KbdHint keys={["mod", "K"]} />
        </button>
        <RecentRuns />
      </ThickeningCapsule>
    </header>
  );
}

/** Phones: a chrome bar with the page title (large titles live in the content) and the account. */
export function MobileTopBar() {
  const crumbs = useBreadcrumbs();
  const { solid, tint, titleOpacity, reduce, scrolled } = useThickening();
  const title = crumbs.at(-1)?.label ?? "";
  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-2 px-4 pt-[env(safe-area-inset-top)] lg:hidden" data-scrolled={scrolled}>
      <span aria-hidden className="pointer-events-none absolute inset-0 -z-20 [backdrop-filter:var(--mat-chrome-filter)] [-webkit-backdrop-filter:var(--mat-chrome-filter)]" />
      <motion.span aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-(--mat-chrome) shadow-[inset_0_-1px_0_0_var(--hairline)]" style={{ opacity: solid ? 1 : reduce ? undefined : tint }} animate={reduce && !solid ? { opacity: scrolled ? 1 : 0.35 } : undefined} transition={tween.fadeIn} />
      <motion.p className="type-headline min-w-0 flex-1 truncate text-label-1" style={{ opacity: reduce ? (scrolled ? 1 : 0) : titleOpacity }} aria-hidden>
        {title}
      </motion.p>
      <UserMenu compact />
    </header>
  );
}
