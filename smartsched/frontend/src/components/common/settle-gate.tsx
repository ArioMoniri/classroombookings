"use client";
/**
 * F-MB-1 (fix-b-2026-10-18, MOBILE.md M-15): a block whose parts load one after another (a card above another card,
 * each growing when its own query answers) pushes everything below it down several times. SettleGate shows ONE
 * placeholder of a reserved height until the parts are `ready`, then the whole block at once: content that appears
 * in place of a placeholder is new content (no layout shift); content that grows above rendered content shifts it.
 *
 * - The children are mounted from the start, inside a `hidden` wrapper, so their queries start at once (the gate
 *   costs no extra round trip) and their state is kept.
 * - It never holds longer than `capMs` (a slow or stuck request shows what has arrived).
 * - Once shown it stays shown: a refetch never hides the block again.
 * - Server render and hydration pass: `ready` must be computed the same way on both (e.g. from `useHydrated`).
 */
import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The longest a page waits for its parts before it shows what it has. */
export const SETTLE_CAP_MS = 1500;

export function SettleGate({
  ready,
  children,
  testId,
  placeholderClassName,
  placeholder,
  capMs = SETTLE_CAP_MS,
}: {
  ready: boolean;
  children: ReactNode;
  testId?: string;
  /** the reserved height (a min-height token such as `min-h-[60dvh]`) */
  placeholderClassName?: string;
  /** optional skeleton inside the placeholder */
  placeholder?: ReactNode;
  capMs?: number;
}) {
  const [shown, setShown] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  // latched during render (no effect needed): once shown, always shown
  if (!shown && (ready || timedOut)) setShown(true);
  useEffect(() => {
    if (shown) return;
    const id = setTimeout(() => setTimedOut(true), capMs);
    return () => clearTimeout(id);
  }, [shown, capMs]);
  const visible = shown || ready || timedOut;
  return (
    <>
      {visible ? null : (
        <div aria-busy="true" data-testid={testId} className={cn("min-h-[60dvh]", placeholderClassName)}>
          {placeholder}
        </div>
      )}
      <div hidden={!visible} data-slot="settle-gate">
        {children}
      </div>
    </>
  );
}
