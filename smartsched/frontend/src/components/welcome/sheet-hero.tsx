"use client";
/**
 * The sheet's hero (spec §8.2): the audience's Lottie poster, decorative (`aria-hidden`), 150 px on desktop and
 * 132 px on phones, hidden in short landscape. WG-09 (motion lane) replaces this with `WelcomeHero` (plays the clip
 * once to the poster frame; the new quick-reserve clip for academicians, staff and department admins).
 */
import Image, { type StaticImageData } from "next/image";
import { useTheme } from "next-themes";
import fileToRulesDark from "@/assets/lottie/file-to-rules-dark-poster.png";
import fileToRulesLight from "@/assets/lottie/file-to-rules-light-poster.png";
import heroSolverDark from "@/assets/lottie/hero-solver-dark-poster.png";
import heroSolverLight from "@/assets/lottie/hero-solver-light-poster.png";
import precheckFixDark from "@/assets/lottie/precheck-fix-dark-poster.png";
import precheckFixLight from "@/assets/lottie/precheck-fix-light-poster.png";
import type { Audience } from "@/lib/api/welcome";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

const POSTER: Record<"solver" | "files" | "precheck", { light: StaticImageData; dark: StaticImageData }> = {
  solver: { light: heroSolverLight, dark: heroSolverDark },
  files: { light: fileToRulesLight, dark: fileToRulesDark },
  precheck: { light: precheckFixLight, dark: precheckFixDark },
};
const CLIP: Record<Audience, keyof typeof POSTER> = {
  academician: "solver",
  staff: "solver",
  dept_admin: "solver",
  approver: "solver",
  viewer: "solver",
  planner: "files",
  admin: "precheck",
};

export function SheetHero({ audience, className }: { audience: Audience; className?: string }) {
  const { resolvedTheme } = useTheme();
  const hydrated = useHydrated();
  const theme = hydrated && resolvedTheme === "dark" ? "dark" : "light";
  const src = POSTER[CLIP[audience]][theme];
  return (
    <div aria-hidden data-testid="welcome-hero" className={cn("relative h-[132px] w-full shrink-0 overflow-hidden rounded-2xl bg-fill-3 sm:h-[150px] [@media(max-height:480px)]:hidden", className)}>
      {hydrated ? <Image src={src} alt="" fill sizes="(max-width: 640px) 100vw, 576px" className="object-cover" /> : null}
    </div>
  );
}
