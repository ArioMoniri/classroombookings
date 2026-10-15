"use client";

/**
 * Busy state that is not motion-only (motion audit 2026-10-15, T1; motion.md §5 "Loops").
 *
 * - `aria-busy="true"` at once, so assistive tech knows the control is working.
 * - The label swaps to a gerund ("Kaydediliyor…") after 150 ms, so a fast request does not flicker.
 * - The control stays focusable (`aria-disabled`, never `disabled` while focused): Chromium blurs a
 *   focused button that becomes disabled and the keyboard user lands on <body>.
 * - Under reduced motion (OS query or the in-app switch) a static glyph replaces the spinner, so the
 *   frozen spinner never reads as an unrelated icon.
 *
 * `BusyButton` wraps `Button`; `BusyLabel` is the content alone for buttons that need their own markup.
 */
import { Hourglass, Loader2 } from "lucide-react";
import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { useReduce } from "@/lib/motion";
import { Button } from "./button";

export const BUSY_DELAY_MS = 150;

/** `true` once `busy` has lasted `delay` ms; resets as soon as the work ends. */
export function useBusyDelay(busy: boolean, delay: number = BUSY_DELAY_MS): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!busy) return;
    const id = window.setTimeout(() => setShown(true), delay);
    return () => {
      window.clearTimeout(id);
      setShown(false);
    };
  }, [busy, delay]);
  return busy && shown;
}

/** Props for any Base UI button while it works: aria-busy, aria-disabled, focus kept. */
export function busyProps(busy: boolean, disabled = false) {
  return {
    "aria-busy": busy || undefined,
    disabled: busy || disabled,
    focusableWhenDisabled: busy || undefined,
  } as const;
}

/** The glyph that stands for "working": a spinner, or a static hourglass under reduced motion. */
export function BusyGlyph({ className }: { className?: string }) {
  const reduce = useReduce();
  return reduce ? (
    <Hourglass aria-hidden data-busy-glyph="static" className={className} />
  ) : (
    <Loader2 aria-hidden data-busy-glyph="spin" className={["animate-spin", className].filter(Boolean).join(" ")} />
  );
}

export function BusyLabel({ busy, label, icon, children }: { busy: boolean; label: ReactNode; icon?: ReactNode; children: ReactNode }) {
  const show = useBusyDelay(busy);
  if (!show) {
    return (
      <>
        {icon}
        {children}
      </>
    );
  }
  return (
    <>
      <BusyGlyph />
      {label}
    </>
  );
}

type BusyButtonProps = ComponentProps<typeof Button> & {
  busy: boolean;
  /** the gerund shown while working ("Running…") */
  busyLabel: ReactNode;
  /** the idle icon; replaced by the busy glyph */
  icon?: ReactNode;
  children: ReactNode;
};

export function BusyButton({ busy, busyLabel, icon, disabled, children, ...props }: BusyButtonProps) {
  return (
    <Button {...props} {...busyProps(busy, Boolean(disabled))}>
      <BusyLabel busy={busy} label={busyLabel} icon={icon}>
        {children}
      </BusyLabel>
    </Button>
  );
}
