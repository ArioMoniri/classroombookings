"use client";
/**
 * The one spotlight ring (spec §4.2, §10): 3 px `--focus`, radius = the target's + 4 px, a 4 px gap, moving between
 * targets with motion `layout` (FLIP transforms, springs.smooth; it jumps under reduced motion). `aria-hidden`,
 * `pointer-events: none`. Forced colours: `Highlight`.
 */
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { springs } from "@/lib/motion";

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
  radius: number;
}

function measure(el: HTMLElement): Box {
  const r = el.getBoundingClientRect();
  const radius = Number.parseFloat(window.getComputedStyle(el).borderTopLeftRadius) || 8;
  return { left: r.left - 4, top: r.top - 4, width: r.width + 8, height: r.height + 8, radius: Math.min(radius + 4, (r.height + 8) / 2) };
}

export function SpotlightRing({ target, reduceMotion }: { target: HTMLElement | null; reduceMotion: boolean }) {
  const [box, setBox] = useState<Box | null>(null);
  useEffect(() => {
    if (!target) return setBox(null);
    let raf = 0;
    const update = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setBox(measure(target)));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(target);
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [target]);
  if (!box) return null;
  return (
    <motion.div
      aria-hidden
      data-testid="tour-ring"
      layout={!reduceMotion}
      transition={reduceMotion ? { duration: 0 } : springs.smooth}
      className="pointer-events-none fixed z-[10002] border-[3px] border-(--focus) forced-colors:border-[Highlight]"
      style={{ left: box.left, top: box.top, width: box.width, height: box.height, borderRadius: box.radius }}
    />
  );
}
