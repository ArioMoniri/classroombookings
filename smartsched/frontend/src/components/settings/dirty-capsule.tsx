"use client";
/**
 * F-RF2-1 (fix-b-2026-10-18, MOBILE.md M-05): Ayarlar › Genel stacks cards that each save on their own (e-posta
 * bildirimleri, güvenlik iletişimi). On a phone their "Kaydet" sat 1700 px down the tab. Once a card has unsaved
 * changes, its save row becomes the page-actions capsule (`pageActionsCapsule`, fixed above the tab bar below lg, the
 * same pattern as /admin/settings' dirty `org-save`); at rest, and from lg up, it stays in its card.
 *
 * The SAME element changes class, so focus and the typed text are kept. Two changed cards stack their capsules
 * (3.75 rem apart: a 44 px button in the capsule's padding plus a gap) instead of covering each other.
 */
import { useEffect, useId, useSyncExternalStore, type CSSProperties } from "react";
import { pageActionsCapsule } from "@/components/admin/kit";
import { cn } from "@/lib/utils";

let order: string[] = [];
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

function setDirty(id: string, dirty: boolean) {
  const has = order.includes(id);
  if (dirty === has) return;
  order = dirty ? [...order, id] : order.filter((x) => x !== id);
  emit();
}

/** Capsule step between two stacked capsules. */
const STEP_REM = 3.75;

/** The capsule's bottom: above the tab bar (globals.css --shell-bottom-h), raised by its place in the stack. */
const DIRTY_CAPSULE = cn(pageActionsCapsule, "max-lg:bottom-[calc(var(--shell-bottom-h)+0.75rem+var(--capsule-offset,0rem))]");

export type DirtyCapsule = { props: { className?: string; style?: CSSProperties; "data-slot"?: "page-actions" }; index: number };

export function useDirtyCapsule(dirty: boolean, className?: string): DirtyCapsule {
  const id = useId();
  const index = useSyncExternalStore(
    subscribe,
    () => order.indexOf(id),
    () => -1,
  );
  // joins the stack when it gets changes, leaves it when saved, reset or unmounted
  useEffect(() => {
    setDirty(id, dirty);
    return () => setDirty(id, false);
  }, [id, dirty]);
  if (!dirty) return { props: { className }, index: -1 };
  const place = Math.max(0, index);
  return {
    props: { className: cn(className, DIRTY_CAPSULE), style: { "--capsule-offset": `${place * STEP_REM}rem` } as CSSProperties, "data-slot": "page-actions" },
    index: place,
  };
}

export const dirtyCapsuleIndex = (c: DirtyCapsule) => c.index;
