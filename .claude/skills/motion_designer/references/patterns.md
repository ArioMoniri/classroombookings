# Motion pattern library (motion v14, React 19)

Every pattern has the same parts: **When**, **Code**, **Reduced motion**, **A11y**. Code imports tokens from `@/lib/motion`, which is a verbatim copy of `references/motion-tokens.ts`. Every `ts`/`tsx` block in this file is a complete module, and `scripts/check_snippets.py` type-checks it in strict mode. Keep that true when you edit this file.

Class names such as `glass`, `glass-thick` and `surface-solid` are placeholders for the material utilities defined in `docs/design/v2/liquid-glass.md`. Material (blur radius, tint, rim) belongs to that spec. Movement belongs to this one.

Global setup (once, in the client providers):

```tsx
"use client";
import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";
import { springs } from "@/lib/motion";

/** reducedMotion="user": Motion drops transform/layout animation when the OS asks; opacity still runs. */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={springs.smooth}>
      {children}
    </MotionConfig>
  );
}
```

`reducedMotion="user"` does not cover `filter`, `backgroundPosition`, `pathLength`, `animate()` on motion values, or CSS. Each pattern below handles those explicitly with `useReduce()`.

---

## 1. Glass panel appear / dismiss (materialise)

**When**: popovers, menus, the event sheet header card, the "jump to latest" pill. Apple's glass "materializes" by modulating light and does not simply fade. On the web we approximate that with scale 0.96→1, a 6 px content blur clearing, and opacity, all on the glass element itself. The panel grows from its trigger (`transformOrigin`). Exits take about 65 % of the entrance time.

```tsx
"use client";
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { springs, tween, useReduce, useReducedTransparency } from "@/lib/motion";

type GlassPanelProps = {
  open: boolean;
  /** CSS transform-origin pointing at the trigger, e.g. "top right" for a toolbar menu. */
  origin?: string;
  labelledBy: string;
  className?: string;
  children: ReactNode;
};

export function GlassPanel({ open, origin = "top center", labelledBy, className = "", children }: GlassPanelProps) {
  const reduce = useReduce();
  const solid = useReducedTransparency();
  const material = solid ? "surface-solid" : "glass";
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="glass-panel"
          role="dialog"
          aria-labelledby={labelledBy}
          className={`${material} ${className}`}
          style={{ transformOrigin: origin }}
          initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: -4, filter: "blur(6px)" }}
          animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
          exit={
            reduce
              ? { opacity: 0, transition: tween.reduced }
              : { opacity: 0, scale: 0.98, filter: "blur(4px)", transition: tween.exit }
          }
          transition={
            reduce ? tween.reduced : { default: springs.glassMorph, opacity: tween.fadeIn, filter: tween.fadeIn }
          }
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

CSS-only variant for Base UI popups (Popover, Menu, Dialog, Select), which expose `data-starting-style` / `data-ending-style`:

```css
.glass-popup {
  transform-origin: var(--transform-origin, top center);
  transition:
    transform var(--spring-glass-morph-ms) var(--spring-glass-morph),
    opacity var(--dur-base) var(--ease-out),
    filter var(--dur-base) var(--ease-out);
}
.glass-popup[data-starting-style] { opacity: 0; transform: scale(0.96) translateY(-4px); filter: blur(6px); }
.glass-popup[data-ending-style]   { opacity: 0; transform: scale(0.98); filter: blur(4px);
  transition-duration: var(--dur-fast); transition-timing-function: var(--ease-in); }
@media (prefers-reduced-motion: reduce) {
  .glass-popup { transition: opacity 100ms linear; }
  .glass-popup[data-starting-style], .glass-popup[data-ending-style] { transform: none; filter: none; }
}
```

**Reduced motion**: opacity only, 100 ms. **Reduced transparency**: `surface-solid` (opaque, 1 px border), and the motion is unchanged. **A11y**: focus moves into the panel after it opens. Do not wait for the animation, because the panel is interactive from frame 1. `Esc` closes, and focus returns to the trigger. The blur is on the panel, never on an ancestor (see SKILL.md, backdrop-root rule).

---

## 2. Segmented control with a morphing indicator

**When**: Day/Week zoom, Must/Try-to, Low/Normal/High, Classes/Exams. The glass pill slides with `glassMorph`, and its 1.2 % overshoot reads as liquid. One `LayoutGroup` per control instance, so two controls on a page never share the pill.

```tsx
"use client";
import { LayoutGroup, motion } from "motion/react";
import { useId, type KeyboardEvent } from "react";
import { springs, useReduce } from "@/lib/motion";

type Option<T extends string> = { value: T; label: string };

export function Segmented<T extends string>(props: {
  options: readonly Option<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  const { options, value, onChange, label } = props;
  const reduce = useReduce();
  const group = useId();

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const i = options.findIndex((o) => o.value === value);
    const next = options[(i + step + options.length) % options.length];
    if (!next) return;
    onChange(next.value);
    e.currentTarget.querySelector<HTMLElement>(`[data-value="${next.value}"]`)?.focus();
  }

  return (
    <LayoutGroup id={group}>
      <div role="radiogroup" aria-label={label} onKeyDown={onKeyDown} className="glass relative inline-flex rounded-full p-1">
        {options.map((o) => {
          const selected = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={selected}
              tabIndex={selected ? 0 : -1}
              data-value={o.value}
              onClick={() => onChange(o.value)}
              className="relative z-0 min-h-9 rounded-full px-3 text-sm"
            >
              {selected && (
                <motion.span
                  layoutId="segmented-pill"
                  aria-hidden
                  className="glass-thick pointer-events-none absolute inset-0 -z-10"
                  style={{ borderRadius: 999 }}
                  transition={reduce ? { duration: 0 } : springs.glassMorph}
                />
              )}
              {o.label}
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
```

**Reduced motion**: the pill jumps (`duration: 0`), and the label colour change stays. **A11y**: `radiogroup` with roving tabindex. Arrow keys move both selection and focus. The selected state is `aria-checked` plus a weight change, never only the pill. `borderRadius` goes through `style`, so Motion scale-corrects it during the morph.

---

## 3. Sidebar / tab-bar liquid morph

**When**: the mobile tab bar (< 768 px) and the desktop sidebar active indicator. The tab bar follows iOS 26: it floats, minimises while you scroll down (inactive labels collapse, the bar narrows) and re-expands when you scroll up. The bar and the active pill morph with `glassMorph`. The desktop sidebar reuses the same `layoutId` pill for its active row.

```tsx
"use client";
import { AnimatePresence, LayoutGroup, motion, useMotionValueEvent, useScroll } from "motion/react";
import { useState, type ReactNode, type RefObject } from "react";
import { springs, tween, useReduce } from "@/lib/motion";

type Tab = { href: string; label: string; icon: ReactNode };

export function GlassTabBar(props: { tabs: readonly Tab[]; active: string; scrollRef: RefObject<HTMLElement | null> }) {
  const { tabs, active, scrollRef } = props;
  const reduce = useReduce();
  const { scrollY } = useScroll({ container: scrollRef });
  const [compact, setCompact] = useState(false);

  useMotionValueEvent(scrollY, "change", (y) => {
    const prev = scrollY.getPrevious() ?? 0;
    if (y < 24) setCompact(false);
    else if (y - prev > 6) setCompact(true);
    else if (prev - y > 6) setCompact(false);
  });

  const morph = reduce ? { duration: 0 } : springs.glassMorph;

  return (
    <LayoutGroup id="tab-bar">
      <motion.nav
        aria-label="Primary"
        layout
        transition={morph}
        style={{ borderRadius: 999 }}
        data-compact={compact}
        className="glass fixed inset-x-0 bottom-[max(12px,env(safe-area-inset-bottom))] mx-auto flex w-fit gap-1 p-1"
      >
        {tabs.map((t) => {
          const isActive = t.href === active;
          return (
            // In the app use next/link <Link>; a plain anchor keeps this snippet framework-free.
            <motion.a
              key={t.href}
              layout="position"
              transition={morph}
              href={t.href}
              aria-label={t.label}
              aria-current={isActive ? "page" : undefined}
              className="relative flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-full px-3"
            >
              {isActive && (
                <motion.span
                  layoutId="tab-pill"
                  aria-hidden
                  className="glass-thick pointer-events-none absolute inset-0 -z-10"
                  style={{ borderRadius: 999 }}
                  transition={morph}
                />
              )}
              <span aria-hidden>{t.icon}</span>
              <AnimatePresence initial={false} mode="popLayout">
                {(!compact || isActive) && (
                  <motion.span
                    key="label"
                    aria-hidden
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0, transition: tween.fadeOut }}
                    transition={tween.fadeIn}
                    className="text-xs"
                  >
                    {t.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </motion.a>
          );
        })}
      </motion.nav>
    </LayoutGroup>
  );
}
```

Desktop sidebar collapse (248 → 56 px) uses the same idea. `motion.aside layout` plus `layout="position"` on each row icon, and labels fade out (`tween.fadeOut`) before the width changes. Motion measures twice (before/after) and animates `transform`, not `width` per frame.

**Reduced motion**: no minimise-on-scroll (keep `compact` false when `reduce`), and the pill and bar jump. **A11y**: links keep `aria-label` when the visible label is hidden, `aria-current="page"` marks the active tab, targets are ≥ 44 px, and the bar never covers the last row of content (the page adds bottom padding = bar height + safe area).

---

## 4. Sheet with detents

**When**: the event sheet and filters on phones/tablets, and the Studio slot pickers. Detents sit at 45 % and 92 % of the viewport. A flick projects with velocity to the nearest detent, and a strong downward flick dismisses. Following iOS 26, the glass is inset and translucent at the low detent and turns opaque as it reaches full height.

```tsx
"use client";
import { animate, motion, useDragControls, useMotionValue, useTransform, type PanInfo } from "motion/react";
import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { springs, useReduce } from "@/lib/motion";

const DETENTS = [0.45, 0.92] as const; // visible fraction of the viewport

export function DetentSheet(props: { open: boolean; onClose: () => void; labelledBy: string; children: ReactNode }) {
  const { open, onClose, labelledBy, children } = props;
  const reduce = useReduce();
  const controls = useDragControls();
  const [vh, setVh] = useState(800);
  const [detent, setDetent] = useState(0);
  const y = useMotionValue(800);

  useEffect(() => {
    const read = () => setVh(window.innerHeight);
    read();
    window.addEventListener("resize", read);
    return () => window.removeEventListener("resize", read);
  }, []);

  const offsets = DETENTS.map((d) => Math.round(vh * (1 - d)));
  const low = offsets[0] ?? 0;
  const high = offsets[1] ?? 0;
  // 0 at the low detent → 1 at full height: drives the opaque layer and the corner inset.
  const solidity = useTransform(y, [low, high], [0, 1]);
  const inset = useTransform(solidity, [0, 1], [0.975, 1]);

  const settle = (target: number, velocity = 0) =>
    animate(y, target, reduce ? { duration: 0 } : { ...springs.sheet, velocity });

  useEffect(() => {
    const c = settle(open ? (offsets[detent] ?? low) : vh);
    return () => c.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, vh]);

  function onDragEnd(_: PointerEvent, info: PanInfo) {
    const projected = y.get() + info.velocity.y * 0.2;
    if (info.velocity.y > 900 || projected > vh * 0.82) {
      onClose();
      return;
    }
    let best = 0;
    offsets.forEach((o, i) => {
      if (Math.abs(o - projected) < Math.abs((offsets[best] ?? 0) - projected)) best = i;
    });
    setDetent(best);
    settle(offsets[best] ?? low, info.velocity.y);
  }

  function cycleDetent(e: MouseEvent<HTMLButtonElement>) {
    if (e.detail !== 0) return; // pointer taps are drags; keyboard Enter/Space has detail 0
    const next = (detent + 1) % offsets.length;
    setDetent(next);
    settle(offsets[next] ?? low);
  }

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      className="glass fixed inset-x-0 top-0 h-dvh rounded-t-[28px]"
      style={{ y, scaleX: inset, transformOrigin: "top center" }}
      drag="y"
      dragListener={false}
      dragControls={controls}
      dragConstraints={{ top: high, bottom: vh }}
      dragElastic={{ top: 0.06, bottom: 0.4 }}
      dragMomentum={false}
      onDragEnd={onDragEnd}
    >
      <motion.div aria-hidden className="surface-solid pointer-events-none absolute inset-0 -z-10 rounded-[inherit]" style={{ opacity: solidity }} />
      <button
        type="button"
        aria-label={detent === 0 ? "Expand sheet" : "Collapse sheet"}
        onPointerDown={(e) => controls.start(e)}
        onClick={cycleDetent}
        className="mx-auto mt-2 block h-6 w-16 touch-none"
      >
        <span aria-hidden className="mx-auto block h-1.5 w-10 rounded-full bg-current opacity-40" />
      </button>
      {children}
    </motion.div>
  );
}
```

Render it inside the app's Dialog primitive (Base UI). The primitive owns the focus trap, `Esc`, scroll lock and the scrim. This component owns only movement.

**Reduced motion**: detents snap with no spring, and drag still works because it is direct manipulation. **A11y**: the grabber is a real button (Enter/Space cycles detents, and its label says what it will do). Drag is never the only way to resize. Content stays reachable at both detents by scrolling. **Perf**: the sheet moves by `transform` only. The opaque layer is an opacity crossfade, not an animated `backdrop-filter`.

---

## 5. Toast stack

**When**: move saved / undo, run finished, import done. At most 3 toasts are visible. Older ones tuck behind (scale −5 %, y −10 px each) and fan out on hover/focus. Swipe-x dismisses. Prefer the beUI *Animated Toast Stack* (MIT, already imported at `components/ui/beui/animated-toast-stack.tsx`), retimed to these tokens. The pattern below is the reference behaviour.

```tsx
"use client";
import { AnimatePresence, motion, type PanInfo } from "motion/react";
import { useState } from "react";
import { springs, tween, useReduce } from "@/lib/motion";

export type ToastItem = { id: string; title: string; action?: { label: string; onClick: () => void } };

const ROW = 64; // px, toast height incl. gap, used when fanned out

export function ToastStack(props: { toasts: readonly ToastItem[]; onDismiss: (id: string) => void; onPause: (paused: boolean) => void }) {
  const { toasts, onDismiss, onPause } = props;
  const reduce = useReduce();
  const [fanned, setFanned] = useState(false);
  const visible = toasts.slice(-3).reverse(); // newest first

  const setOpen = (open: boolean) => {
    setFanned(open);
    onPause(open); // timers pause while the user reads or focuses a toast
  };

  return (
    <section
      aria-label="Notifications (F8)"
      className="fixed bottom-4 right-4 z-50 w-[min(360px,calc(100vw-2rem))]"
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <ol aria-live="polite" aria-relevant="additions text" className="relative h-16">
        <AnimatePresence initial={false}>
          {visible.map((t, i) => (
            <motion.li
              key={t.id}
              className="glass absolute inset-x-0 bottom-0 flex min-h-14 items-center gap-3 rounded-2xl px-4"
              style={{ zIndex: 10 - i, transformOrigin: "bottom center" }}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.96 }}
              animate={
                reduce
                  ? { opacity: 1, y: fanned ? -i * ROW : 0 }
                  : { opacity: 1, y: fanned ? -i * ROW : -i * 10, scale: fanned ? 1 : 1 - i * 0.05 }
              }
              exit={{ opacity: 0, scale: reduce ? 1 : 0.96, transition: tween.exit }}
              transition={reduce ? tween.reduced : springs.smooth}
              drag={reduce ? false : "x"}
              dragSnapToOrigin
              dragElastic={0.6}
              onDragEnd={(_: PointerEvent, info: PanInfo) => {
                if (Math.abs(info.offset.x) > 80 || Math.abs(info.velocity.x) > 500) onDismiss(t.id);
              }}
            >
              <p className="flex-1 text-sm">{t.title}</p>
              {t.action && (
                <button type="button" onClick={t.action.onClick} className="min-h-9 rounded-full px-3 text-sm font-medium">
                  {t.action.label}
                </button>
              )}
              <button type="button" aria-label="Dismiss" onClick={() => onDismiss(t.id)} className="size-9 rounded-full">
                ×
              </button>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </section>
  );
}
```

If you keep `sonner` instead, cap its 400 ms default: `[data-sonner-toast] { transition-duration: var(--spring-smooth-ms) !important; transition-timing-function: var(--spring-smooth) !important; }` and `visibleToasts={3}`.

**Reduced motion**: no scale or swipe, opacity plus a position jump. **A11y**: a polite live region with additions only. Undo toasts stay ≥ 6 s and pause on hover/focus (WCAG 2.2.1). F8 focuses the region, and every action is a real button. Swipe is never the only dismissal.

---

## 6. List insert / remove / reorder

**When**: rule cards, the review tray, the issues rail, upload rows. Inserts fade and drop in 6 px, removals pop out of layout so the siblings close the gap at once, and reorder works by drag handle or Alt+↑/↓.

```tsx
"use client";
import { AnimatePresence, Reorder, useDragControls } from "motion/react";
import type { KeyboardEvent, Ref } from "react";
import { springs, tween, useReduce } from "@/lib/motion";

export type Row = { id: string; label: string };

export function SortableRows(props: {
  rows: readonly Row[];
  onReorder: (rows: Row[]) => void;
  announce: (message: string) => void;
}) {
  const { rows, onReorder, announce } = props;

  function move(from: number, to: number) {
    if (to < 0 || to >= rows.length) return;
    const next = [...rows];
    const [item] = next.splice(from, 1);
    if (!item) return;
    next.splice(to, 0, item);
    onReorder(next);
    announce(`${item.label} moved to position ${to + 1} of ${rows.length}`);
  }

  return (
    <Reorder.Group as="ul" axis="y" values={[...rows]} onReorder={onReorder} className="relative flex flex-col gap-2">
      <AnimatePresence initial={false} mode="popLayout">
        {rows.map((row, i) => (
          <SortableRow key={row.id} row={row} onKeyMove={(dir) => move(i, i + dir)} />
        ))}
      </AnimatePresence>
    </Reorder.Group>
  );
}

function SortableRow(props: { row: Row; onKeyMove: (dir: -1 | 1) => void; ref?: Ref<HTMLLIElement> }) {
  const { row, onKeyMove, ref } = props;
  const reduce = useReduce();
  const controls = useDragControls();

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (!e.altKey) return;
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      onKeyMove(e.key === "ArrowUp" ? -1 : 1);
    }
  }

  return (
    <Reorder.Item
      ref={ref}
      value={row}
      as="li"
      dragListener={false}
      dragControls={controls}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduce ? { opacity: 0, transition: tween.reduced } : { opacity: 0, scale: 0.98, transition: tween.exit }}
      transition={reduce ? { duration: 0 } : springs.smooth}
      whileDrag={reduce ? undefined : { scale: 1.02 }}
      className="glass flex items-center gap-2 rounded-xl p-3"
    >
      <button
        type="button"
        aria-label={`Reorder ${row.label}. Alt plus arrow keys move it.`}
        onPointerDown={(e) => controls.start(e)}
        onKeyDown={onKeyDown}
        className="size-9 cursor-grab touch-none rounded-lg"
      >
        ⋮⋮
      </button>
      <span>{row.label}</span>
    </Reorder.Item>
  );
}
```

**Reduced motion**: rows appear and disappear without travel, and siblings jump. **A11y**: keyboard reorder through Alt+↑/↓ on the handle, with a polite announcement ("moved to position 3 of 8"). Focus stays on the handle after a move. Do not stagger on filter or sort, only on first reveal (stagger rules in springs.md).

---

## 7. Drag-lift / drop-settle with magnetic snap (timetable events)

**When**: moving an event in the day/week grid. dnd-kit remains the drag engine (timetable-grid.md §4.2). Motion adds three things. **Lift**: scale 1.03 plus a deeper shadow, which is a pre-rendered layer fading in. **Magnetic snap**: the ghost is pulled toward the slot under the pointer within 16 px, and the drop-slot outline glides between cells with `snappy`. **Settle**: the drop animation uses the `snappy` spring as a CSS `linear()` easing, both for a valid move (into the new cell) and for a rejected one (spring back).

```tsx
"use client";
import { defaultDropAnimationSideEffects, type DropAnimation, type Modifier } from "@dnd-kit/core";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cssSpring, springs, useReduce } from "@/lib/motion";

/** Pull the dragged ghost toward the hovered slot. Full snap inside radius/3, linear falloff to `radius`. */
export function magneticSnap(radius = 16): Modifier {
  return ({ transform, activeNodeRect, over }) => {
    if (!activeNodeRect || !over) return transform;
    const x = activeNodeRect.left + transform.x;
    const y = activeNodeRect.top + transform.y;
    const dx = over.rect.left - x;
    const dy = over.rect.top - y;
    const d = Math.hypot(dx, dy);
    if (d > radius) return transform;
    const pull = d < radius / 3 ? 1 : 1 - (d - radius / 3) / (radius - radius / 3);
    return { ...transform, x: transform.x + dx * pull, y: transform.y + dy * pull };
  };
}

/** Settle into the final cell (or back to the origin on a rejected drop) with the snappy spring. */
export const settleDrop: DropAnimation = {
  duration: cssSpring.snappy.ms,
  easing: cssSpring.snappy.easing,
  sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: "0.4" } } }),
};

/** Content of <DragOverlay>: lifts on mount. Shadow is a separate layer so only opacity animates. */
export function LiftedGhost({ children }: { children: ReactNode }) {
  const reduce = useReduce();
  return (
    <motion.div
      className="relative"
      initial={{ scale: 1 }}
      animate={{ scale: reduce ? 1 : 1.03 }}
      transition={springs.snappy}
      style={{ touchAction: "none" }}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] shadow-[0_12px_32px_-8px_rgb(0_0_0/0.35)]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.12 }}
      />
      {children}
    </motion.div>
  );
}

/** One outline that glides between candidate slots instead of N outlines toggling. */
export function DropSlot(props: { status: "ok" | "conflict"; spanRows: number }) {
  const reduce = useReduce();
  return (
    <motion.div
      layoutId="drop-slot"
      aria-hidden
      transition={reduce ? { duration: 0 } : springs.snappy}
      className={props.status === "ok" ? "outline-2 outline-[var(--primary)]" : "outline-2 outline-dashed outline-[var(--status-infeasible-border)]"}
      style={{ gridRow: `span ${props.spanRows}`, borderRadius: 8 }}
    />
  );
}
```

Wiring: `<DndContext modifiers={[magneticSnap()]}>`, `<DragOverlay dropAnimation={reduce ? null : settleDrop}>` then `<LiftedGhost>`. Render `<DropSlot>` in the hovered cell only.

**Reduced motion**: no lift scale, no magnetic pull (pass `modifiers={[]}`), no drop animation, and the slot outline jumps. The ghost still follows the pointer 1:1 because that is direct manipulation. **A11y**: the keyboard path (Space to pick up, arrows, Space to drop) gets the same slot outline. dnd-kit announcements give the cell in words ("A 204, Wednesday P7"). Conflict is signalled by a dashed outline plus an icon plus text, never colour or motion alone.

---

## 8. Resize handles

**When**: changing an event's period span (bottom edge), and the Studio panel splitters. The height snaps per period, never per pixel. Each snap is one layout change that Motion animates with `snappy`, so dragging feels magnetic without per-frame layout.

```tsx
"use client";
import { motion } from "motion/react";
import { useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { springs, useReduce } from "@/lib/motion";

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function ResizableEvent(props: {
  span: number;
  min?: number;
  max: number;
  rowHeight: number;
  label: string;
  onCommit: (span: number) => void;
  children: ReactNode;
}) {
  const { span, min = 1, max, rowHeight, label, onCommit, children } = props;
  const reduce = useReduce();
  const [preview, setPreview] = useState(span);
  const start = useRef<{ y: number; span: number } | null>(null);
  const transition = reduce ? { duration: 0 } : springs.snappy;

  function onPointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = { y: e.clientY, span: preview };
  }
  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!start.current) return;
    const next = clamp(start.current.span + Math.round((e.clientY - start.current.y) / rowHeight), min, max);
    if (next !== preview) setPreview(next);
  }
  function onPointerUp() {
    start.current = null;
    if (preview !== span) onCommit(preview);
  }
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setPreview((p) => clamp(p + (e.key === "ArrowDown" ? 1 : -1), min, max));
    } else if (e.key === "Enter") {
      onCommit(preview);
    } else if (e.key === "Escape") {
      setPreview(span);
    }
  }

  return (
    <motion.div layout transition={transition} className="relative" style={{ height: preview * rowHeight }}>
      <motion.div layout="position" transition={transition}>
        {children}
      </motion.div>
      <div
        role="slider"
        tabIndex={0}
        aria-label={`Resize ${label}`}
        aria-orientation="vertical"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={preview}
        aria-valuetext={`${preview} periods`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onKeyDown={onKeyDown}
        className="absolute inset-x-0 bottom-0 h-2 cursor-ns-resize touch-none opacity-0 focus-visible:opacity-100 [@media(hover:hover)]:hover:opacity-100"
      />
    </motion.div>
  );
}
```

**Reduced motion**: the span jumps per period. **A11y**: the handle is a vertical slider (↑/↓ change, Enter commits, Esc reverts), its hit area is 8 px tall on pointer devices, and on touch it is replaced by the sheet's period-range picker (timetable-grid.md §4.4). The live validity text ("P7–P10, conflicts with ENG 102") goes to the grid's polite live region.

---

## 9. Conflict shake (subtle)

**When**: a rejected drop, an invalid inline edit, a precheck fix that failed. It plays once: 3 px amplitude, 2 cycles, 240 ms. It always comes with a persistent static signal (dashed outline plus text). It is never used for "loading" and never repeats while the error persists.

```tsx
"use client";
import { useAnimate } from "motion/react";
import { useCallback } from "react";
import { useReduce } from "@/lib/motion";

export function useConflictShake<T extends HTMLElement = HTMLDivElement>() {
  const [scope, animate] = useAnimate<T>();
  const reduce = useReduce();
  const shake = useCallback(() => {
    if (reduce || !scope.current) return; // the static dashed outline carries the message
    animate(scope.current, { x: [0, -3, 3, -2, 2, 0] }, { duration: 0.24, ease: "easeOut" });
  }, [animate, reduce, scope]);
  return [scope, shake] as const;
}
```

**Reduced motion**: no movement. The dashed outline and message appear immediately. **A11y**: the reason is announced in the polite live region ("Couldn't move: A 204 Wed P7 is taken by ENG 102"). The shake is decoration on top of that, not the message. The 240 ms single burst is far from the 3-flashes rule.

---

## 10. Success check draw

**When**: "Saved ✓" on rule cards, run finished, import committed. A ring draws (180 ms), then the tick draws (160 ms, starting 100 ms in), with a tiny `bouncySubtle` pop. Total ≤ 280 ms. The spinner-to-check morph from transitions.dev's free set inspired the idea, and it is re-implemented here, not copied.

```tsx
"use client";
import { AnimatePresence, motion } from "motion/react";
import { ease, springs, tween, useReduce } from "@/lib/motion";

export function SuccessCheck({ show, label }: { show: boolean; label: string }) {
  const reduce = useReduce();
  const draw = (delay: number, duration: number) =>
    reduce ? { duration: 0 } : { duration, delay, ease: ease.out };
  return (
    <AnimatePresence>
      {show && (
        <motion.svg
          key="check"
          viewBox="0 0 24 24"
          width={20}
          height={20}
          role="img"
          aria-label={label}
          initial={reduce ? { opacity: 1 } : { opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, transition: tween.exit }}
          transition={reduce ? { duration: 0 } : springs.bouncySubtle}
        >
          <motion.circle
            cx={12}
            cy={12}
            r={10}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            initial={{ pathLength: reduce ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={draw(0, 0.18)}
          />
          <motion.path
            d="M7 12.5l3.2 3.2L17 9"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.2}
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: reduce ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={draw(0.1, 0.16)}
          />
        </motion.svg>
      )}
    </AnimatePresence>
  );
}
```

**Reduced motion**: the finished check appears at once. **A11y**: the text "Saved" is next to it or in the live region. The SVG has `role="img"` and a label. Do not loop.

---

## 11. Number ticker

**When**: KPI tiles, the score ring value, "1,238 placed", rail counts. Animate on **change**, not on first paint. A dashboard that counts up from 0 on every visit is decoration. It uses the `ticker` spring (no overshoot, so the number never shows a wrong value), locale-formatted, with tabular figures.

```tsx
"use client";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect, useMemo } from "react";
import { springs, useReduce } from "@/lib/motion";

export function NumberTicker(props: { value: number; locale: string; format?: Intl.NumberFormatOptions }) {
  const { value, locale, format } = props;
  const reduce = useReduce();
  const fmt = useMemo(() => new Intl.NumberFormat(locale, format), [locale, format]);
  const integer = (format?.maximumFractionDigits ?? 0) === 0;
  const mv = useMotionValue(value); // first paint shows the real value
  const text = useTransform(mv, (v) => fmt.format(integer ? Math.round(v) : v));

  useEffect(() => {
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, springs.ticker);
    return () => controls.stop();
  }, [value, reduce, mv]);

  return (
    <span className="tabular-nums">
      <motion.span aria-hidden>{text}</motion.span>
      <span className="sr-only">{fmt.format(value)}</span>
    </span>
  );
}
```

**Reduced motion**: the value jumps. **A11y**: screen readers get the final number from the `sr-only` twin, never the intermediate frames. Changes that matter are announced by the owning component (for example "Score 92, up 3"), not by the ticker.

---

## 12. Skeleton → content crossfade

**When**: any async region. If data arrives in < 150 ms, show no skeleton. Once shown, keep it at least 300 ms so it never flashes. Skeleton and content share one grid cell, so the swap has no layout jump. Content enters with opacity plus 4 px y.

```tsx
"use client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { springs, tween, useReduce } from "@/lib/motion";

/** true only if `loading` lasted > delayMs; once true, stays true for ≥ minMs. */
function useSkeletonGate(loading: boolean, delayMs = 150, minMs = 300): boolean {
  const [show, setShow] = useState(false);
  const [shownAt, setShownAt] = useState(0);
  useEffect(() => {
    if (loading && !show) {
      const t = setTimeout(() => {
        setShow(true);
        setShownAt(Date.now());
      }, delayMs);
      return () => clearTimeout(t);
    }
    if (!loading && show) {
      const t = setTimeout(() => setShow(false), Math.max(0, minMs - (Date.now() - shownAt)));
      return () => clearTimeout(t);
    }
  }, [loading, show, shownAt, delayMs, minMs]);
  return show;
}

export function Reveal(props: { loading: boolean; skeleton: ReactNode; children: ReactNode }) {
  const { loading, skeleton, children } = props;
  const reduce = useReduce();
  const showSkeleton = useSkeletonGate(loading);
  return (
    <div aria-busy={loading} className="grid [&>*]:[grid-area:1/1]">
      <AnimatePresence initial={false}>
        {showSkeleton ? (
          <motion.div key="skeleton" aria-hidden exit={{ opacity: 0, transition: tween.fadeOut }}>
            {skeleton}
          </motion.div>
        ) : !loading ? (
          <motion.div
            key="content"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? tween.reduced : { default: springs.smooth, opacity: tween.fadeIn }}
          >
            {children}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
```

**Reduced motion**: the content fades in over 100 ms, and the skeleton shimmer is static (`.skeleton { animation: none }` in the global reduced-motion block). **A11y**: `aria-busy` on the region and the skeleton is `aria-hidden`. Focus is not moved by the swap.

---

## 13. Route transitions

**When**: every navigation inside the app shell. Enter only: content fades in and rises 6 px (`smooth`), and the old page leaves instantly. Apple's rule is "don't make people wait for an animation", and App Router exit animations would hold the old tree. Put it in `app/(app)/template.tsx`, which re-mounts on every navigation, while `layout.tsx` (the shell, the glass chrome) stays still. Spatial continuity between pages (list card → detail) uses `layoutId` only inside one route. Cross-route shared elements wait for React `<ViewTransition>` to leave experimental status in Next.js (checked 2026-10: still experimental).

```tsx
"use client";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { springs, tween, useReduce } from "@/lib/motion";

export default function Template({ children }: { children: ReactNode }) {
  const reduce = useReduce();
  return (
    <motion.div
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? tween.reduced : { default: springs.smooth, opacity: tween.fadeIn }}
      className="min-h-full"
    >
      {children}
    </motion.div>
  );
}
```

**Reduced motion**: 100 ms fade. **A11y**: Next's route announcer reads the new title, and focus moves to the page `<h1>` (tabIndex −1) after navigation, not after the animation. Caveat: while `y ≠ 0` the wrapper is a containing block for `position: fixed` children. Render page-level fixed UI (sheets, toasts) through portals.

---

## 14. Hover parallax with specular light (glass)

**When**: large glass cards only (dashboard KPI tiles, room cards, Studio summary). This is the web stand-in for Liquid Glass highlights that "respond to geometry". A soft light follows the pointer, and decoration moves ≤ 2 px against it. Text never moves, because sub-pixel text blurs. Fine pointers only. One card at a time (the hovered one).

```tsx
"use client";
import { motion, useMotionValue, useSpring, useTransform } from "motion/react";
import type { PointerEvent, ReactNode } from "react";
import { pointerSpring, useFinePointer, useReduce } from "@/lib/motion";

export function SpecularCard(props: { children: ReactNode; decoration?: ReactNode; className?: string }) {
  const { children, decoration, className = "" } = props;
  const live = useFinePointer() && !useReduce();
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const sx = useSpring(px, pointerSpring);
  const sy = useSpring(py, pointerSpring);
  // The light is a 200 % layer moved by transform: compositor-only, never repainted.
  const lightX = useTransform(sx, [0, 1], ["-25%", "25%"]);
  const lightY = useTransform(sy, [0, 1], ["-25%", "25%"]);
  const depthX = useTransform(sx, [0, 1], [2, -2]);
  const depthY = useTransform(sy, [0, 1], [2, -2]);

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width);
    py.set((e.clientY - r.top) / r.height);
  }
  function onPointerLeave() {
    px.set(0.5);
    py.set(0.5);
  }

  return (
    <div
      className={`glass relative isolate overflow-hidden ${className}`}
      onPointerMove={live ? onPointerMove : undefined}
      onPointerLeave={live ? onPointerLeave : undefined}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -inset-1/2 -z-10"
        style={{
          x: live ? lightX : "-12%",
          y: live ? lightY : "-12%",
          background: "radial-gradient(closest-side, rgb(255 255 255 / 0.12), transparent 70%)",
        }}
      />
      {decoration && (
        <motion.div aria-hidden className="pointer-events-none absolute inset-0 -z-10" style={live ? { x: depthX, y: depthY } : undefined}>
          {decoration}
        </motion.div>
      )}
      {children}
    </div>
  );
}
```

**Reduced motion / coarse pointer**: a static highlight at the top-left (the light is "parked"), with no parallax. **Reduced transparency**: drop the light layer entirely. **A11y**: purely decorative (`aria-hidden`, `pointer-events: none`), and contrast is checked with the light at its brightest spot. Peak highlight alpha ≤ 0.12 in light mode and ≤ 0.08 in dark mode.

---

## 15. Scroll-linked header that thickens its material

**When**: the app top bar, the Studio step header, the timetable sticky header. At rest the header is thin glass. As content scrolls under it, a tint layer fades in (0 → 1 over the first 48 px) and a hairline appears, so the material "thickens" without animating `backdrop-filter`. The timetable uses Apple's **hard** edge style (uniform tint over header plus pinned room headers). Other pages use the soft style (gradient mask at the bottom edge).

```tsx
"use client";
import { motion, useMotionValueEvent, useScroll, useTransform } from "motion/react";
import { useState, type ReactNode, type RefObject } from "react";
import { tween, useReduce } from "@/lib/motion";

export function GlassHeader(props: { scrollRef: RefObject<HTMLElement | null>; hard?: boolean; children: ReactNode }) {
  const { scrollRef, hard = false, children } = props;
  const reduce = useReduce();
  const { scrollY } = useScroll({ container: scrollRef });
  const tint = useTransform(scrollY, [0, 48], [0, 1]);
  const hairline = useTransform(scrollY, [24, 48], [0, 1]);
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 8));

  return (
    <header className="sticky top-0 z-30 isolate" data-scrolled={scrolled}>
      {/* constant backdrop-filter: one blur pass, never animated */}
      <div aria-hidden className="glass pointer-events-none absolute inset-0 -z-20" />
      <motion.div
        aria-hidden
        className={`glass-thick pointer-events-none absolute inset-0 -z-10 ${hard ? "" : "[mask-image:linear-gradient(to_bottom,black_70%,transparent)]"}`}
        style={{ opacity: reduce ? undefined : tint }}
        animate={reduce ? { opacity: scrolled ? 1 : 0 } : undefined}
        transition={tween.fadeIn}
      />
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-[var(--border)]"
        style={{ opacity: reduce ? (scrolled ? 1 : 0) : hairline }}
      />
      {children}
    </header>
  );
}
```

**Reduced motion**: a binary state (thin/thick) with a 180 ms opacity fade, not tied to scroll position. **Reduced transparency**: the header is opaque at all times, with the hairline only. **A11y**: the text contrast of header content is measured against the *thin* state over the busiest content, which is the worst case. **Perf**: `useScroll` runs on `ScrollTimeline` when available, and the tint layer only changes opacity.

---

## 16. Chat message streaming

**When**: the assistant panel. The bubble enters once (opacity plus 8 px, `smooth`). Streamed chunks fade in through a CSS class at zero JS cost (no Motion component per token). The list sticks to the bottom only if the user is already at the bottom, with no smooth scrolling while streaming. When done, chunks collapse into one text node.

```tsx
"use client";
import { motion } from "motion/react";
import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";
import { springs, useReduce } from "@/lib/motion";

export function useStickToBottom(ref: RefObject<HTMLElement | null>, trigger: unknown) {
  const pinned = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [ref]);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight; // instant: smooth-scrolling a moving target judders
  }, [ref, trigger]);
  return pinned;
}

export function StreamingMessage(props: { chunks: readonly string[]; done: boolean }) {
  const { chunks, done } = props;
  const reduce = useReduce();
  return (
    <motion.article
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={springs.smooth}
      aria-busy={!done}
      className="glass max-w-[68ch] rounded-2xl px-4 py-3"
    >
      <p className="whitespace-pre-wrap">
        {done
          ? chunks.join("")
          : chunks.map((c, i) => (
              <span key={i} className="stream-chunk">
                {c}
              </span>
            ))}
      </p>
    </motion.article>
  );
}
```

```css
.stream-chunk { animation: stream-in var(--dur-fast) var(--ease-out) both; }
@keyframes stream-in { from { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .stream-chunk { animation: none; } }
```

**Reduced motion**: chunks appear without a fade, and the bubble has no rise. **A11y**: the log container is `role="log"` with `aria-live="off"` while streaming, so a screen reader never reads token by token. When `done`, a separate `sr-only` polite region receives "Assistant replied: <first sentence>". When the user has scrolled up, a "Jump to latest" glass pill (pattern 1) appears instead of yanking the scroll.

---

## 17. AI "thinking" shimmer

**When**: waiting for the assistant, NL rule parsing, precheck "Checking…". A soft highlight sweeps across the label text (1.6 s, linear, looped). Looping indicators are the one exemption from the 300 ms rule, because they represent ongoing work and stop when it does. After 5 s an elapsed counter appears ("Thinking · 8 s"), as in Unify. Only one shimmer is on screen at a time.

```tsx
"use client";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { useReduce } from "@/lib/motion";

export function ThinkingShimmer(props: { label: string; startedAt: number }) {
  const { label, startedAt } = props;
  const reduce = useReduce();
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [startedAt]);

  return (
    <div role="status" className="inline-flex items-center gap-2 text-sm">
      {reduce ? (
        <span className="text-[var(--fg-muted)]">{label}</span>
      ) : (
        <motion.span
          className="bg-clip-text text-transparent forced-colors:text-[CanvasText]"
          style={{
            backgroundImage: "linear-gradient(90deg, var(--fg-muted) 35%, var(--fg) 50%, var(--fg-muted) 65%)",
            backgroundSize: "300% 100%",
          }}
          animate={{ backgroundPosition: ["100% 0%", "0% 0%"] }}
          transition={{ duration: 1.6, ease: "linear", repeat: Infinity }}
        >
          {label}
        </motion.span>
      )}
      {secs >= 5 && (
        <span aria-hidden className="tabular-nums text-[var(--fg-muted)]">
          · {secs} s
        </span>
      )}
    </div>
  );
}
```

**Reduced motion**: static muted text. **A11y**: `role="status"` announces the label once, the counter is `aria-hidden` so it doesn't re-announce every second, and forced-colors mode gets solid text. The shimmer is never the only sign of progress: the Send button turns into Stop.

---

## 18. Command palette open

**When**: ⌘K. It is a glass panel at the top third of the screen: scale 0.98 → 1, y −8 → 0, `glassMorph`, origin top-centre. The scrim fades in 120 ms. The highlighted row has one glass pill that glides between rows with `snappy` as the selection moves (keyboard or pointer). Closing is 120 ms, opacity plus scale 0.98. The existing palette is cmdk inside the Base UI Dialog, so the open/close animation is CSS on `data-starting-style`, and Motion handles only the row pill.

```css
.palette-popup {
  transform-origin: top center;
  transition:
    transform var(--spring-glass-morph-ms) var(--spring-glass-morph),
    opacity var(--dur-base) var(--ease-out);
}
.palette-popup[data-starting-style] { opacity: 0; transform: translateY(-8px) scale(0.98); }
.palette-popup[data-ending-style]   { opacity: 0; transform: scale(0.98);
  transition-duration: var(--dur-fast); transition-timing-function: var(--ease-in); }
.palette-backdrop { transition: opacity var(--dur-fast) var(--ease-out); }
.palette-backdrop[data-starting-style], .palette-backdrop[data-ending-style] { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .palette-popup { transition: opacity 100ms linear; }
  .palette-popup[data-starting-style], .palette-popup[data-ending-style] { transform: none; }
}
```

```tsx
"use client";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { springs, useReduce } from "@/lib/motion";

/** Put inside each cmdk <CommandItem>; cmdk sets data-selected on the active row. */
export function PaletteRow(props: { selected: boolean; children: ReactNode }) {
  const reduce = useReduce();
  return (
    <span className="relative flex w-full items-center gap-2 px-3 py-2">
      {props.selected && (
        <motion.span
          layoutId="palette-row"
          aria-hidden
          className="glass-thick pointer-events-none absolute inset-0 -z-10"
          style={{ borderRadius: 10 }}
          transition={reduce ? { duration: 0 } : springs.snappy}
        />
      )}
      {props.children}
    </span>
  );
}
```

**Reduced motion**: 100 ms fade, and the row pill jumps. **A11y**: cmdk provides the combobox/listbox roles and `aria-activedescendant`. The input is focused on open (frame 1, not after the animation). `Esc` closes and focus returns to the invoking element. Results update without animating list height.

---

## 19. Island morph (pill → card)

**When**: the shell "run in progress" island. A compact glass pill in the top bar ("Run #42 · 38 %") expands into a status card on click, the way the Dynamic Island expands. It is one `layoutId` morph with `glassMorph`. Content inside crossfades (`popLayout`) so text never stretches. beUI *Dynamic Island* (MIT) is the reference. Its 0.8 s duration/bounce shell spring is replaced by `glassMorph` to respect the ceiling.

```tsx
"use client";
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { springs, tween, useReduce } from "@/lib/motion";

export function RunIsland(props: { expanded: boolean; onToggle: () => void; compact: ReactNode; detail: ReactNode }) {
  const { expanded, onToggle, compact, detail } = props;
  const reduce = useReduce();
  const morph = reduce ? { duration: 0 } : springs.glassMorph;
  return (
    <motion.div
      layout
      transition={morph}
      style={{ borderRadius: expanded ? 24 : 999 }}
      className={`glass overflow-hidden ${expanded ? "w-[min(360px,calc(100vw-2rem))]" : "w-fit"}`}
    >
      <button type="button" aria-expanded={expanded} onClick={onToggle} className="block w-full text-left">
        <AnimatePresence initial={false} mode="popLayout">
          <motion.div
            key={expanded ? "detail" : "compact"}
            layout="position"
            initial={{ opacity: 0, filter: reduce ? "none" : "blur(4px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, transition: tween.exit }}
            transition={reduce ? tween.reduced : { duration: 0.18, ease: "easeOut" }}
          >
            {expanded ? detail : compact}
          </motion.div>
        </AnimatePresence>
      </button>
    </motion.div>
  );
}
```

**Reduced motion**: the size swaps instantly and the content fades over 100 ms. **A11y**: a disclosure button with `aria-expanded`. Progress lives in a polite `role="status"` inside `detail`, announced at phase changes only (Queued → Running → Done), not every percentage.
