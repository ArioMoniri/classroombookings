"use client";
/**
 * HX-19 (audit m11, helper.md §7, motion.md §3.21): drag-to-dismiss and the exit timing of the phone helper sheet.
 *
 * Purpose: "the sheet came from below, you can push it back down, and it leaves the way it came."
 * - The handle drives a motion value 1:1 with the finger (no spring lag; pattern 4, skill §6). The same value is the
 *   sheet's `y`, so the enter/exit animations and the drag never fight.
 * - Release: past 30 % of the height or a downward flick → dismiss (`shouldDismissSheet` from ui/sheet, the rule every
 *   bottom sheet uses). Otherwise it springs back with `springs.sheet` carrying the release velocity; under reduced
 *   motion it is back on the same frame.
 * - Exits (≤ 200 ms, never slower than the ≈ 270 ms enter): ✕ / Esc slide down in `dur.base` with `ease.in`; a drag
 *   continues the flick in `dur.fast` with `ease.out`; desktop fades and moves 24 px in `dur.fast` `ease.in`. Reduced
 *   motion: every close is instant.
 * - `will-change: transform` is set on pointerdown and cleared on release (skill §4).
 */
import { animate, useMotionValue, type MotionValue, type TargetAndTransition } from "motion/react";
import { useRef, type PointerEvent, type RefObject } from "react";
import { shouldDismissSheet } from "@/components/ui/sheet";
import { dur, ease, springs } from "@/lib/motion";

export type HelperExitKind = "close" | "drag";

/** The exit target of the sheet for how it was closed. */
export function helperSheetExit(kind: HelperExitKind, { reduce, desktop }: { reduce: boolean; desktop: boolean }): TargetAndTransition {
  if (reduce) return { opacity: 0, transition: { duration: dur.instant } };
  if (desktop) return { opacity: 0, x: 24, transition: { duration: dur.fast, ease: ease.in } };
  if (kind === "drag") return { y: "100%", transition: { duration: dur.fast, ease: ease.out } };
  return { y: "100%", transition: { duration: dur.base, ease: ease.in } };
}

/** A tap moves less than this; more is a drag (its trailing click is ignored). */
const TAP_SLOP = 6;
/** Velocity is read from the last move only when it is this recent (ms); a finger that stopped is not a flick. */
const FLICK_WINDOW = 100;

type Gesture = { startY: number; h: number; lastY: number; lastT: number; prevY: number; prevT: number; moved: boolean };

export function useHelperSheetDrag(
  sheetRef: RefObject<HTMLElement | null>,
  { reduce, onDismiss }: { reduce: boolean; onDismiss: (kind: HelperExitKind) => void },
): {
  y: MotionValue<number | string>;
  handle: {
    onPointerDown: (e: PointerEvent<HTMLButtonElement>) => void;
    onPointerMove: (e: PointerEvent<HTMLButtonElement>) => void;
    onPointerUp: (e: PointerEvent<HTMLButtonElement>) => void;
    onPointerCancel: (e: PointerEvent<HTMLButtonElement>) => void;
    onClick: () => void;
  };
} {
  const y = useMotionValue<number | string>(0);
  const g = useRef<Gesture | null>(null);
  const suppressClick = useRef(false);

  const settle = (el: HTMLElement | null) => {
    if (el) el.style.willChange = "";
  };
  const springBack = (velocity: number) => {
    if (reduce) y.set(0);
    else animate(y, 0, { ...springs.sheet, velocity });
  };

  const finish = (e: PointerEvent<HTMLButtonElement>, cancelled: boolean) => {
    const s = g.current;
    g.current = null;
    const el = sheetRef.current;
    e.currentTarget.removeAttribute?.("data-dragging");
    settle(el);
    if (!s) return;
    suppressClick.current = s.moved;
    const dy = Math.max(0, e.clientY - s.startY);
    const t = performance.now();
    const recent = t - s.lastT <= FLICK_WINDOW;
    const v = recent ? (s.lastY - s.prevY) / Math.max(1, s.lastT - s.prevT) : 0; // px/ms, + = down
    if (!cancelled && s.moved && shouldDismissSheet(dy, s.h, v)) onDismiss("drag");
    else if (s.moved || dy > 0) springBack(v * 1000);
  };

  return {
    y,
    handle: {
      onPointerDown: (e) => {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        const el = sheetRef.current;
        if (!el) return;
        y.stop();
        const now = performance.now();
        g.current = { startY: e.clientY, h: el.getBoundingClientRect().height, lastY: e.clientY, lastT: now, prevY: e.clientY, prevT: now, moved: false };
        suppressClick.current = false;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        el.style.willChange = "transform";
      },
      onPointerMove: (e) => {
        const s = g.current;
        if (!s) return;
        const dy = Math.max(0, e.clientY - s.startY);
        if (!s.moved && Math.abs(e.clientY - s.startY) > TAP_SLOP) {
          s.moved = true;
          e.currentTarget.setAttribute?.("data-dragging", "");
        }
        s.prevY = s.lastY;
        s.prevT = s.lastT;
        s.lastY = e.clientY;
        s.lastT = performance.now();
        y.set(dy);
      },
      onPointerUp: (e) => finish(e, false),
      onPointerCancel: (e) => finish(e, true),
      onClick: () => {
        // the click after a drag is not a tap; a tap (or a screen-reader activation) closes, like the ✕
        if (suppressClick.current) {
          suppressClick.current = false;
          return;
        }
        onDismiss("close");
      },
    },
  };
}
