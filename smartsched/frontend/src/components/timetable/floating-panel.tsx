"use client";
/**
 * A glass panel anchored to a point (drop location, drag-create block). Motion pattern §1 "materialise":
 * the glass element scales 0.96 → 1 and fades (glassMorph); its *content* clears a 6 px blur (never a filter
 * on the backdrop-filter element, G6). Transform origin points at the anchor. Esc and an outside press close
 * it; focus moves in on open and returns to the opener on close.
 */
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";

export interface FloatingPanelProps {
  open: boolean;
  anchor: { x: number; y: number } | null;
  onClose: () => void;
  labelledBy: string;
  width?: number;
  className?: string;
  children: ReactNode;
  testId?: string;
}

export function FloatingPanel({ open, anchor, onClose, labelledBy, width = 340, className, children, testId }: FloatingPanelProps) {
  const reduce = useReduce();
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number; origin: string }>({ left: 0, top: 0, origin: "top left" });
  const opener = useRef<Element | null>(null);

  useLayoutEffect(() => {
    if (!open || !anchor) return;
    opener.current = document.activeElement;
    const h = ref.current?.offsetHeight ?? 260;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const right = anchor.x + 12 + width < vw - 8;
    const left = right ? anchor.x + 12 : Math.max(8, anchor.x - 12 - width);
    const below = anchor.y + h < vh - 8;
    const top = below ? Math.max(8, anchor.y - 16) : Math.max(8, vh - h - 8);
    setPos({ left, top, origin: `${right ? "left" : "right"} ${below ? "top" : "bottom"}` });
  }, [open, anchor, width]);

  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      const first = ref.current?.querySelector<HTMLElement>("[data-autofocus], button, input, select, textarea, [tabindex]:not([tabindex='-1'])");
      first?.focus();
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onDown, true);
    const back = opener.current;
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onDown, true);
      if (back instanceof HTMLElement) back.focus({ preventScroll: true });
    };
  }, [open, onClose]);

  if (typeof document === "undefined") return null;
  return createPortal(
    <AnimatePresence>
      {open && anchor ? (
        <motion.div
          key="floating"
          ref={ref}
          role="dialog"
          aria-labelledby={labelledBy}
          data-testid={testId}
          data-glass="thick"
          className={cn("glass-thick fixed z-50 rounded-2xl p-3 text-[13px] text-label-1", className)}
          style={{ left: pos.left, top: pos.top, width, transformOrigin: pos.origin }}
          initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: -4 }}
          animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
          exit={reduce ? { opacity: 0, transition: tween.reduced } : { opacity: 0, scale: 0.98, transition: tween.exit }}
          transition={reduce ? tween.reduced : { default: springs.glassMorph, opacity: tween.fadeIn }}
        >
          <motion.div initial={reduce ? false : { filter: "blur(6px)" }} animate={{ filter: "blur(0px)" }} transition={tween.fadeIn}>
            {children}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
