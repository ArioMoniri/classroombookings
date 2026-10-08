"use client";
// Source: https://beui.dev (lib/hooks/use-hover-capable.ts) via shadcn registry @beui/status-bar — https://github.com/starc007/ui-components
// Licence: MIT, Copyright (c) 2026 Saurabh Chauhan (full text: src/components/ui/LICENSES/beui-MIT.txt)
// Modified: no
import { useEffect, useState } from "react";

/**
 * Returns true only on devices that have a true hover (mouse / trackpad).
 * Touch devices fire phantom `:hover` on tap that sticks until tap-elsewhere
 * — gate hover-only effects (scale lifts, magnetic pulls) behind this.
 */
export function useHoverCapable() {
  const [canHover, setCanHover] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
    const update = () => setCanHover(mq.matches);
    update();
    mq.addEventListener?.("change", update);
    return () => mq.removeEventListener?.("change", update);
  }, []);

  return canHover;
}
