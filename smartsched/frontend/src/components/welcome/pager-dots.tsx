"use client";
/** Phone sheet page dots (spec §9): 8 px circles, the active one an 18 × 8 pill that moves (`layoutId`). Decorative: the "1 / 4" text carries the state. */
import { LayoutGroup, motion } from "motion/react";
import { useReduce } from "@/lib/motion";
import { instant, welcomeMotion } from "./motion";
import { cn } from "@/lib/utils";

export function PagerDots({ count, index, className }: { count: number; index: number; className?: string }) {
  const reduce = useReduce();
  return (
    <LayoutGroup id="welcome-dots">
      <div aria-hidden data-testid="welcome-dots" data-index={index} className={cn("flex items-center justify-center gap-1.5", className)}>
        {Array.from({ length: count }, (_, i) => (
          <span key={i} className={cn("relative h-2 rounded-full bg-fill-1", i === index ? "w-[18px]" : "w-2")}>
            {i === index ? <motion.span layoutId="welcome-dot" className="absolute inset-0 rounded-full bg-tint" transition={reduce ? instant : welcomeMotion.dot} /> : null}
          </span>
        ))}
      </div>
    </LayoutGroup>
  );
}
