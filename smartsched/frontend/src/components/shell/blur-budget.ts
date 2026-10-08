"use client";
/**
 * Glass budget for the shell chrome (calendar.md §13 rule 8: at most 5 `backdrop-filter` surfaces on screen;
 * liquid-glass.md G7; motion_designer §4). The calendar and the all-classes page spend that budget on their
 * own floating chrome (capsules, scrubber, calendar sidebar, inspector). While they are mounted the shell's
 * sidebar, top-bar capsules and phone bars are **tint-only**: same tint, grain, sheen, edge and ambient,
 * `--mat-chrome-filter: none`. No blur pass is spent on what sits behind them:
 *
 * - the sidebar only ever has the fixed scene behind it (it is a flex column, content never scrolls under
 *   it), and a 40 px blur of the smooth scene mesh is that same mesh, so it keeps its translucent tint;
 * - the capsules and phone bars float over scrolling content, so without blur the tint is the chrome solid
 *   (`--mat-chrome-solid`, the token the no-backdrop fallback already uses, liquid-glass.md §8). The
 *   thickening on scroll (motion pattern §15) is unchanged: it fades that tint layer, never a filter.
 */
import { usePathname } from "next/navigation";

/** Routes whose own chrome uses the glass budget (prefix match: `/timetable?run=…`, `/classes/…`). */
export const TINT_ONLY_ROUTES = ["/timetable", "/classes"] as const;

export function isTintOnlyRoute(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return TINT_ONLY_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

export function useTintOnlyChrome(): boolean {
  return isTintOnlyRoute(usePathname());
}

/** Translucent chrome over the scene without its blur pass (the sidebar). */
export const TINT_ONLY_OVER_SCENE = "[--mat-chrome-filter:none]";

/** Chrome over content without its blur pass: the chrome solid as the tint (tab bar, search orb). */
export const TINT_ONLY_OVER_CONTENT = "[--mat-chrome-filter:none] [--mat-chrome:var(--mat-chrome-solid)]";
