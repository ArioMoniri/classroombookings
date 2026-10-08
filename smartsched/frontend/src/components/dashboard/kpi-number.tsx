"use client";

import { MotionConfig } from "motion/react";
import { useState } from "react";
import { NumberTicker } from "@/components/ui/beui/number-ticker";
import { useReduce } from "@/lib/motion";

/**
 * beUI number ticker, tuned for SmartSched (motion.md §3.5, pattern §11, anti-pattern A9):
 * - **no count-up on page load**: the first value renders in place (the ticker's digit columns are set
 *   instantly through MotionConfig reducedMotion="always");
 * - only a value that changes while the page is open rolls, within the 300 ms ceiling (0.27 s, no stagger);
 * - reduced motion (OS or in-app) always jumps; screen readers get the final number (ticker's sr-only twin).
 */
export function KpiNumber({ value, format, className, prefix, suffix }: { value: number; format?: (n: number) => string; className?: string; prefix?: string; suffix?: string }) {
  const reduce = useReduce();
  const [first] = useState(value);
  const [changed, setChanged] = useState(false);
  if (!changed && value !== first) setChanged(true);
  return (
    <MotionConfig reducedMotion={changed && !reduce ? "never" : "always"}>
      <NumberTicker value={value} format={format} prefix={prefix} suffix={suffix} duration={0.27} stagger={0} startOnView={false} className={className} />
    </MotionConfig>
  );
}
