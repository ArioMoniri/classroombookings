"use client";
/**
 * "Yeni" badge on a nav entry with an unseen hint (spec §4.5; transitions.dev notification-badge, retimed: one pop on
 * springs.bouncySubtle, ≤ 32 px; appears instantly under reduced motion). Decorative for assistive tech: the entry's
 * own name is unchanged and the hint itself says "Yeni: …".
 */
import { motion } from "motion/react";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { useEligibleHints } from "./registry";

export function NewBadge({ href }: { href: string }) {
  const { t } = useI18n();
  const reduce = useReduce();
  const hydrated = useHydrated();
  const hints = useEligibleHints();
  const hint = hints.find((h) => h.def.badge === href);
  if (!hydrated || !hint) return null;
  return (
    <motion.span
      aria-hidden
      data-testid={`new-badge-${hint.def.key}`}
      initial={reduce ? false : { scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={reduce ? { duration: 0 } : springs.bouncySubtle}
      className="ml-1.5 inline-flex h-4 shrink-0 items-center rounded-full bg-tint px-1.5 type-caption leading-none font-semibold text-tint-foreground"
    >
      {t("welcome.hints.new")}
    </motion.span>
  );
}
