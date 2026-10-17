"use client";
/**
 * Purpose: "When the planner switches a section or new results arrive, the content settles in place so they see
 * that the view changed" (motion skill pattern 12, skeleton → content). Enter only: opacity 0 → 1 and y 4 → 0 on
 * springs.smooth (settles ≈ 280 ms, under the 300 ms ceiling); no exit animation (the old panel is gone at once,
 * so nothing blocks input). Reduced motion: opacity only, 100 ms linear, no travel. Not used on frequent actions
 * (filters, sorting, cell focus): those change content with no motion.
 */
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { pick, springs, tween, useReduce } from "@/lib/motion";

export function FadePanel({ panelKey, children, className, ...rest }: { panelKey: string; children: ReactNode; className?: string } & Record<`data-${string}`, string | undefined>) {
  const reduce = useReduce();
  return (
    <motion.div
      key={panelKey}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
      animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={pick(reduce, springs.smooth, tween.reduced)}
      className={className}
      {...rest}
    >
      {children}
    </motion.div>
  );
}
