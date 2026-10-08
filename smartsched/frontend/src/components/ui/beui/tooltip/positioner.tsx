"use client";
// Source: https://beui.dev (components/motion/tooltip/positioner.tsx) via shadcn registry @beui/status-bar — https://github.com/starc007/ui-components
// Licence: MIT, Copyright (c) 2026 Saurabh Chauhan (full text: src/components/ui/LICENSES/beui-MIT.txt)
// Modified: no
/* eslint-disable react-hooks/refs -- vendored upstream code kept byte-identical for diffing against the registry; patterns are intentional upstream. Re-check these rules when re-syncing from the registry. */
import { useIsPresent } from "motion/react";
import { useCallback, useState, type ReactNode } from "react";
import { useTooltipPosition } from "./use-position";

type PositionProps = Parameters<typeof useTooltipPosition>[0];

/** Readiness lives with the mounted overlay, not a trigger ref's attach/detach cycle. */
export function TooltipPositioner({
  children,
  ...position
}: Omit<PositionProps, "open" | "onPosition"> & {
  children: (ready: boolean, present: boolean) => ReactNode;
}) {
  const present = useIsPresent();
  const [ready, setReady] = useState(false);
  const onPosition = useCallback(() => setReady(true), []);
  useTooltipPosition({ ...position, open: present, onPosition });
  return (
    <span
      ref={position.floatingRef}
      inert={!present}
      aria-hidden={!present || undefined}
      className="pointer-events-none fixed left-0 top-0 z-[9999] w-max"
      style={{ visibility: "hidden", maxWidth: "calc(100vw - 16px)" }}
    >
      {children(ready, present)}
    </span>
  );
}
