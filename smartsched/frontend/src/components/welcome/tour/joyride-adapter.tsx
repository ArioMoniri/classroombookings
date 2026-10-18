"use client";
/**
 * React Joyride 3.2 (MIT, https://github.com/gilbarbara/react-joyride) behind our TourEngine interface (spec §4.2).
 * Loaded lazily (next/dynamic from the provider → tour-runner → here), so the library is not in any page's first load.
 *
 * - Controlled: one step at a time (`stepIndex` 0 of a one-step list, re-keyed per step); the runner owns the
 *   index, routes and events. Library beacons, buttons, scrolling and Escape handling are off (`skipBeacon`,
 *   `skipScroll`, `dismissKeyAction: false`, `overlayClickAction: false`); its focus trap, `aria-modal`, SVG overlay
 *   with the spotlight hole (no backdrop-filter: Liquid Glass ≤ 3 blur surfaces holds) and Floating UI positioning stay.
 * - `tooltipComponent` = our TourCard. Phones: docked at the bottom (fixed), above the tab bar when the target is in it.
 * - Non-interactive steps block clicks through the hole; interactive steps leave the target operable and turn the
 *   focus trap off so Tab can reach it.
 */
import { Joyride, type Step } from "react-joyride";
import { useId, useMemo } from "react";
import type { TourEngineProps } from "./engine";
import { TourCard, TourCardContext } from "./tour-card";
import { welcomeMotion } from "../motion";

/** The step card fades in (spec §8.1 "Step card in / out"); the card itself adds the .98 → 1 scale (tour-card.tsx). */
const FLOATER_IN = `opacity var(--dur-fast) var(--ease-out)`;
const FLOATER_IN_REDUCED = `opacity ${welcomeMotion.reduced.duration * 1000}ms linear`;

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return window.getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** Phones: dock the card at the bottom; 10 px above the target when the target sits in the bottom tab bar. */
function dockMiddleware(target: HTMLElement) {
  return {
    name: "welcome-dock",
    fn: ({ rects }: { rects: { floating: { width: number; height: number } } }) => {
      const vh = window.innerHeight;
      const r = target.getBoundingClientRect();
      const inTabBar = r.top > vh - 140;
      const gap = inTabBar ? vh - r.top + 10 : 8;
      return { x: 8, y: Math.max(8, vh - rects.floating.height - gap) };
    },
  };
}

export default function JoyrideAdapter({ step, controls, docked, reduceMotion }: TourEngineProps) {
  const bodyId = useId();
  const overlay = useMemo(() => cssVar("--overlay", "rgba(15, 23, 42, 0.45)"), []);
  const radius = Number.parseFloat(window.getComputedStyle(step.target).borderTopLeftRadius) || 8;
  const steps: Step[] = [
    {
      id: step.id,
      target: step.target,
      title: step.title,
      content: step.body,
      placement: docked ? "bottom" : "auto",
      isFixed: docked,
      floatingOptions: docked ? { strategy: "fixed", hideArrow: true, flipOptions: false, middleware: [dockMiddleware(step.target)] } : { hideArrow: true },
      width: docked ? "calc(100vw - 16px)" : 360,
    },
  ];
  return (
    <TourCardContext.Provider value={{ step, controls, docked, bodyId }}>
      <Joyride
        key={step.id}
        run
        continuous
        stepIndex={0}
        steps={steps}
        tooltipComponent={TourCard}
        loaderComponent={null}
        locale={{ back: "", close: "", last: "", next: "", skip: "" }}
        options={{
          skipBeacon: true,
          skipScroll: true,
          buttons: [],
          dismissKeyAction: false,
          overlayClickAction: false,
          blockTargetInteraction: !step.interactive,
          disableFocusTrap: step.interactive,
          overlayColor: overlay,
          backgroundColor: "transparent",
          spotlightPadding: 4,
          spotlightRadius: radius + 4,
          targetWaitTimeout: 0,
          zIndex: 10000,
          offset: 12,
        }}
        styles={{
          // docked: the fixed floating box itself spans the viewport; without a width it shrink-wrapped the card
          // (334 px of 390, the tooltip's 100% max-width follows it) (e2e 2026-10-18, wg-tour phone)
          floater: { filter: "none", transition: reduceMotion ? FLOATER_IN_REDUCED : FLOATER_IN, ...(docked ? { width: "calc(100vw - 16px)" } : {}) },
          tooltip: { padding: 0, backgroundColor: "transparent", borderRadius: 24 },
        }}
      />
    </TourCardContext.Provider>
  );
}
