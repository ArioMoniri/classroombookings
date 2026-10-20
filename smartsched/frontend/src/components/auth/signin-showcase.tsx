"use client";
/**
 * The sign-in showcase (docs/design/v3/login-navbar-2026-10.md §2): the scene right of the sheet says what SmartSched
 * does (overline, headline, three value lines) and carries the schedule hero under the copy, centred, as the product
 * preview. Static text, nothing animates here (the hero keeps its own rules, auth.md §11.3). Only `/login` mounts it.
 *
 * - ≥ 1024: copy + hero; the hero frame is `--showcase-hero-w` wide (720 at ≥ 1280, 560 below), set on this element
 *   through CSS custom properties so the memoised hero never takes props.
 * - 768–1023: copy only (the hero is not mounted below 1024, AUX-10).
 * - < 768: no aside; the sheet shows the compact value list under the form instead (`SignInValueList compact`).
 * The copy sits above the hero in normal flow and never overlaps it (motion audit: the hero's centre is the scene's).
 */
import { CalendarCheck2, ClipboardCheck, DoorOpen, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { rich } from "./signin-shell";

const POINTS: readonly { key: MessageKey; icon: LucideIcon; testId: string; className?: string }[] = [
  { key: "signin.showcase.point1", icon: CalendarCheck2, testId: "signin-showcase-point-1" },
  { key: "signin.showcase.point2", icon: DoorOpen, testId: "signin-showcase-point-2" },
  // the height guard (spec §2.3): under 820 px tall the third line steps aside so the column fits 1024 × 768
  { key: "signin.showcase.point3", icon: ClipboardCheck, testId: "signin-showcase-point-3", className: "lg:[@media(max-height:820px)]:hidden" },
];

/** The three value lines: icon chip + one sentence, the first clause in label-1. */
export function SignInValueList({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { t } = useI18n();
  return (
    <ul className={cn("flex flex-col", compact ? "gap-2.5" : "gap-3 lg:max-xl:gap-2.5", className)}>
      {POINTS.map(({ key, icon: Icon, testId, className: extra }) => (
        <li key={key} className={cn("flex items-start gap-3 text-label-2", compact ? "type-footnote" : "type-body lg:max-xl:type-callout", !compact && extra)} data-testid={compact ? undefined : testId}>
          <span aria-hidden className={cn("flex shrink-0 items-center justify-center rounded-lg bg-tint-soft text-tint-text [&_svg]:stroke-[1.75]", compact ? "size-6 [&_svg]:size-3.5" : "size-7 [&_svg]:size-4")}>
            <Icon />
          </span>
          <span className={cn("min-w-0 [&_strong]:text-label-1", compact ? "pt-0.5" : "pt-0.5")}>{rich(t(key))}</span>
        </li>
      ))}
    </ul>
  );
}

/** The scene column right of the sheet. `hero` is the memoised SignInHero (rendered by the shell). */
export function SignInShowcase({ hero }: { hero: ReactNode }) {
  const { t } = useI18n();
  return (
    <aside
      aria-labelledby="signin-showcase-title"
      data-testid="signin-showcase"
      className="hidden min-w-0 flex-1 items-center justify-center px-(--showcase-pad) py-10 md:flex forced-colors:hidden"
    >
      <div className="flex w-full max-w-[300px] flex-col gap-(--showcase-gap) lg:max-w-(--showcase-max)">
        <div className="flex flex-col" data-testid="signin-showcase-copy">
          <p className="type-overline text-label-2 lg:[@media(max-height:820px)]:hidden">{t("signin.showcase.eyebrow")}</p>
          <h2 id="signin-showcase-title" className="mt-2 max-w-[22ch] type-title-2 text-balance text-label-1 xl:type-title-1">
            {t("signin.showcase.title")}
          </h2>
          <SignInValueList className="mt-5 lg:[@media(max-height:700px)]:hidden" />
        </div>
        {hero}
      </div>
    </aside>
  );
}
